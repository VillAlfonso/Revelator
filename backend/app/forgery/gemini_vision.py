"""
Gemini Vision — primary forensic classifier.

Reads the document image and returns a structured JSON verdict against the
19-category taxonomy. Output is parsed into a dict that the analyze route
saves to the Scan row.

The 19 categories cover the 16 trained forgery classes plus three fallbacks:
  - no_forgery_detected  → image is a document, but nothing suspicious
  - not_a_document       → meme, selfie, joke; the explanation says what it is
  - other                → real forgery that doesn't fit the 16; describe freely
"""

from __future__ import annotations

import io
import json
import re
from typing import Optional, Dict, Any

from PIL import Image

from ..config import GEMINI_API_KEY, GEMINI_VISION_MODEL


# ── Category taxonomy ──────────────────────────────────────────────────────
# Each tuple: (code, human-readable label). The code is what gets stored in
# Scan.detected_category and surfaced to the frontend.
CATEGORIES = [
    # Traced
    ("traced_carbon",            "Traced — Carbon Transfer"),
    ("traced_indentation",       "Traced — Indentation / Canal Light"),
    ("traced_projection",        "Traced — Projection Process"),
    # Alteration
    ("addition_insertion",       "Alteration — Addition: Insertion"),
    ("addition_interlineation",  "Alteration — Addition: Interlineation"),
    ("erasure_chemical",         "Alteration — Erasure: Chemical"),
    ("erasure_mechanical",       "Alteration — Erasure: Mechanical"),
    # Digital
    ("digital_cut_paste",        "Cut and Paste Forgery"),
    ("digital_desktop",          "Digital — Desktop Publishing"),
    ("digital_scanned",          "Digital — Scanned Document"),
    # Obliteration
    ("obliteration_ink",         "Obliteration — Ink Stroke"),
    ("obliteration_whiteout",    "Obliteration — White Out"),
    ("obliteration_pigment",     "Obliteration — Opaque Pigment"),
    # Sympathetic Ink
    ("sympathetic_indented",     "Sympathetic Ink — Indented Writing"),
    ("sympathetic_special",      "Sympathetic Ink — Special Ink"),
    # Currency
    ("currency_analysis",        "Currency Forgery"),
    # Fallbacks
    ("no_forgery_detected",      "No Forgery Detected"),
    ("not_a_document",           "Not a Document"),
    ("other",                    "Other Forgery"),
]

CATEGORY_CODES = [c[0] for c in CATEGORIES]
CATEGORY_LABELS = dict(CATEGORIES)


SYSTEM_PROMPT = """You are a forensic document examiner. You will be shown an image and you must classify it into EXACTLY ONE of these 19 categories.

CATEGORY CODES (use the code on the left in your JSON response):

Traced (signature/text traced from a source onto a target document):
  traced_carbon            — Carbon-paper transfer; faint carbon residue along strokes.
  traced_indentation       — Pressure indentation visible on backside or via raking light.
  traced_projection        — Projected/light-table tracing; uniform line weight, no carbon, no grooves.

Alteration:
  addition_insertion       — New characters/digits inserted INSIDE existing words or numbers.
  addition_interlineation  — New writing squeezed BETWEEN existing lines.
  erasure_chemical         — Bleach/solvent erasure; discoloration halo, fiber damage, ink ghosting.
  erasure_mechanical       — Eraser/blade scraping; thinned/abraded paper, surface roughness.

Cut and Paste / Digital Fabrication:
  digital_cut_paste        — A section physically cut from one document and pasted onto another (visible edges, shadows, texture mismatch, adhesive marks), OR a region digitally spliced in (mismatched compression, lighting, or font). Use this for ANY cut-and-paste forgery, physical or digital.
  digital_desktop          — Whole document fabricated in Word/Canva/Photoshop; unnatural typography or layout.
  digital_scanned          — Scanned-then-edited document; scan artifacts plus digital tampering.

Obliteration (covering original text):
  obliteration_ink         — Original text scribbled out with ink.
  obliteration_whiteout    — Correction fluid covering text.
  obliteration_pigment     — Opaque marker, paint, or other pigment covering text.

Sympathetic Ink:
  sympathetic_indented     — Indented writing visible only via raking light or carbon dusting.
  sympathetic_special      — Invisible/special ink (UV-reactive, iodine-fumed, heat-revealed, etc.). Identify the kind.

Currency:
  currency_analysis        — Banknote suspected counterfeit.

Fallbacks (use ONLY when none of the above fit):
  no_forgery_detected      — Image IS a document and looks authentic, no tampering visible.
  not_a_document           — Image is NOT a document at all (meme, selfie, photo, screenshot, joke). Describe what it actually is.
  other                    — Real forgery, but doesn't fit any of the 16 specific categories. Describe it.

OUTPUT FORMAT — return ONLY valid JSON, no prose, no markdown fences:

{
  "category": "<one code from the list above>",
  "subtype": "<specific kind, e.g. 'Bleach-based ink remover', 'UV-reactive ink', 'Selfie', 'Meme', or null if not applicable>",
  "confidence": <float between 0.0 and 1.0>,
  "explanation": "<MUST start by stating the category in plain English, then explain why you chose it based on visible cues>",
  "evidence": ["<short visible cue>", "<another cue>", ...],
  "tools_likely_used": "<what tools/methods the forger likely used, or null if not applicable / not a forgery>"
}

RULES:
1. The "explanation" field MUST begin with the human-readable category name, e.g. "Chemical Erasure detected." or "This is a selfie, not a document."
2. After naming the category, explain WHY using the visible cues.
3. For sympathetic_special, identify the specific kind of ink in subtype (UV, iodine, heat, etc.) and explain what it likely is.
4. For erasure_chemical, name the likely chemical class in subtype (bleach, acetone, etc.).
5. For not_a_document, explicitly say what the image is — selfie, meme, screenshot, joke, etc.
6. For other, describe the forgery in detail in the explanation.
7. Pick exactly ONE category. If torn between two, pick the dominant one and mention the other in explanation.
8. Output ONLY the JSON object — no preamble, no code fences, no commentary outside the JSON.
9. For digital_cut_paste: use this for BOTH physical cut-and-paste (scissors + adhesive) AND digital splicing. Do NOT fall back to "other" just because the cut-and-paste appears physical rather than digital.
10. BIAS TOWARD DETECTION: These images are submitted specifically because they are suspected forgeries. When you see even subtle anomalies — inconsistent ink density, misaligned baselines, abrupt texture changes, differing font weights, suspicious white patches, or any region that looks different from the surrounding area — classify it as the most likely forgery type. Do NOT classify as no_forgery_detected unless the document looks completely clean and consistent throughout.
11. LOW CONFIDENCE IS STILL EVIDENCE: Even if you are not certain, assign the most likely forgery category and set confidence accordingly (0.50–0.70 for uncertain). Only use no_forgery_detected when you see zero signs of manipulation.
12. COMMON SUBTLE CUES to look for: slight color/brightness difference in a region; text that looks slightly different in weight or spacing from surrounding text; a small white or discolored patch; any area where the paper texture changes; pixels that look sharper or blurrier than the rest; evidence of something being written over or under other content."""


