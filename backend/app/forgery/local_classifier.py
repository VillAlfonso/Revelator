"""
Local specimen classifier - optional fast pre-classifier.

If backend/app/data/specimen_classifier.pt exists (trained by train_classifier.py)
and torch is installed, predict() returns the specimen category for an image plus a
confidence. The analyze pipeline uses a confident prediction to hand Gemini a locked
category hint (and a short explain-only prompt), so answers stay category-correct on
the specimen set and cost fewer tokens. If torch or the model file is missing,
predict() returns None and the pipeline falls back to full Gemini classification.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any

from PIL import Image

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "specimen_classifier.pt"

# classifier class (a forgery code from train_classifier.py) -> (primary Gemini code,
# candidate leaf codes, human label). Codes outside the 15-category set map to "other".
CLASS_TO_GEMINI = {
    "traced_carbon": ("traced_carbon", ["traced_carbon"], "carbon-transfer tracing"),
    "traced_indentation": ("traced_indentation", ["traced_indentation"], "indentation / canal tracing"),
    "traced_projection": ("traced_projection", ["traced_projection"], "projection tracing"),
    "erasure_chemical": ("erasure_chemical", ["erasure_chemical"], "chemical erasure"),
    "erasure_mechanical": ("erasure_mechanical", ["erasure_mechanical"], "mechanical erasure"),
    "digital_cut_paste": ("digital_cut_paste", ["digital_cut_paste"], "digital cut-and-paste"),
    "digital_desktop": ("digital_desktop", ["digital_desktop"], "desktop-published forgery"),
    "digital_scanned": ("digital_scanned", ["digital_scanned"], "scanned composite"),
    "addition": ("addition_insertion", ["addition_insertion", "addition_interlineation"], "an addition (insertion or interlineation)"),
    "obliteration": ("obliteration_ink", ["obliteration_ink", "obliteration_whiteout"], "an obliteration (ink or white-out)"),
    "sympathetic_indented": ("sympathetic_indented", ["sympathetic_indented"], "indented (impression) writing"),
    "sympathetic_special": ("sympathetic_special", ["sympathetic_special"], "secret / sympathetic ink"),
    "counterfeit": ("currency_analysis", ["currency_analysis", "digital_desktop", "other"], "a banknote or official document (verify authenticity)"),
    "charred": ("other", ["other"], "a charred / burned document"),
    "water_soaked": ("other", ["other"], "a water-soaked / liquid-damaged document"),
    "paper_fold": ("other", ["other"], "a paper-fold / crease specimen"),
    "embossing": ("other", ["other"], "an embossed / dry-seal specimen"),
    "typewriting": ("other", ["other"], "a typewriting-identification specimen"),
    "contact_writing": ("other", ["other"], "a contact / offset-transfer specimen"),
}


@lru_cache(maxsize=1)
def _load():
    """Load the model once. Returns a context dict, or None if unavailable."""
    try:
        import torch
        import torch.nn as nn
        from torchvision import models
        import torchvision.transforms as T
    except Exception:
        return None
    if not MODEL_PATH.exists():
        return None
    try:
        ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
        classes = ckpt["classes"]
        m = models.mobilenet_v3_large(weights=None)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, len(classes))
        m.load_state_dict(ckpt["state_dict"])
        m.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        m.to(device)
        tf = T.Compose([
            T.Resize((ckpt["img_size"], ckpt["img_size"])),
            T.ToTensor(),
            T.Normalize(ckpt["mean"], ckpt["std"]),
        ])
        return {"model": m, "classes": classes, "tf": tf, "device": device, "torch": torch}
    except Exception as exc:
        print(f"[WARN] local_classifier failed to load: {exc}")
        return None


def available() -> bool:
    return _load() is not None


def predict(image: Image.Image) -> Optional[Dict[str, Any]]:
    """Return {folder, category, candidates, label, confidence} or None if unavailable."""
    ctx = _load()
    if ctx is None:
        return None
    torch = ctx["torch"]
    x = ctx["tf"](image.convert("RGB")).unsqueeze(0).to(ctx["device"])
    with torch.no_grad():
        probs = torch.softmax(ctx["model"](x), dim=1)[0]
        conf, idx = torch.max(probs, 0)
    cls = ctx["classes"][int(idx)]
    fam, cands, label = CLASS_TO_GEMINI.get(cls, ("other", ["other"], cls))
    return {
        "class": cls,
        "category": fam,
        "candidates": cands,
        "label": label,
        "confidence": float(conf),
    }
