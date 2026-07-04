"""
Specimen evaluation harness for Revelator.

Runs the Gemini Vision classifier over the labeled SPECIMEN PICTURES set and
scores it, so prompt/pipeline changes can be measured instead of guessed at.
This is the closest thing to "training" in a BYOK Gemini setup: a feedback loop.

Two things are scored per image:
  1. Forged/Genuine axis (most reliable label): each specimen folder has
     Forged/ and Genuine/ subtrees.
       - Forged  image is correct when the verdict is forged or suspicious.
       - Genuine image is correct when the verdict is no_forgery_detected.
  2. Category hit (Forged images only): did the predicted category land in the
     set of codes acceptable for that folder (subfolder-precise where possible)?

Usage (run from the backend/ directory):
    python evaluate_specimens.py --sample 2                 # quick smoke test
    python evaluate_specimens.py --sample 10 --category ERASURE
    python evaluate_specimens.py --sample 5 --critique      # include the low-confidence critique pass
    python evaluate_specimens.py --sample 3 --out misses.csv

Every image is a real Gemini call on your GEMINI_API_KEY, so --sample defaults
to a tiny number. See CLAUDE.md for the folder -> code map.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import string
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

from app.config import GEMINI_API_KEY  # noqa: E402
from app.forgery.gemini_vision import (  # noqa: E402
    classify as gemini_classify,
    confidence_gated_analyze,
    preprocess_image,
    CATEGORY_CODES,
    CATEGORY_LABELS,
)

SPECIMEN_DIR = Path(__file__).resolve().parent.parent / "SPECIMEN PICTURES"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# The live dashboard reads this file via GET /api/prompt-analysis/accuracy.
ACCURACY_FILE = Path(__file__).resolve().parent / "app" / "data" / "specimen_accuracy.json"

# Categories that count as "a forgery/tampering sign was found".
FORGERY_CATS = {c for c in CATEGORY_CODES if c not in {"no_forgery_detected", "not_a_document", "other"}}

# Folder name -> acceptable predicted codes (folder-level), against the current
# 16-forgery taxonomy. Specimen folders that have no dedicated category in that
# taxonomy (charred, water-soaked, paper-fold, embossing, typewriting) map to
# "other" - the honest expectation is that the model routes them there. The
# forged/genuine axis is still scored for every folder.
FOLDER_EXPECTED = {
    "ADDITION": {"addition_insertion", "addition_interlineation"},
    "CHARRED DOCUMENTS": {"other"},
    "CONTACT WRITING": {"other", "traced_carbon"},
    "COUNTERFEITED-FALSIFIED DOCUMENTS": {
        "currency_analysis", "digital_desktop", "digital_cut_paste", "digital_scanned",
        "addition_insertion", "erasure_chemical", "erasure_mechanical", "other",
    },
    "EMBOSING PRINT": {"other"},
    "ERASURE": {"erasure_chemical", "erasure_mechanical"},
    "INDENTED WRITINGS": {"sympathetic_indented", "traced_indentation"},
    "MODERN FORGERY": {"digital_cut_paste", "digital_desktop", "digital_scanned"},
    "OBLITERATED WRITING": {"obliteration_ink", "obliteration_whiteout"},
    "PAPER FOLD": {"other"},
    "SECRET WRITING": {"sympathetic_special"},
    "TRACED FORGERY": {"traced_carbon", "traced_indentation", "traced_projection"},
    "TYPEWRITING IDENTIFICAITON": {"other"},
    "WATER SOAKED DOCUMENTS_": {"other"},
}

# (folder, UPPERCASE subfolder token) -> precise code, when the folder splits by method.
SUBFOLDER_EXPECTED = {
    ("ERASURE", "CHEMICAL"): {"erasure_chemical"},
    ("ERASURE", "MECHANICAL"): {"erasure_mechanical"},
    ("MODERN FORGERY", "CUT AND PASTE"): {"digital_cut_paste"},
    ("MODERN FORGERY", "DESKTOP PUBLISHING"): {"digital_desktop"},
    ("MODERN FORGERY", "SCAN DOCUMENT"): {"digital_scanned"},
    ("TRACED FORGERY", "CARBON"): {"traced_carbon"},
    ("TRACED FORGERY", "CANAL PROCESS"): {"traced_indentation"},
    ("TRACED FORGERY", "TRANSMITTED LIGHT"): {"traced_projection"},
}


def verdict_from(category: str, confidence: float) -> str:
    """Mirror of _verdict_from_gemini in routes/analyze.py."""
    if category == "not_a_document":
        return "not_a_document"
    if category == "no_forgery_detected":
        return "no_forgery_detected"
    if confidence >= 0.70:
        return "forged"
    if confidence >= 0.50:
        return "suspicious"
    return "no_forgery_detected"


def label_of(parts: list[str]) -> str | None:
    """Forged / Genuine from the path segments, or None if unlabeled (e.g. Unsorted)."""
    lowered = [p.lower() for p in parts]
    if "forged" in lowered:
        return "forged"
    if "genuine" in lowered:
        return "genuine"
    return None


def acceptable_codes(folder: str, rel_parts: list[str]) -> set[str]:
    up = [p.upper() for p in rel_parts]
    for (f, token), codes in SUBFOLDER_EXPECTED.items():
        if f == folder and token in up:
            return codes
    return FOLDER_EXPECTED.get(folder, set())


def collect(sample: int, only: str | None, seed: int) -> list[dict]:
    """Pick up to `sample` images per (folder, forged/genuine)."""
    rng = random.Random(seed)
    buckets: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for folder in sorted(FOLDER_EXPECTED):
        if only and only.upper() not in folder.upper():
            continue
        root = SPECIMEN_DIR / folder
        if not root.is_dir():
            print(f"[WARN] missing folder: {root}")
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
                continue
            rel_parts = path.relative_to(root).parts
            lab = label_of(list(rel_parts))
            if lab is None:
                continue  # skip Unsorted / unlabeled
            buckets[(folder, lab)].append(path)

    chosen: list[dict] = []
    for (folder, lab), paths in buckets.items():
        rng.shuffle(paths)
        for p in paths[:sample]:
            rel_parts = list(p.relative_to(SPECIMEN_DIR / folder).parts)
            chosen.append({
                "folder": folder,
                "label": lab,
                "path": p,
                "accept": acceptable_codes(folder, rel_parts),
            })
    return chosen


def generate_scan_id() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"RV-{ts}-{rnd}"


def resolve_keys_and_user(email):
    """Return (keys, user_id, source). Gathers ALL of the account's keys (active
    first) so the run can rotate across them to dodge free-tier rate limits;
    falls back to any account's keys, then the env GEMINI_API_KEY."""
    from app.database import SessionLocal
    from app.models import User, UserApiKey
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        uid = user.id if user else None
        if user:
            rows = (db.query(UserApiKey).filter(UserApiKey.user_id == user.id)
                    .order_by(UserApiKey.is_active.desc()).all())
            keys = [r.api_key for r in rows if r.api_key]
            if not keys and user.gemini_api_key:
                keys = [user.gemini_api_key]
            if keys:
                return keys, uid, f"db user_api_keys ({email}, {len(keys)} key(s))"
        rows = db.query(UserApiKey).all()
        keys = [r.api_key for r in rows if r.api_key]
        if keys:
            return keys, (uid or rows[0].user_id), f"db user_api_keys (any account, {len(keys)})"
        if GEMINI_API_KEY:
            return [GEMINI_API_KEY], uid, "env GEMINI_API_KEY"
        return [], uid, None
    finally:
        db.close()


