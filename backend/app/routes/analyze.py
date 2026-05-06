"""
Document analysis routes.
"""

import io
import json
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from PIL import Image

from ..auth import get_current_user, get_user_from_token
from ..database import get_db
from ..models import User, Scan
from ..config import (
    FREE_SCANS_PER_MONTH, PRO_SCANS_PER_MONTH, PREMIUM_SCANS_PER_MONTH,
    UNLIMITED, LLM_PLANS, UPLOAD_DIR,
)
from ..forgery.detector import (
    CLASS_LABELS, NAME_TO_CLASS, VALID_CATEGORIES, TRAINING_STATUS,
    DATASET_COUNTS, LIMITED_DATA_THRESHOLD, MODELS_DIR,
    run_yolo_inference, determine_verdict, get_training_warning,
    _count_dataset_images,
)
from ..forgery.llm import get_llm_explanation
from ..forgery.document_gate import check_is_document
from ..forgery.gemini_vision import classify as gemini_classify
from ..forgery.document_types import get_document_types_response
from ..forgery.model_tiers import (
    TIER_ANALYST, TIER_DETECTIVE, TIER_SHERLOCK, ALL_TIERS,
    TIER_AVAILABLE, TIER_META, get_tiers_response, is_tier_allowed,
)
from ..forgery import llava_client

router = APIRouter(prefix="/api", tags=["analysis"])


PLAN_LIMITS = {
    "free": FREE_SCANS_PER_MONTH,
    "pro": PRO_SCANS_PER_MONTH,
    "premium": PREMIUM_SCANS_PER_MONTH,
}


def generate_scan_id() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"RV-{ts}-{rnd}"


def check_scan_limit(user: User):
    """Reset monthly counter if needed, then enforce plan limit. UNLIMITED (-1) skips the cap."""
    now = datetime.utcnow()
    if user.scan_reset_date and (now - user.scan_reset_date).days >= 30:
        user.scans_this_month = 0
        user.scan_reset_date = now

    limit = PLAN_LIMITS.get(user.plan, FREE_SCANS_PER_MONTH)
    if limit == UNLIMITED:
        return
    if user.scans_this_month >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly scan limit reached ({limit} scans on the {user.plan} plan). Upgrade for unlimited scans.",
        )


@router.get("/document-types")
def get_document_types():
    """Get list of document types for scan context selection."""
    return get_document_types_response()


@router.get("/tiers")
def get_model_tiers(current_user: User = Depends(get_current_user)):
    """Return model tier metadata with `unlocked` flags for the current user's plan."""
    return get_tiers_response(user_plan=current_user.plan)


@router.get("/categories")
def get_categories():
    _count_dataset_images()  # refresh counts from disk on every call
    categories = {}
    category_totals = {}
    for class_id, info in CLASS_LABELS.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
            category_totals[cat] = 0
        is_trained = TRAINING_STATUS.get(info["name"], False)
        count = DATASET_COUNTS.get(info["name"], 0)
        category_totals[cat] += count
        categories[cat].append({
            "class_id": class_id,
            "api_key": info["name"],
            "title": info["title"],
            "color": info["color"],
            "is_trained": is_trained,
            "training_note": "Ready" if is_trained else "Needs training data",
            "dataset_count": count,
            "limited_data": count < LIMITED_DATA_THRESHOLD,
        })
    trained_count = sum(1 for v in TRAINING_STATUS.values() if v)
    total_count = len(TRAINING_STATUS)
    return {
        "categories": categories,
        "category_dataset_totals": category_totals,
        "total_classes": len(CLASS_LABELS),
        "limited_data_threshold": LIMITED_DATA_THRESHOLD,
        "training_summary": {
            "trained": trained_count,
            "untrained": total_count - trained_count,
            "total": total_count,
            "percentage_ready": f"{(trained_count / total_count) * 100:.0f}%",
            "total_dataset_images": sum(DATASET_COUNTS.values()),
        },
    }


