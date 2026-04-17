"""
Document analysis routes.
"""

import io
import json
import random
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from PIL import Image

from ..auth import get_current_user
from ..database import get_db
from ..models import User, Scan
from ..config import FREE_SCANS_PER_MONTH, BASIC_SCANS_PER_MONTH, PRO_SCANS_PER_MONTH
from ..forgery.detector import (
    CLASS_LABELS, NAME_TO_CLASS, VALID_CATEGORIES, TRAINING_STATUS,
    run_yolo_inference, determine_verdict, get_training_warning,
)
from ..forgery.llm import get_llm_explanation

router = APIRouter(prefix="/api", tags=["analysis"])


PLAN_LIMITS = {
    "free": FREE_SCANS_PER_MONTH,
    "basic": BASIC_SCANS_PER_MONTH,
    "pro": PRO_SCANS_PER_MONTH,
}


def generate_scan_id() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"FG-{ts}-{rnd}"


def check_scan_limit(user: User):
    """Reset monthly counter if needed, then enforce plan limit."""
    now = datetime.utcnow()
    if user.scan_reset_date and (now - user.scan_reset_date).days >= 30:
        user.scans_this_month = 0
        user.scan_reset_date = now

    limit = PLAN_LIMITS.get(user.plan, FREE_SCANS_PER_MONTH)
    if user.scans_this_month >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly scan limit reached ({limit} scans on {user.plan} plan). Upgrade for more.",
        )


@router.get("/categories")
def get_categories():
    categories = {}
    for class_id, info in CLASS_LABELS.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        is_trained = TRAINING_STATUS.get(info["name"], False)
        categories[cat].append({
            "class_id": class_id,
            "api_key": info["name"],
            "title": info["title"],
            "color": info["color"],
            "is_trained": is_trained,
            "training_note": "Ready" if is_trained else "Needs training data",
        })
    trained_count = sum(1 for v in TRAINING_STATUS.values() if v)
    total_count = len(TRAINING_STATUS)
    return {
        "categories": categories,
        "total_classes": len(CLASS_LABELS),
        "training_summary": {
            "trained": trained_count,
            "untrained": total_count - trained_count,
            "total": total_count,
            "percentage_ready": f"{(trained_count / total_count) * 100:.0f}%",
        },
    }


@router.post("/analyze")
def analyze_document(
    imageFile: UploadFile = File(...),
    category: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate category
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Options: {VALID_CATEGORIES}")

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

    # Run YOLO
    detections = run_yolo_inference(image, category)
    verdict, confidence = determine_verdict(detections)
    llm_explanation = get_llm_explanation(detections, category)
    training_warning = get_training_warning(category, detections)
    category_trained = TRAINING_STATUS.get(category, False) if category else False

    # Build annotations
    annotations = [
        {
            "id": d["id"],
            "type": "bounding_box",
            "coordinates": d["coordinates"],
            "color": d["color"],
            "title": d["title"],
            "confidence": d["confidence"],
        }
        for d in detections
    ]

    scan_id = generate_scan_id()

    # Save to database
    scan = Scan(
        scan_id=scan_id,
        user_id=current_user.id,
        filename=imageFile.filename or "unknown",
        category_analyzed=category,
        verdict=verdict,
        confidence_score=confidence,
        llm_explanation=llm_explanation,
        annotations_json=json.dumps(annotations),
        image_width=width,
        image_height=height,
        training_warning=training_warning,
    )
    db.add(scan)
    current_user.scans_this_month += 1
    db.commit()

    return {
        "scan_id": scan_id,
        "category_analyzed": category,
        "verdict": verdict,
        "confidence_score": confidence,
        "llm_explanation": llm_explanation,
        "annotations": annotations,
        "original_image_dimensions": {"width": width, "height": height},
        "timestamp": datetime.now().isoformat(),
        "training_warning": training_warning,
        "category_trained": category_trained,
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
        "annotations": json.loads(scan.annotations_json) if scan.annotations_json else [],
        "image_width": scan.image_width,
        "image_height": scan.image_height,
        "training_warning": scan.training_warning,
        "created_at": scan.created_at.isoformat() if scan.created_at else "",
    }
