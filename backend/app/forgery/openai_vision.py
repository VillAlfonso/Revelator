"""OpenAI image classification, used only for explicitly intercepted scans."""

import base64
import io
import json
import math

import requests
from PIL import Image

from .fixed_category import explanation_prompt

from ..config import OPENAI_API_KEY, OPENAI_VISION_MODEL
from .gemini_vision import (
    CATEGORY_CODES, CATEGORY_LABELS, SYSTEM_PROMPT, REPORT_EXPLANATION_RULES, _build_user_context_block, _coerce,
)


class OpenAIAnalysisError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def _report_schema(category=None):
    properties = {
        "category": {"type": "string", "enum": [category] if category else sorted(CATEGORY_CODES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "explanation": {"type": "string"},
        **{field: {"type": ["string", "null"]} for field in
           ("subtype", "anomaly_location", "tools_likely_used")},
        **{field: {"type": "array", "items": {"type": "string"}} for field in
           ("evidence", "reasoning_steps")},
        "alternatives": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "category": {"type": "string", "enum": sorted(CATEGORY_CODES)},
                "reasoning": {"type": "string"},
            },
            "required": ["category", "reasoning"],
        }},
    }
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}


def _validate_format(value, schema, field="report"):
    """Validate shape only; never echo model text or credential details in errors."""
    def invalid():
        raise OpenAIAnalysisError(f"OpenAI response has an invalid or missing {field} field. Please retry.")

    kind = schema["type"]
    if isinstance(kind, list):
        if value is not None and not isinstance(value, str):
            invalid()
    elif kind == "object":
        if not isinstance(value, dict):
            invalid()
        for name in schema["required"]:
            if name not in value:
                raise OpenAIAnalysisError(f"OpenAI response is missing {field}.{name}. Please retry.")
            _validate_format(value[name], schema["properties"][name], f"{field}.{name}")
    elif kind == "array":
        if not isinstance(value, list):
            invalid()
        for item in value:
            _validate_format(item, schema["items"], f"{field}[]")
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            invalid()
    elif kind == "string":
        if not isinstance(value, str) or ("enum" in schema and value not in schema["enum"]):
            invalid()
        if field == "report.explanation" and not value.strip():
            invalid()


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
        instructions = explanation_prompt(admin_category, CATEGORY_LABELS[admin_category]) + REPORT_EXPLANATION_RULES
    schema = _report_schema(admin_category)
    instructions += (
        "\nOUTPUT FORMAT: confidence is a JSON number between 0 and 1 (e.g. 0.95, "
        "never 95 or a percentage string). subtype, anomaly_location and tools_likely_used "
        "are strings or null, never lists. evidence and reasoning_steps are arrays of strings. "
        "Include every field required by the response schema."
    )
    def request_json(request_instructions, request_text):
        try:
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": OPENAI_VISION_MODEL,
                    "store": False,
                    "instructions": request_instructions,
                    "input": [{"role": "user", "content": [
                        {"type": "input_text", "text": request_text},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"},
                    ]}],
                    "text": {"format": {"type": "json_schema", "name": "forensic_report",
                                        "strict": True, "schema": schema}},
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
                raise OpenAIAnalysisError("OpenAI response was incomplete. Please retry.")
            if any(part.get("type") == "refusal"
                   for item in payload.get("output", []) if item.get("type") == "message"
                   for part in item.get("content", [])):
                raise OpenAIAnalysisError("OpenAI declined to generate this report.")
            text = "".join(
                part.get("text", "")
                for item in payload.get("output", []) if item.get("type") == "message"
                for part in item.get("content", []) if part.get("type") == "output_text"
            )
            return json.loads(text), payload.get("model")
        except (ValueError, TypeError, AttributeError, KeyError):
            raise OpenAIAnalysisError("OpenAI did not return valid JSON. Please retry.") from None
    try:
        task = "Explain the fixed category using visible image details and return JSON." if admin_category else "Analyze this image and return JSON."
        parsed, model_used = request_json(instructions, task + context)
        _validate_format(parsed, schema)
        if admin_category:
            parsed["category"] = admin_category
        result = _coerce(parsed)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise OpenAIAnalysisError("OpenAI did not return a complete, valid classification. Please retry.") from None
    result["model_used"] = model_used or OPENAI_VISION_MODEL
    return result