@router.get("/samples/{category_id}")
def get_samples(category_id: str):
    """List available sample images from a category's training dataset."""
    if category_id not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category_id}")

    category_dir = MODELS_DIR / category_id
    if not category_dir.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found for {category_id}")

    samples = []

    # Collect images from train, valid, test folders
    for split in ["train", "valid", "test"]:
        split_dir = category_dir / split / "images"
        if split_dir.exists():
            # Get all image files (jpg, png, etc.)
            image_files = sorted([
                f.name for f in split_dir.glob("*")
                if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png"]
            ])
            # Randomize and limit to 5 per split for display
            if image_files:
                selected = random.sample(image_files, min(5, len(image_files)))
                for filename in selected:
                    samples.append({
                        "filename": filename,
                        "split": split,
                        "url": f"/api/samples/{category_id}/image/{split}/{filename}"
                    })

    return {
        "category_id": category_id,
        "total_available": len(samples),
        "samples": samples,
    }


@router.get("/samples/{category_id}/image/{split}/{filename}")
def get_sample_image(category_id: str, split: str, filename: str):
    """Serve a sample image from the training dataset."""
    if category_id not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")

    if split not in ["train", "valid", "test"]:
        raise HTTPException(status_code=400, detail="Invalid split")

    # Guard against path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = (MODELS_DIR / category_id / split / "images" / filename).resolve()

    # Verify the file is within the expected directory
    expected_dir = (MODELS_DIR / category_id / split / "images").resolve()
    if not str(file_path).startswith(str(expected_dir)) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(file_path)


@router.get("/about")
def get_about_info():
    """Public endpoint: pipeline metadata + per-class dataset transparency for the About page."""
    by_category = {}
    for class_id, info in CLASS_LABELS.items():
        cat = info["category"]
        if cat not in by_category:
            by_category[cat] = {"classes": [], "total_images": 0, "trained_classes": 0}
        count = DATASET_COUNTS.get(info["name"], 0)
        is_trained = TRAINING_STATUS.get(info["name"], False)
        by_category[cat]["classes"].append({
            "title": info["title"],
            "api_key": info["name"],
            "is_trained": is_trained,
            "dataset_count": count,
            "limited_data": count < LIMITED_DATA_THRESHOLD,
        })
        by_category[cat]["total_images"] += count
        if is_trained:
            by_category[cat]["trained_classes"] += 1

    return {
        "pipeline": [
            {"step": 1, "name": "Upload", "detail": "Image arrives over HTTPS, normalized to RGB."},
            {"step": 2, "name": "Inference", "detail": "A YOLO object-detection model trained for the chosen forgery category scans the image."},
            {"step": 3, "name": "Aggregation", "detail": "Detected regions are scored; verdict is forged / suspicious / no_forgery_detected based on confidence and detection count."},
            {"step": 4, "name": "Explanation (optional)", "detail": "An LLM generates a plain-language summary of the findings, available on the LLM-tier plan."},
            {"step": 5, "name": "History", "detail": "The image and findings are stored against your account so you can revisit any scan."},
        ],
        "verdict_meaning": {
            "forged":               "High-confidence detections matching known forgery patterns. Manual review still recommended.",
            "suspicious":           "Anomalies present but below the strong-evidence threshold. Treat as inconclusive.",
            "no_forgery_detected":  "No matches above the detection threshold. Absence of evidence is not proof of authenticity.",
            "not_a_document":       "The upload doesn't appear to be a paper document, ID, certificate, receipt, or similar. Skipped without scoring.",
        },
        "limitations": [
            "Detection quality is bounded by training-set size and diversity. Classes with few samples will miss subtle cases.",
            "Lighting, camera angle, focus, and resolution materially affect results. Photograph documents flat with even light.",
            "Photographed prints of digital forgeries may produce different signals than the original digital file.",
            "The detector is calibrated for document examination; out-of-domain images (memes, photos of objects) yield meaningless verdicts.",
            "Revelator is a screening tool. Findings are not, by themselves, admissible forensic evidence.",
        ],
        "categories": by_category,
        "totals": {
            "classes": len(CLASS_LABELS),
            "trained_classes": sum(1 for v in TRAINING_STATUS.values() if v),
            "total_dataset_images": sum(DATASET_COUNTS.values()),
            "limited_data_threshold": LIMITED_DATA_THRESHOLD,
        },
        "model_tiers": list(TIER_META.values()),
    }