def _client():
    """Lazy-initialize the Gemini client. Returns None if no API key is configured."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        return None


def _strip_json_fence(text: str) -> str:
    """Strip ```json ... ``` fences if Gemini wrapped its response."""
    text = text.strip()
    if text.startswith("```"):
        # remove opening fence (with optional language tag)
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        # remove closing fence
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _coerce(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and coerce Gemini's JSON into the schema we save to the DB."""
    raw_cat = (parsed.get("category") or "").strip().lower()
    if raw_cat not in CATEGORY_CODES:
        raw_cat = "other"

    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
        if confidence < 0.0:
            confidence = 0.0
        elif confidence > 1.0:
            confidence = 1.0
    except (TypeError, ValueError):
        confidence = 0.0

    evidence = parsed.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    evidence = [str(e).strip() for e in evidence if str(e).strip()]

    return {
        "category": raw_cat,
        "category_label": CATEGORY_LABELS[raw_cat],
        "subtype": (parsed.get("subtype") or "").strip() or None,
        "confidence": confidence,
        "explanation": (parsed.get("explanation") or "").strip(),
        "evidence": evidence,
        "tools_likely_used": (parsed.get("tools_likely_used") or "").strip() or None,
        "certainty_level": "HIGH" if confidence >= 0.85 else "MEDIUM" if confidence >= 0.60 else "LOW",
    }


def _fallback(reason: str) -> Dict[str, Any]:
    """Default response when Gemini is unavailable or fails."""
    return {
        "category": "other",
        "category_label": CATEGORY_LABELS["other"],
        "subtype": None,
        "confidence": 0.0,
        "explanation": f"Gemini Vision was unavailable: {reason}",
        "evidence": [],
        "tools_likely_used": None,
    }


def classify(image: Image.Image, document_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Run Gemini Vision against the document image. Returns a dict with the keys:
        category, category_label, subtype, confidence, explanation, evidence, tools_likely_used
    Always returns a dict — on any failure, falls back to the 'other' category
    with the failure reason in the explanation.

    Args:
        image: PIL Image to classify
        document_type: Optional document type (passport, check, contract, etc.) to provide context
    """
    client = _client()
    if client is None:
        return _fallback("API key not configured or google-genai not installed")

    # Re-encode to JPEG bytes for the API.
    buf = io.BytesIO()
    img_to_send = image if image.mode == "RGB" else image.convert("RGB")
    img_to_send.save(buf, format="JPEG", quality=88)
    buf.seek(0)

    # Build prompt with document type context if provided
    prompt = SYSTEM_PROMPT
    if document_type and document_type != "other":
        prompt = f"{SYSTEM_PROMPT}\n\nDOCUMENT TYPE HINT: The user indicates this is a {document_type.replace('_', ' ')}. Use this as context to guide your classification — certain forgery types are more likely for this document type."

    try:
        from google.genai import types as genai_types
        response = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[
                prompt,
                genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        text = response.text or ""
    except Exception as exc:  # noqa: BLE001
        return _fallback(f"API call failed: {exc}")

    text = _strip_json_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object inside a noisy response.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return _fallback("response was not valid JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return _fallback("response was not valid JSON")

    if not isinstance(parsed, dict):
        return _fallback("response was not a JSON object")

    return _coerce(parsed)
