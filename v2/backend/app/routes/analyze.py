"""Document analysis routes.

Frontend uploads an image with a Firebase ID token. We:
  1. Verify the token + look up the user's profile in Firestore.
  2. Enforce plan-based scan limits and tier permissions.
  3. Run the document gate, then Gemini Vision (and optionally LLaVA).
  4. Persist the original image to Firebase Storage.
  5. Write a `scans/{scan_id}` Firestore doc the frontend can read back.
  6. Increment the user's scans_this_month.
"""

from __future__ import annotations

import io
import json
import random
import string
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image

from ..auth import get_current_user
from ..config import LLM_PLANS, PLAN_LIMITS, UNLIMITED
from ..firebase_admin_init import bucket, db
from ..forgery import llava_client
from ..forgery.document_gate import check_is_document
from ..forgery.document_types import DOCUMENT_TYPES, get_document_types_response
from ..forgery.gemini_vision import (
    CATEGORY_CODES,
    CATEGORY_LABELS,
    classify as gemini_classify,
)
from ..forgery.llm import get_llm_explanation
from ..forgery.model_tiers import (
    ALL_TIERS,
    TIER_ANALYST,
    TIER_AVAILABLE,
    TIER_DETECTIVE,
    TIER_META,
    TIER_SHERLOCK,
    get_tiers_response,
    is_tier_allowed,
)

router = APIRouter(prefix="/api", tags=["analysis"])

_FORGERY_CATS = {
    c for c in CATEGORY_CODES
    if c not in {"no_forgery_detected", "not_a_document", "other"}
}


def _now():
    return datetime.now(timezone.utc)


def _generate_scan_id() -> str:
    ts = _now().strftime("%Y%m%d")
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"RV-{ts}-{rnd}"


def _check_scan_limit(user: dict) -> None:
    plan = user.get("plan", "free")
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    if limit == UNLIMITED:
        return
    used = user.get("scans_this_month", 0)
    # Roll the counter once a month
    reset = user.get("scan_reset_date")
    if reset and (_now() - _coerce_dt(reset)).days >= 30:
        used = 0
        db().collection("users").document(user["uid"]).update({
            "scans_this_month": 0,
            "scan_reset_date": _now(),
        })
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly scan limit reached ({limit} on the {plan} plan). "
                   f"Upgrade for unlimited scans.",
        )


def _coerce_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    return _now()


def _verdict_from_gemini(gemini: dict) -> tuple[str, float]:
    cat = gemini["category"]
    conf = gemini["confidence"]
    if cat == "not_a_document":
        return "not_a_document", conf
    if cat == "no_forgery_detected":
        return "no_forgery_detected", conf
    if cat in _FORGERY_CATS:
        if conf >= 0.70:
            return "forged", conf
        if conf >= 0.50:
            return "suspicious", conf
        return "no_forgery_detected", conf
    if conf >= 0.70:
        return "forged", conf
    if conf >= 0.50:
        return "suspicious", conf
    return "no_forgery_detected", conf


def _upload_to_storage(image: Image.Image, uid: str, scan_id: str) -> Optional[str]:
    """Upload the JPEG to `users/{uid}/scans/{scan_id}.jpg` and return the storage path."""
    try:
        b = bucket()
    except Exception as exc:
        print(f"⚠️  Storage bucket not configured ({exc}); image will not be saved.")
        return None
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    blob = b.blob(f"users/{uid}/scans/{scan_id}.jpg")
    blob.upload_from_file(buf, content_type="image/jpeg")
    return blob.name


@router.get("/document-types")
def get_document_types():
    return get_document_types_response()


@router.get("/tiers")
def get_model_tiers(current_user: dict = Depends(get_current_user)):
    return get_tiers_response(user_plan=current_user.get("plan", "free"))


@router.get("/about")
def get_about_info():
    return {
        "verdict_meaning": {
            "forged": "High-confidence indicators matching known forgery patterns. Manual review still recommended.",
            "suspicious": "Anomalies present but below the strong-evidence threshold. Treat as inconclusive.",
            "no_forgery_detected": "No forgery signals detected above threshold. Absence of evidence is not proof of authenticity.",
            "not_a_document": "The upload doesn't appear to be a document. Skipped without scoring.",
        },
        "limitations": [
            "Gemini Vision is a general-purpose model — subtle, domain-specific forgeries may be missed.",
            "Lighting, camera angle, focus, and resolution materially affect results.",
            "Revelator is a screening tool. Findings are not by themselves admissible forensic evidence.",
        ],
        "model_tiers": list(TIER_META.values()),
    }