@router.post("/analyze")
def analyze_document(
    imageFile: UploadFile = File(...),
    category: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    model_tier: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate category
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Options: {VALID_CATEGORIES}")

    # Resolve & validate model tier (default to Analyst — always available)
    tier = (model_tier or TIER_ANALYST).lower()
    if tier not in ALL_TIERS:
        raise HTTPException(status_code=400, detail=f"Invalid model_tier. Options: {ALL_TIERS}")
    if not is_tier_allowed(current_user.plan, tier):
        raise HTTPException(
            status_code=403,
            detail=f"The {TIER_META[tier]['name']} tier requires a higher plan. "
                   f"Upgrade to {TIER_META[tier]['plans'][0]} or above.",
        )

    # Check scan limit
    check_scan_limit(current_user)

    # Read image
    try:
        image_data = imageFile.file.read()
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        width, height = image.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Document gate — short-circuit before quota and DB write so users aren't
    # charged scans for non-document uploads.
    is_doc, gate_reason = check_is_document(image)
    if not is_doc:
        return {
            "scan_id": None,
            "category_analyzed": category,
            "verdict": "not_a_document",
            "confidence_score": 0.0,
            "llm_explanation": gate_reason or (
                "This does not appear to be a document. Please upload a paper "
                "document, ID, certificate, receipt, or similar."
            ),
            "llm_locked": False,
            "llm_required_plan": "pro",
            "annotations": [],
            "original_image_dimensions": {"width": width, "height": height},
            "timestamp": datetime.now().isoformat(),
            "training_warning": None,
            "category_trained": False,
        }

    # Run YOLO
    detections = run_yolo_inference(image, category)
    verdict, confidence = determine_verdict(detections)
    # LLM explanation is a paid feature — only generated for plans in LLM_PLANS.
    llm_explanation = (
        get_llm_explanation(detections, category, image=image)
        if current_user.plan in LLM_PLANS
        else None
    )
    training_warning = get_training_warning(category, detections)
    category_trained = TRAINING_STATUS.get(category, False) if category else False

    # ── Tiered inference ─────────────────────────────────────────────────────
    # Analyst:   Gemini only (always runs; baseline).
    # Detective: LLaVA-100 + Gemini verification. Falls back to Analyst if
    #            LLaVA stub isn't wired up.
    # Sherlock:  LLaVA-500 + document-type aware + Gemini verification. Same
    #            fallback behavior as Detective until deployed.
    gemini = gemini_classify(image, document_type=document_type)
    llava_result = None
    tier_used = TIER_ANALYST  # what actually ran, may differ from requested

    if tier == TIER_DETECTIVE and TIER_AVAILABLE[TIER_DETECTIVE]:
        llava_result = llava_client.classify_detective(image, document_type=document_type)
        if llava_result is not None:
            tier_used = TIER_DETECTIVE
    elif tier == TIER_SHERLOCK and TIER_AVAILABLE[TIER_SHERLOCK]:
        llava_result = llava_client.classify_sherlock(image, document_type=document_type)
        if llava_result is not None:
            tier_used = TIER_SHERLOCK

    # When a LLaVA tier returned a result, prefer its category but keep Gemini's
    # explanation/evidence as the verification layer. Confidence is averaged so
    # disagreement lowers the score automatically.
    if llava_result is not None:
        agreement = llava_result["category"] == gemini["category"]
        avg_conf = (llava_result["confidence"] + gemini["confidence"]) / 2
        gemini = {
            **gemini,
            "category": llava_result["category"],
            "category_label": llava_result.get("category_label", gemini["category_label"]),
            "subtype": llava_result.get("subtype", gemini["subtype"]),
            "confidence": avg_conf if agreement else min(llava_result["confidence"], gemini["confidence"]),
            "explanation": (
                f"{llava_result['explanation']}\n\n"
                f"Verification: {gemini['explanation']}"
            ),
            "evidence": (llava_result.get("evidence") or []) + gemini.get("evidence", []),
            "tools_likely_used": llava_result.get("tools_likely_used", gemini["tools_likely_used"]),
            "certainty_level": "HIGH" if agreement and avg_conf >= 0.85 else (
                "MEDIUM" if agreement and avg_conf >= 0.60 else "LOW"
            ),
        }

    # Filter out base COCO model detections — they are not forgery evidence.
    # The _default model (yolov8n.pt) is a COCO general detector used as a
    # placeholder when no category-specific YOLO weights exist. Its detections
    # mean nothing in a forgery context, so we strip them before verdict logic.
    real_detections = [d for d in detections if d.get("model_used") != "_default"]
    if real_detections != detections:
        verdict, confidence = determine_verdict(real_detections)

    from ..forgery.gemini_vision import CATEGORY_CODES
    _FORGERY_CATS = {c for c in CATEGORY_CODES if c not in {"no_forgery_detected", "not_a_document", "other"}}

    if gemini["category"] in _FORGERY_CATS:
        # Gemini identified a specific forgery type — let it drive the verdict.
        # Threshold: ≥0.70 → forged, 0.50–0.69 → suspicious. Below 0.50 we
        # trust YOLO's assessment (or keep the existing verdict).
        g_conf = gemini["confidence"]
        if g_conf >= 0.70:
            verdict = "forged"
            confidence = g_conf
        elif g_conf >= 0.50:
            if verdict == "no_forgery_detected":
                verdict = "suspicious"
                confidence = g_conf
    elif gemini["category"] == "not_a_document" and not real_detections:
        verdict = "not_a_document"
    elif gemini["category"] == "no_forgery_detected" and not real_detections:
        verdict = "no_forgery_detected"

    # Build annotations from real (non-COCO) detections only.
    annotations = [
        {
            "id": d["id"],
            "type": "bounding_box",
            "coordinates": d["coordinates"],
            "color": d["color"],
            "title": d["title"],
            "confidence": d["confidence"],
        }
        for d in real_detections
    ]

    scan_id = generate_scan_id()

    # Persist the uploaded image to disk under uploads/<user_id>/<scan_id>.jpg.
    # Stored as JPEG to normalize format; original filename is kept in DB for display.
    user_dir = UPLOAD_DIR / current_user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    saved_path = user_dir / f"{scan_id}.jpg"
    try:
        image.save(saved_path, format="JPEG", quality=88)
        image_path = str(saved_path.relative_to(UPLOAD_DIR))
    except Exception:
        image_path = None

    # Save to database
    scan = Scan(
        scan_id=scan_id,
        user_id=current_user.id,
        filename=imageFile.filename or "unknown",
        category_analyzed=category,
        document_type=document_type,
        verdict=verdict,
        confidence_score=confidence,
        llm_explanation=llm_explanation,
        annotations_json=json.dumps(annotations),
        image_width=width,
        image_height=height,
        image_path=image_path,
        training_warning=training_warning,
        detected_category=gemini["category"],
        detected_subtype=gemini["subtype"],
        category_explanation=gemini["explanation"],
        tools_likely_used=gemini["tools_likely_used"],
        category_confidence=gemini["confidence"],
        category_evidence=json.dumps(gemini["evidence"]),
    )
    db.add(scan)
    current_user.scans_this_month += 1
    db.commit()

    return {
        "scan_id": scan_id,
        "category_analyzed": category,
        "document_type": document_type,
        "verdict": verdict,
        "confidence_score": confidence,
        "llm_explanation": llm_explanation,
        "llm_locked": current_user.plan not in LLM_PLANS,
        "llm_required_plan": "pro",
        "annotations": annotations,
        "original_image_dimensions": {"width": width, "height": height},
        "timestamp": datetime.now().isoformat(),
        "training_warning": training_warning,
        "category_trained": category_trained,
        "detected_category": gemini["category"],
        "detected_category_label": gemini["category_label"],
        "detected_subtype": gemini["subtype"],
        "category_explanation": gemini["explanation"],
        "category_evidence": gemini["evidence"],
        "tools_likely_used": gemini["tools_likely_used"],
        "category_confidence": gemini["confidence"],
        "certainty_level": gemini.get("certainty_level"),
        "model_tier_requested": tier,
        "model_tier_used": tier_used,
        "model_tier_fallback": tier != tier_used,
    }


@router.post("/preliminary")
def preliminary_scan(
    imageFile: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    try:
        image_data = imageFile.file.read()
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    detections = run_yolo_inference(image, None)
    category_scores = {}
    for det in detections:
        cat = det["category"]
        if cat not in category_scores:
            category_scores[cat] = {"count": 0, "max_confidence": 0}
        category_scores[cat]["count"] += 1
        category_scores[cat]["max_confidence"] = max(category_scores[cat]["max_confidence"], det["confidence"])

    suggestions = sorted(
        [{"category": c, "confidence": s["max_confidence"], "detections": s["count"]}
         for c, s in category_scores.items()],
        key=lambda x: x["confidence"], reverse=True,
    )
    return {"suggestions": suggestions[:3], "total_detections": len(detections)}


@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    scans = (
        db.query(Scan)
        .filter(Scan.user_id == current_user.id)
        .order_by(Scan.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(Scan).filter(Scan.user_id == current_user.id).count()
    return {
        "scans": [
            {
                "id": s.id,
                "scan_id": s.scan_id,
                "filename": s.filename,
                "category_analyzed": s.category_analyzed,
                "verdict": s.verdict,
                "confidence_score": s.confidence_score,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "has_image": bool(s.image_path),
                "has_llm_explanation": bool(s.llm_explanation),
                "detected_category": s.detected_category,
                "category_confidence": s.category_confidence,
                "document_type": s.document_type,
            }
            for s in scans
        ],
        "total": total,
    }


@router.get("/history/{scan_id}")
def get_scan_detail(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.user_id == current_user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {
        "id": scan.id,
        "scan_id": scan.scan_id,
        "filename": scan.filename,
        "category_analyzed": scan.category_analyzed,
        "verdict": scan.verdict,
        "confidence_score": scan.confidence_score,
        "llm_explanation": scan.llm_explanation,
        "llm_locked": (not scan.llm_explanation) and (current_user.plan not in LLM_PLANS),
        "llm_required_plan": "pro",
        "annotations": json.loads(scan.annotations_json) if scan.annotations_json else [],
        "image_width": scan.image_width,
        "image_height": scan.image_height,
        "has_image": bool(scan.image_path),
        "training_warning": scan.training_warning,
        "detected_category": scan.detected_category,
        "detected_category_label": _gemini_label(scan.detected_category),
        "detected_subtype": scan.detected_subtype,
        "category_explanation": scan.category_explanation,
        "tools_likely_used": scan.tools_likely_used,
        "category_confidence": scan.category_confidence,
        "category_evidence": json.loads(scan.category_evidence) if scan.category_evidence else [],
        "certainty_level": (
            "HIGH" if (scan.category_confidence or 0) >= 0.85
            else "MEDIUM" if (scan.category_confidence or 0) >= 0.60
            else "LOW"
        ) if scan.category_confidence else None,
        "document_type": scan.document_type,
        "document_type_label": _document_type_label(scan.document_type),
        "created_at": scan.created_at.isoformat() if scan.created_at else "",
    }


def _gemini_label(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    from ..forgery.gemini_vision import CATEGORY_LABELS
    return CATEGORY_LABELS.get(code)


def _document_type_label(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    from ..forgery.document_types import DOCUMENT_TYPES
    return DOCUMENT_TYPES.get(key, {}).get("title")


@router.get("/history/{scan_id}/image")
def get_scan_image(
    scan_id: str,
    token: str = Query(..., description="Access token (query param so <img src> works)"),
    db: Session = Depends(get_db),
):
    """Serve the uploaded image for a scan. Owner-only."""
    user = get_user_from_token(token, db)
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.user_id == user.id).first()
    if not scan or not scan.image_path:
        raise HTTPException(status_code=404, detail="Image not found")

    # Resolve and guard against path traversal: ensure the resolved file is inside UPLOAD_DIR.
    file_path = (UPLOAD_DIR / scan.image_path).resolve()
    if not str(file_path).startswith(str(UPLOAD_DIR.resolve())) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(file_path, media_type="image/jpeg")