def _classify_rotating(pre, keys, start):
    """Round-robin across keys; on an unavailable/rate-limited response, fall
    through to the next key. Returns (result, key_index_used)."""
    last = None
    n = len(keys)
    for off in range(n):
        ki = (start + off) % n
        res = gemini_classify(pre, api_key=keys[ki])
        if not res.get("_unavailable"):
            return res, ki
        last = res
    return last, start % n


def persist_scan(user_id, image, res, verdict, conf, filename):
    """Write a Scan row (+ image) so the run shows up in the account's history,
    mirroring what /api/analyze persists."""
    from app.database import SessionLocal
    from app.models import Scan
    from app.config import UPLOAD_DIR
    scan_id = generate_scan_id()
    w, h = image.size
    image_path = None
    try:
        d = UPLOAD_DIR / user_id
        d.mkdir(parents=True, exist_ok=True)
        (image if image.mode == "RGB" else image.convert("RGB")).save(d / f"{scan_id}.jpg", format="JPEG", quality=88)
        image_path = f"{user_id}/{scan_id}.jpg"
    except Exception:
        image_path = None
    db = SessionLocal()
    try:
        db.add(Scan(
            scan_id=scan_id, user_id=user_id, filename=filename,
            document_type=None, verdict=verdict, confidence_score=conf,
            annotations_json="[]", image_width=w, image_height=h, image_path=image_path,
            detected_category=res.get("category"), detected_subtype=res.get("subtype"),
            category_explanation=res.get("explanation"), tools_likely_used=res.get("tools_likely_used"),
            category_confidence=res.get("confidence"),
            category_evidence=json.dumps(res.get("evidence", [])),
            reasoning_steps=json.dumps(res.get("reasoning_steps", [])),
            anomaly_location=res.get("anomaly_location"),
            alternatives=json.dumps(res.get("alternatives", [])),
            certainty_level=res.get("certainty_level"),
            suspicion_reason="[specimen eval]",
        ))
        db.commit()
    finally:
        db.close()
    return scan_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Score Revelator against the SPECIMEN PICTURES set.")
    ap.add_argument("--sample", type=int, default=2, help="images per (folder, forged/genuine). Default 2.")
    ap.add_argument("--category", default=None, help="substring filter on folder name, e.g. ERASURE")
    ap.add_argument("--critique", action="store_true", help="also run the low-confidence self-critique pass")
    ap.add_argument("--seed", type=int, default=7, help="sampling seed (for reproducible picks)")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep between calls")
    ap.add_argument("--out", default="specimen_misses.csv", help="CSV path for the miss log")
    ap.add_argument("--user", default="test@gmail.com", help="account whose key to use and save scans under")
    ap.add_argument("--no-save-history", dest="save_history", action="store_false", help="do not write Scan rows")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-image line")
    args = ap.parse_args()

    keys, user_id, source = resolve_keys_and_user(args.user)
    if not keys:
        print("ERROR: no Gemini API key found. Add one to the test account in the app")
        print("       (Account -> API Keys), or set GEMINI_API_KEY in the project .env, then retry.")
        return 2
    if not SPECIMEN_DIR.is_dir():
        print(f"ERROR: specimen folder not found at {SPECIMEN_DIR}")
        return 2

    save_history = bool(args.save_history and user_id)

    items = collect(args.sample, args.category, args.seed)
    if not items:
        print("No labeled images matched. Check --category spelling.")
        return 1

    print(f"Specimen set : {SPECIMEN_DIR}")
    print(f"Key source   : {source}")
    print(f"Save history : {('yes -> user ' + user_id) if save_history else 'no'}")
    print(f"Evaluating   : {len(items)} images "
          f"({'2 calls each' if args.critique else '1 call each'})\n")

    # folder -> counters
    stats = defaultdict(lambda: {"n": 0, "label_ok": 0, "cat_hit": 0, "cat_n": 0})
    misses: list[dict] = []
    unavailable = 0

    for i, it in enumerate(items, 1):
        folder, lab, path, accept = it["folder"], it["label"], it["path"], it["accept"]
        try:
            image = Image.open(path)
            pre = preprocess_image(image)
            res, used_ki = _classify_rotating(pre, keys, i - 1)
            if res.get("_unavailable"):
                unavailable += 1
                if not args.quiet:
                    print(f"[{i}/{len(items)}] unavailable (all keys): {str(res.get('explanation',''))[:80]}")
                if unavailable >= 6:
                    print("ABORT: too many unavailable responses (keys rate-limited/invalid).")
                    break
                continue
            if args.critique:
                res = confidence_gated_analyze(pre, {}, res, api_key=keys[used_ki]).get("result", res)
        except Exception as exc:  # keep going on a single bad file
            print(f"[{i}/{len(items)}] {folder}/{lab}: ERROR {type(exc).__name__}: {exc}")
            continue

        cat = res.get("category", "other")
        conf = float(res.get("confidence", 0.0) or 0.0)
        verdict = verdict_from(cat, conf)
        pred_binary = "genuine" if verdict == "no_forgery_detected" else (
            "not_a_document" if verdict == "not_a_document" else "forged")

        label_ok = (
            (lab == "forged" and verdict in {"forged", "suspicious"}) or
            (lab == "genuine" and verdict == "no_forgery_detected")
        )
        s = stats[folder]
        s["n"] += 1
        s["label_ok"] += int(label_ok)

        cat_hit = None
        if lab == "forged":
            s["cat_n"] += 1
            cat_hit = cat in accept
            s["cat_hit"] += int(cat_hit)

        if save_history:
            try:
                persist_scan(user_id, image, res, verdict, conf, f"specimen/{folder}/{lab}/{path.name}")
            except Exception as exc:
                if not args.quiet:
                    print(f"    (history save failed: {exc})")

        if not args.quiet:
            flag = "OK " if label_ok else "XX "
            hit_str = "" if cat_hit is None else (" cat+" if cat_hit else " cat-")
            print(f"[{i}/{len(items)}] {flag}{folder}/{lab:<7} -> {cat} ({conf:.2f} {verdict}){hit_str}")

        if not label_ok or cat_hit is False:
            misses.append({
                "folder": folder, "label": lab, "file": str(path.name),
                "predicted_category": cat, "confidence": f"{conf:.2f}",
                "verdict": verdict, "pred_binary": pred_binary,
                "acceptable": "|".join(sorted(accept)),
            })
        if args.delay:
            time.sleep(args.delay)

    # ── Report ────────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print(f"{'FOLDER':<36}{'N':>4}{'FORGED/GENUINE':>16}{'CATEGORY HIT':>16}")
    print("-" * 78)
    tot_n = tot_lab = tot_cat_hit = tot_cat_n = 0
    for folder in sorted(stats):
        s = stats[folder]
        lab_pct = 100 * s["label_ok"] / s["n"] if s["n"] else 0
        cat_pct = 100 * s["cat_hit"] / s["cat_n"] if s["cat_n"] else 0
        lab_col = f"{s['label_ok']}/{s['n']} ({lab_pct:.0f}%)"
        cat_col = f"{s['cat_hit']}/{s['cat_n']} ({cat_pct:.0f}%)" if s["cat_n"] else "-"
        print(f"{folder:<36}{s['n']:>4}{lab_col:>16}{cat_col:>16}")
        tot_n += s["n"]; tot_lab += s["label_ok"]; tot_cat_hit += s["cat_hit"]; tot_cat_n += s["cat_n"]
    print("-" * 78)
    lab_pct = 100 * tot_lab / tot_n if tot_n else 0
    cat_pct = 100 * tot_cat_hit / tot_cat_n if tot_cat_n else 0
    lab_col = f"{tot_lab}/{tot_n} ({lab_pct:.0f}%)"
    cat_col = f"{tot_cat_hit}/{tot_cat_n} ({cat_pct:.0f}%)"
    print(f"{'TOTAL':<36}{tot_n:>4}{lab_col:>16}{cat_col:>16}")
    print("=" * 78)
    print("FORGED/GENUINE = did the verdict match the folder's Forged/Genuine label.")
    print("CATEGORY HIT   = on Forged images, did the predicted code land in the acceptable set.")

    # Write the machine-readable results the live dashboard reads.
    folders_doc = []
    for folder in sorted(stats):
        s = stats[folder]
        folders_doc.append({
            "folder": folder,
            "n": s["n"],
            "label_ok": s["label_ok"],
            "label_pct": round(100 * s["label_ok"] / s["n"], 1) if s["n"] else 0.0,
            "cat_hit": s["cat_hit"],
            "cat_n": s["cat_n"],
            "cat_pct": round(100 * s["cat_hit"] / s["cat_n"], 1) if s["cat_n"] else None,
        })
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.getenv("GEMINI_VISION_MODEL") or "auto (fallback chain)",
        "sample_per_bucket": args.sample,
        "critique": bool(args.critique),
        "category_filter": args.category or None,
        "total_images": tot_n,
        "overall": {
            "n": tot_n,
            "label_ok": tot_lab,
            "label_pct": round(100 * tot_lab / tot_n, 1) if tot_n else 0.0,
            "cat_hit": tot_cat_hit,
            "cat_n": tot_cat_n,
            "cat_pct": round(100 * tot_cat_hit / tot_cat_n, 1) if tot_cat_n else 0.0,
        },
        "folders": folders_doc,
        "misses": len(misses),
    }
    ACCURACY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCURACY_FILE.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"Accuracy summary written to {ACCURACY_FILE} (served at /api/prompt-analysis/accuracy)")

    if misses:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(misses[0].keys()))
            w.writeheader()
            w.writerows(misses)
        print(f"\n{len(misses)} miss(es) written to {args.out}")
    else:
        print("\nNo misses. (Small sample - scale up --sample before trusting this.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
