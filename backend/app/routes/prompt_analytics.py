"""Live prompt, model, overlap, and specimen analytics."""

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request

from ..config import APP_VERSION, GEMINI_VISION_MODEL
from ..forgery.gemini_vision import (
    CRITIQUE_PROMPT_TEMPLATE,
    DETAILED_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    TRIAGE_PROMPT,
    _model_chain,
    analyze_prompts,
)
from ..operations import record_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["prompt-analytics"])

ACCURACY_FILE = Path(__file__).resolve().parent.parent / "data" / "specimen_accuracy.json"
SPECIMEN_DIR = Path(__file__).resolve().parents[3] / "SPECIMEN PICTURES"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPECIMEN_LABELS = {"forged", "genuine", "unsorted"}


@lru_cache(maxsize=1)
def _specimen_inventory() -> dict:
    if not SPECIMEN_DIR.is_dir():
        return {
            "status": "not_available",
            "source": SPECIMEN_DIR.name,
            "total_images": 0,
            "folder_count": 0,
            "labels": {label: 0 for label in sorted(SPECIMEN_LABELS)},
            "folders": [],
        }

    folders = []
    label_totals = {label: 0 for label in sorted(SPECIMEN_LABELS)}
    total_images = 0
    specimen_folders = sorted(path for path in SPECIMEN_DIR.iterdir() if path.is_dir())

    for folder in specimen_folders:
        counts = {label: 0 for label in sorted(SPECIMEN_LABELS)}
        subfolders: dict[str, int] = {}
        folder_total = 0
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            folder_total += 1
            relative_parts = path.relative_to(folder).parts[:-1]
            labels = [part.casefold() for part in relative_parts]
            label = next((name for name in labels if name in SPECIMEN_LABELS), None)
            if label:
                counts[label] += 1
                label_totals[label] += 1
            subfolder = next(
                (part for part in relative_parts if part.casefold() not in SPECIMEN_LABELS),
                None,
            )
            if subfolder:
                subfolders[subfolder] = subfolders.get(subfolder, 0) + 1

        total_images += folder_total
        folders.append({
            "name": folder.name,
            "total_images": folder_total,
            "labels": counts,
            "subfolders": [
                {"name": name, "total_images": count}
                for name, count in sorted(subfolders.items())
            ],
        })

    return {
        "status": "ok",
        "source": SPECIMEN_DIR.name,
        "total_images": total_images,
        "folder_count": len(folders),
        "labels": label_totals,
        "folders": folders,
    }


@router.get("/prompt-analysis/accuracy")
def get_system_accuracy(request: Request):
    """Read the most recent specimen-evaluation report."""
    if not ACCURACY_FILE.exists():
        return {
            "status": "no_data",
            "message": "No evaluation run yet. Run: cd backend && python evaluate_specimens.py --sample 3",
        }
    try:
        data = json.loads(ACCURACY_FILE.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Could not read specimen accuracy report")
        record_event(
            "prompt_analytics_failure",
            f"Could not read specimen accuracy report ({type(exc).__name__})",
            severity="error",
            request_id=getattr(request.state, "request_id", None),
            path="/api/prompt-analysis/accuracy",
            status_code=500,
        )
        return {"status": "error", "message": "Could not read the specimen accuracy report."}


@router.get("/prompt-analysis")
def get_prompt_analysis():
    """Build analytics from the current prompt, model configuration, and specimens."""
    data = analyze_prompts()
    data["rules"] = [
        {
            "title": (title or "Rule").strip() + ":",
            "text": text.strip(),
        }
        for rule in data["rules"]
        for title, separator, text in [rule.partition(":")]
    ]

    prompt_fingerprint = hashlib.sha256(
        "\0".join((
            SYSTEM_PROMPT,
            TRIAGE_PROMPT,
            DETAILED_PROMPT_TEMPLATE,
            CRITIQUE_PROMPT_TEMPLATE,
        )).encode("utf-8")
    ).hexdigest()
    data["vision"] = {
        "app_version": APP_VERSION,
        "model": GEMINI_VISION_MODEL,
        "model_fallback_chain": _model_chain(),
        "prompt_version": prompt_fingerprint[:12],
        "prompt_sha256": prompt_fingerprint,
    }
    data["specimens"] = _specimen_inventory()
    return data
