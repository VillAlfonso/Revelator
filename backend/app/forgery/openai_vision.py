"""OpenAI image classification, used only for explicitly intercepted scans."""

import base64
import io
import json
import math

import requests
from PIL import Image

from ..config import OPENAI_API_KEY, OPENAI_VISION_MODEL
from .gemini_vision import (
    CATEGORY_CODES, CATEGORY_LABELS, SYSTEM_PROMPT, REPORT_EXPLANATION_RULES, _build_user_context_block, _coerce,
)


class OpenAIAnalysisError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def classify(
    image: Image.Image,
    document_type=None,
    suspicion_reason=None,
    area_of_concern=None,
    image_source=None,
    is_forged_belief=None,
    shot_type=None,
    lighting=None,
    physical_clues=None,
    admin_category=None,
):
    if not OPENAI_API_KEY:
        raise OpenAIAnalysisError("OpenAI API key is not configured on the server")

    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=88)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    context = _build_user_context_block(
        document_type, suspicion_reason, area_of_concern, image_source,
        is_forged_belief, shot_type, lighting, physical_clues,
    )
    instructions = SYSTEM_PROMPT + REPORT_EXPLANATION_RULES
    if admin_category:
        if admin_category not in CATEGORY_CODES:
            raise ValueError("Unknown administrator category")
        instructions += (
            "\n\nCLASSIFICATION CONSTRAINT: Use exactly "
            f"{admin_category} ({CATEGORY_LABELS[admin_category]}) in the JSON category field. "
            "Explain the selected category using visible image evidence. "
            "Describe uncertainty honestly and do not invent evidence."
        )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_VISION_MODEL,
                "store": False,
                "instructions": instructions,
                "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": "Analyze this image and return JSON." + context},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"},
                ]}],
                "text": {"format": {"type": "json_object"}},
                "max_output_tokens": 4096,
            },
            timeout=(10, 120),
        )
    except requests.RequestException:
        raise OpenAIAnalysisError("OpenAI could not be reached. Please try another scan.") from None

    # Do not surface raw provider errors, which can contain credential details.
    if response.status_code in {401, 403}:
        raise OpenAIAnalysisError("OpenAI rejected the server API key or model access", 422)
    if response.status_code == 429:
        raise OpenAIAnalysisError("OpenAI quota or rate limit reached. Check API billing and retry.", 429)
    if not response.ok:
        raise OpenAIAnalysisError(f"OpenAI request failed (HTTP {response.status_code})")
    try:
        payload = response.json()
        if payload.get("status") != "completed":
            raise ValueError("Incomplete response")
        text = "".join(
            part.get("text", "")
            for item in payload.get("output", []) if item.get("type") == "message"
            for part in item.get("content", []) if part.get("type") == "output_text"
        )
        parsed = json.loads(text)
        if (
            not isinstance(parsed, dict)
            or parsed.get("category") not in CATEGORY_CODES
            or not isinstance(parsed.get("explanation"), str)
            or not parsed["explanation"].strip()
            or not math.isfinite(float(parsed.get("confidence")))
            or not 0 <= float(parsed["confidence"]) <= 1
        ):
            raise ValueError("Invalid classification")
        if admin_category:
            parsed["category"] = admin_category
        result = _coerce(parsed)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise OpenAIAnalysisError("OpenAI did not return a complete, valid classification. Please retry.") from None
    result["model_used"] = payload.get("model") or OPENAI_VISION_MODEL
    return result
