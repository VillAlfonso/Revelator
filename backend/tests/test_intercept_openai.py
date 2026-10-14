import asyncio
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from PIL import Image

from app.forgery import openai_vision
from app.forgery.gemini_vision import _coerce
from app.intercept_queue import InterceptQueue
from app.routes import analyze, intercept


RESULT = {"category": "no_forgery_detected", "confidence": 0.9,
          "explanation": "No forgery detected. No visible alterations."}


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def start_scan(self, queue):
        task = asyncio.create_task(queue.wait_for_decision(
            user_id="test", username="test", email="test@example.com",
            filename="test.jpg", document_type=None, width=20, height=20,
            image_data=b"preview",
        ))
        await asyncio.sleep(0)
        return task, next(reversed(queue._pending))

    async def test_provider_is_per_scan_and_decision_is_once_only(self):
        queue = InterceptQueue()
        first, first_id = await self.start_scan(queue)
        second, second_id = await self.start_scan(queue)
        queue.choose_category(first_id, "erasure_chemical", provider="openai")
        with self.assertRaises(LookupError):
            queue.choose_category(first_id, "erasure_chemical", provider="openai")
        queue.choose_category(second_id, "other")
        first_decision = await first
        self.assertEqual((first_decision.provider, first_decision.category), ("openai", "erasure_chemical"))
        decision = await second
        self.assertEqual((decision.provider, decision.category), ("gemini", "other"))

    async def test_timeout_and_skip_keep_gemini(self):
        queue = InterceptQueue()
        with patch("app.intercept_queue.INTERCEPT_WINDOW_SECONDS", 0.01):
            task, _ = await self.start_scan(queue)
            self.assertEqual((await task).provider, "gemini")
        task, scan_id = await self.start_scan(queue)
        queue.skip_scan(scan_id)
        self.assertEqual((await task).provider, "gemini")

    async def test_expired_choice_rejected(self):
        queue = InterceptQueue()
        task, scan_id = await self.start_scan(queue)
        queue._pending[scan_id].deadline = 0
        with self.assertRaises(TimeoutError):
            queue.skip_scan(scan_id, provider="openai")
        self.assertEqual((await task).provider, "gemini")


class OpenAITests(unittest.TestCase):
    def test_decision_passes_category_and_provider_together(self):
        with patch.object(intercept, "OPENAI_API_KEY", "test-key"), patch.object(intercept, "intercept_queue") as queue:
            intercept.decide_intercept_scan(
                "test", intercept.InterceptDecision(category="erasure_chemical", provider="openai"), current_admin=Mock(),
            )
            queue.choose_category.assert_called_once_with("test", "erasure_chemical", provider="openai")
            queue.skip_scan.assert_not_called()
        self.assertEqual(intercept.InterceptDecision(category="other").provider, "gemini")

    @patch.object(openai_vision, "OPENAI_API_KEY", "test-key")
    @patch.object(openai_vision.requests, "post")
    def test_image_context_and_result(self, post):
        post.return_value = Mock(status_code=200, ok=True)
        post.return_value.json.return_value = {
            "status": "completed", "model": "gpt-4.1-mini",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(RESULT)},
            ]}],
        }
        result = openai_vision.classify(Image.new("RGB", (20, 20)), document_type="receipt", admin_category="erasure_chemical")
        self.assertEqual(result["category"], "erasure_chemical")
        self.assertEqual(result["category_label"], "Alteration - Erasure: Chemical")
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertIn("CLASSIFICATION CONSTRAINT: Use exactly erasure_chemical", payload["instructions"])
        self.assertIn("receipt", payload["input"][0]["content"][0]["text"])
        self.assertTrue(payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,"))
        post.return_value.json.return_value["status"] = "incomplete"
        with self.assertRaises(openai_vision.OpenAIAnalysisError):
            openai_vision.classify(Image.new("RGB", (20, 20)))

    @patch.object(openai_vision, "OPENAI_API_KEY", "test-key")
    @patch.object(openai_vision.requests, "post")
    def test_provider_errors_are_safe(self, post):
        for status, expected in [(401, 422), (403, 422), (429, 429), (500, 503)]:
            post.return_value = Mock(status_code=status, ok=False, text="secret-key")
            with self.assertRaises(openai_vision.OpenAIAnalysisError) as caught:
                openai_vision.classify(Image.new("RGB", (20, 20)))
            self.assertEqual(caught.exception.status_code, expected)
            self.assertNotIn("secret-key", str(caught.exception))

    def test_pipeline_uses_only_openai_and_saves_result(self):
        with ExitStack() as stack:
            directory = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(patch.object(analyze, "UPLOAD_DIR", Path(directory)))
            provider = stack.enter_context(patch.object(analyze, "openai_classify", return_value={
                **_coerce(RESULT), "model_used": "gpt-4.1-mini",
            }))
            for name in ["gemini_classify", "confidence_gated_analyze", "explain_with_hint",
                         "match_sample_image", "check_is_document"]:
                stack.enter_context(patch.object(analyze, name, side_effect=AssertionError(name)))
            db = Mock()
            user = SimpleNamespace(id="test", scan_reset_date=None, scans_this_month=0)
            result = analyze._analyze_document_sync(
                Image.new("RGB", (20, 20)), "test.jpg", None, "receipt",
                None, None, None, None, None, None, None,
                user, db, "erasure_chemical", SimpleNamespace(), provider="openai",
            )
            provider.assert_called_once()
            self.assertEqual(provider.call_args.kwargs["admin_category"], "erasure_chemical")
            db.query.assert_not_called()
            self.assertEqual(result["detected_category"], "erasure_chemical")
            saved = db.add.call_args.args[0]
            self.assertEqual(saved.analysis_method, "standard_openai")
            self.assertEqual(saved.analysis_model, "gpt-4.1-mini")

    def test_missing_key_does_not_release_scan(self):
        with patch.object(intercept, "OPENAI_API_KEY", ""), patch.object(intercept, "intercept_queue") as queue:
            with self.assertRaises(HTTPException) as caught:
                intercept.decide_intercept_scan("test", intercept.InterceptDecision(category="erasure_chemical", provider="openai"), current_admin=Mock())
            self.assertEqual(caught.exception.status_code, 503)
            queue.choose_category.assert_not_called()


if __name__ == "__main__":
    unittest.main()
