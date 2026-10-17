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
    async def test_global_override_preserves_category_and_individual_settings(self):
        queue = InterceptQueue()
        first, first_id = await self.start_scan(queue)
        queue.set_openai_all_scans(True)
        self.assertFalse(first.done())
        queue.choose_category(first_id, "erasure_chemical", provider="gemini")
        decision = await first
        self.assertEqual((decision.category, decision.provider), ("erasure_chemical", "openai"))
        queue.set_openai_all_scans(False)
        for individual in ["gemini", "openai"]:
            task, scan_id = await self.start_scan(queue)
            queue.choose_category(scan_id, "other", provider=individual)
            self.assertEqual((await task).provider, individual)

    async def test_global_applies_to_skip_and_timeout_without_admin(self):
        queue = InterceptQueue()
        queue.set_openai_all_scans(True)
        task, scan_id = await self.start_scan(queue)
        queue.skip_scan(scan_id)
        self.assertEqual((await task).provider, "openai")
        with patch("app.intercept_queue.INTERCEPT_WINDOW_SECONDS", 0.01):
            task, _ = await self.start_scan(queue)
            self.assertEqual((await task).provider, "openai")

    async def test_global_setting_persists_and_notifies_admins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            queue = InterceptQueue(path)
            events, _, loop = queue.subscribe()
            queue.set_openai_all_scans(True)
            event = await asyncio.wait_for(events.get(), timeout=1)
            self.assertEqual(event, {"event": "provider_settings", "data": {"openai_all_scans": True}})
            self.assertTrue(InterceptQueue(path).provider_settings()["openai_all_scans"])
            queue.set_openai_all_scans(False)
            self.assertFalse(InterceptQueue(path).provider_settings()["openai_all_scans"])
            queue.unsubscribe(events, loop)

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
    def test_global_enable_requires_key_and_does_not_submit_scans(self):
        with patch.object(intercept, "OPENAI_API_KEY", ""), patch.object(intercept, "intercept_queue") as queue:
            with self.assertRaises(HTTPException):
                intercept.set_provider_settings(intercept.InterceptProviderSettings(openai_all_scans=True), current_admin=Mock())
            queue.set_openai_all_scans.assert_not_called()
            intercept.set_provider_settings(intercept.InterceptProviderSettings(openai_all_scans=False), current_admin=Mock())
            queue.set_openai_all_scans.assert_called_once_with(False)
            queue.choose_category.assert_not_called()
            queue.skip_scan.assert_not_called()

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
        self.assertIn("REPORT WRITING RULES", payload["instructions"])
        self.assertIn("Do not invent observations", payload["instructions"])
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
                         "check_is_document"]:
                stack.enter_context(patch.object(analyze, name, side_effect=AssertionError(name)))
            lookup = stack.enter_context(patch.object(analyze, "match_sample_image", return_value=None))
            db = Mock()
            user = SimpleNamespace(id="test", scan_reset_date=None, scans_this_month=0)
            result = analyze._analyze_document_sync(
                Image.new("RGB", (20, 20)), "test.jpg", None, "receipt",
                None, None, None, None, None, None, None,
                user, db, "erasure_chemical", SimpleNamespace(), provider="openai",
            )
            provider.assert_called_once()
            lookup.assert_called_once()
            self.assertEqual(provider.call_args.kwargs["admin_category"], "erasure_chemical")
            db.query.assert_not_called()
            self.assertEqual(result["detected_category"], "erasure_chemical")
            saved = db.add.call_args.args[0]
            self.assertEqual(saved.analysis_method, "standard_openai")
            self.assertEqual(saved.analysis_model, "gpt-4.1-mini")

    def test_sample_match_uses_provider_for_visible_explanation(self):
        sample = SimpleNamespace(sample_path="Samples/Traced/forged.png", category="traced_projection", category_label="Projection Tracing", dataset_label="forged")
        for selected_provider in ["gemini", "openai"]:
            with self.subTest(provider=selected_provider), ExitStack() as stack:
                directory = stack.enter_context(tempfile.TemporaryDirectory())
                stack.enter_context(patch.object(analyze, "UPLOAD_DIR", Path(directory)))
                stack.enter_context(patch.object(analyze, "match_sample_image", return_value=sample))
                response = {**_coerce({**RESULT, "category": "traced_projection", "explanation": "Projection tracing: the visible strokes show uneven contours."}), "model_used": "test-model"}
                chosen = stack.enter_context(patch.object(analyze, selected_provider + "_classify", return_value=response))
                other = "gemini" if selected_provider == "openai" else "openai"
                stack.enter_context(patch.object(analyze, other + "_classify", side_effect=AssertionError(other)))
                db = Mock()
                db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
                user = SimpleNamespace(id="test", scan_reset_date=None, scans_this_month=0, gemini_api_key=None)
                result = analyze._analyze_document_sync(
                    Image.new("RGB", (20, 20)), "test.jpg", None, None,
                    None, None, None, None, None, None, None,
                    user, db, None, SimpleNamespace(), provider=selected_provider,
                )
                chosen.assert_called_once()
                field = "sample_category" if selected_provider == "gemini" else "admin_category"
                self.assertEqual(chosen.call_args.kwargs[field], "traced_projection")
                self.assertEqual(result["detected_category"], "traced_projection")
                self.assertEqual(result["category_explanation"], response["explanation"])
                self.assertEqual(db.add.call_args.args[0].analysis_model, "test-model")

    def test_admin_choice_still_overrides_openai_sample_match(self):
        with ExitStack() as stack:
            directory = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(patch.object(analyze, "UPLOAD_DIR", Path(directory)))
            stack.enter_context(patch.object(analyze, "match_sample_image", return_value=SimpleNamespace(
                sample_path="Samples/Traced/forged.png", category="traced_projection", dataset_label="forged",
            )))
            provider = stack.enter_context(patch.object(analyze, "openai_classify", return_value={
                **_coerce(RESULT), "model_used": "gpt-4.1-mini",
            }))
            db = Mock()
            result = analyze._analyze_document_sync(
                Image.new("RGB", (20, 20)), "test.jpg", None, None,
                None, None, None, None, None, None, None,
                SimpleNamespace(id="test", scan_reset_date=None, scans_this_month=0),
                db, "erasure_chemical", SimpleNamespace(), provider="openai",
            )
            self.assertEqual(provider.call_args.kwargs["admin_category"], "erasure_chemical")
            self.assertEqual(result["detected_category"], "erasure_chemical")
            self.assertEqual(db.add.call_args.args[0].analysis_method, "standard_openai")

    def test_missing_key_does_not_release_scan(self):
        with patch.object(intercept, "OPENAI_API_KEY", ""), patch.object(intercept, "intercept_queue") as queue:
            with self.assertRaises(HTTPException) as caught:
                intercept.decide_intercept_scan("test", intercept.InterceptDecision(category="erasure_chemical", provider="openai"), current_admin=Mock())
            self.assertEqual(caught.exception.status_code, 503)
            queue.choose_category.assert_not_called()


if __name__ == "__main__":
    unittest.main()
