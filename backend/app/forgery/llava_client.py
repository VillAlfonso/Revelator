"""
LLaVA inference client - STUB.

This module is the contract between Revelator's backend and the eventual
fine-tuned LLaVA models hosted on Hugging Face Spaces. Two endpoints are
expected to exist:

  Detective: LLaVA fine-tuned on 100 imgs/category
  Sherlock:  LLaVA fine-tuned on 500 imgs/category + document-type data

Until those Spaces are deployed, every call here returns `None` and the
analyze endpoint falls back to the Analyst (Gemini) result. To wire it up,
fill in the `_call_llava_space()` helper and set the env vars listed below.

Required env vars (when ready):
  LLAVA_DETECTIVE_URL   e.g. https://yourname-llava-detective.hf.space/api/predict
  LLAVA_SHERLOCK_URL    e.g. https://yourname-llava-sherlock.hf.space/api/predict
  LLAVA_API_KEY         optional bearer token if the Space is private
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from PIL import Image

# ── Config (read from env at import time so swaps don't require a code change) ──
LLAVA_DETECTIVE_URL = os.getenv("LLAVA_DETECTIVE_URL", "")
LLAVA_SHERLOCK_URL = os.getenv("LLAVA_SHERLOCK_URL", "")
LLAVA_API_KEY = os.getenv("LLAVA_API_KEY", "")


# ── Public API ────────────────────────────────────────────────────────────────

def classify_detective(image: Image.Image, document_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call the Detective tier (LLaVA-100). Returns None if not configured."""
    if not LLAVA_DETECTIVE_URL:
        return None
    return _call_llava_space(LLAVA_DETECTIVE_URL, image, document_type, tier="detective")


def classify_sherlock(image: Image.Image, document_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call the Sherlock tier (LLaVA-500 + document-type data). Returns None
    if not configured."""
    if not LLAVA_SHERLOCK_URL:
        return None
    return _call_llava_space(LLAVA_SHERLOCK_URL, image, document_type, tier="sherlock")


# ── Internal ──────────────────────────────────────────────────────────────────

def _call_llava_space(
    url: str,
    image: Image.Image,
    document_type: Optional[str],
    tier: str,
) -> Optional[Dict[str, Any]]:
    """STUB: send the image to the configured HF Space and parse the response.

    The real implementation will look something like:

        import io, base64, requests
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode()
        headers = {"Authorization": f"Bearer {LLAVA_API_KEY}"} if LLAVA_API_KEY else {}
        payload = {"data": [b64, document_type or "other"]}
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        out = r.json()["data"][0]   # Gradio response shape
        return _normalize(out)

    Expected response shape (must match gemini_vision.classify):
        {
            "category":           "<one of CATEGORY_CODES>",
            "category_label":     "<human label>",
            "subtype":            "<short string or empty>",
            "confidence":         0.0–1.0,
            "explanation":        "<plain-language summary>",
            "evidence":           ["<bullet>", ...],
            "tools_likely_used":  "<short string>",
            "certainty_level":    "HIGH" | "MEDIUM" | "LOW",
        }

    Returns None on any failure so analyze() can fall back to Analyst.
    """
    # Stub: not yet wired. Returning None makes analyze() fall back to Gemini.
    return None


def expected_response_shape() -> dict:
    """Doc-helper: shape that LLaVA Spaces must return for Revelator to parse."""
    return {
        "category": "str",
        "category_label": "str",
        "subtype": "str",
        "confidence": "float (0..1)",
        "explanation": "str",
        "evidence": "List[str]",
        "tools_likely_used": "str",
        "certainty_level": "HIGH | MEDIUM | LOW",
    }