@router.post("/analyze")
def analyze_document(
    imageFile: UploadFile = File(...),
    category: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    model_tier: Optional[str] = Form(None),
    suspicion_reason: Optional[str] = Form(None),
    area_of_concern: Optional[str] = Form(None),
    image_source: Optional[str] = Form(None),
    is_forged_belief: Optional[str] = Form(None),
    shot_type: Optional[str] = Form(None),
    lighting: Optional[str] = Form(None),
    physical_clues: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    user_plan = current_user.get("plan", "free")
    uid = current_user["uid"]

    # ── Tier validation ──────────────────────────────────────────
    tier = (model_tier or TIER_ANALYST).lower()
    if tier not in ALL_TIERS:
        raise HTTPException(400, f"Invalid model_tier. Options: {ALL_TIERS}")
    if not is_tier_allowed(user_plan, tier):
        raise HTTPException(
            403,
            f"The {TIER_META[tier]['name']} tier requires a higher plan. "
            f"Upgrade to {TIER_META[tier]['plans'][0]} or above.",
        )

    _check_scan_limit(current_user)

    # ── Read image ───────────────────────────────────────────────
    try:
        image_data = imageFile.file.read()
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        width, height = image.size
    except Exception as e:
        raise HTTPException(400, f"Invalid image: {e}")

    # ── Document gate (skip quota for non-documents) ─────────────
    is_doc, gate_reason = check_is_document(image)
    if not is_doc:
        return {
            "scan_id": None,
            "document_type": document_type,
            "verdict": "not_a_document",
            "confidence_score": 0.0,
            "llm_explanation": gate_reason or "This does not appear to be a document.",
            "llm_locked": user_plan not in LLM_PLANS,
            "llm_required_plan": "premium",
            "annotations": [],
            "original_image_dimensions": {"width": width, "height": height},
            "timestamp": _now().isoformat(),
            "detected_category": "not_a_document",
            "detected_category_label": "Not a Document",
        }

    # ── Run Gemini ───────────────────────────────────────────────
    gemini = gemini_classify(
        image,
        document_type=document_type,
        suspicion_reason=suspicion_reason,
        area_of_concern=area_of_concern,
        image_source=image_source,
        is_forged_belief=is_forged_belief,
        shot_type=shot_type,
        lighting=lighting,
        physical_clues=physical_clues,
    )

    if gemini.get("_unavailable"):
        raise HTTPException(503, "Gemini Vision is temporarily unavailable. Please try again in a moment.")

    # ── Optional LLaVA ensemble (Detective / Sherlock) ───────────
    llava_result = None
    tier_used = TIER_ANALYST
    if tier == TIER_DETECTIVE and TIER_AVAILABLE[TIER_DETECTIVE]:
        llava_result = llava_client.classify_detective(image, document_type=document_type)
        if llava_result is not None:
            tier_used = TIER_DETECTIVE
    elif tier == TIER_SHERLOCK and TIER_AVAILABLE[TIER_SHERLOCK]:
        llava_result = llava_client.classify_sherlock(image, document_type=document_type)
        if llava_result is not None:
            tier_used = TIER_SHERLOCK

    if llava_result is not None:
        agreement = llava_result["category"] == gemini["category"]
        avg_conf = (llava_result["confidence"] + gemini["confidence"]) / 2
        gemini = {
            **gemini,
            "category": llava_result["category"],
            "category_label": llava_result.get("category_label", gemini["category_label"]),
            "subtype": llava_result.get("subtype", gemini["subtype"]),
            "confidence": avg_conf if agreement else min(llava_result["confidence"], gemini["confidence"]),
            "explanation": f"{llava_result['explanation']}\n\nVerification: {gemini['explanation']}",
            "evidence": (llava_result.get("evidence") or []) + gemini.get("evidence", []),
            "tools_likely_used": llava_result.get("tools_likely_used", gemini["tools_likely_used"]),
            "certainty_level": (
                "HIGH" if agreement and avg_conf >= 0.85
                else "MEDIUM" if agreement and avg_conf >= 0.60
                else "LOW"
            ),
        }

    verdict, confidence = _verdict_from_gemini(gemini)

    # ── LLM explanation (premium only) ───────────────────────────
    llm_explanation = (
        get_llm_explanation(gemini, image=image)
        if user_plan in LLM_PLANS else None
    )

    scan_id = _generate_scan_id()
    image_path = _upload_to_storage(image, uid, scan_id)

    # ── Persist to Firestore ─────────────────────────────────────
    scan_doc = {
        "scan_id": scan_id,
        "user_id": uid,
        "filename": imageFile.filename or "unknown",
        "category_analyzed": category,
        "document_type": document_type,
        "verdict": verdict,
        "confidence_score": confidence,
        "llm_explanation": llm_explanation,
        "image_width": width,
        "image_height": height,
        "image_path": image_path,
        "detected_category": gemini["category"],
        "detected_category_label": gemini["category_label"],
        "detected_subtype": gemini.get("subtype"),
        "category_explanation": gemini["explanation"],
        "tools_likely_used": gemini.get("tools_likely_used"),
        "category_confidence": gemini["confidence"],
        "category_evidence": gemini.get("evidence") or [],
        "reasoning_steps": gemini.get("reasoning_steps") or [],
        "anomaly_location": gemini.get("anomaly_location"),
        "certainty_level": gemini.get("certainty_level"),
        "model_tier_requested": tier,
        "model_tier_used": tier_used,
        "model_tier_fallback": tier != tier_used,
        "created_at": _now(),
    }
    db().collection("scans").document(scan_id).set(scan_doc)

    # Increment user's monthly scan counter atomically
    from firebase_admin import firestore as _fs  # local to avoid module-level coupling
    db().collection("users").document(uid).update({
        "scans_this_month": _fs.Increment(1),
        "updated_at": _now(),
    })

    return {
        **{k: v for k, v in scan_doc.items() if k != "created_at"},
        "timestamp": _now().isoformat(),
        "llm_locked": user_plan not in LLM_PLANS,
        "llm_required_plan": "premium",
        "annotations": [],
        "original_image_dimensions": {"width": width, "height": height},
    }


@router.get("/health")
def health():
    return {"status": "ok"}
