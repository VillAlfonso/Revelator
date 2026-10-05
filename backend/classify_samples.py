"""Assign fixed category labels to Samples images and optionally explain them with Gemini.

Folder labels are authoritative; Gemini is only asked for visible supporting
evidence and cannot change the category assigned in the output.

Run from the repository root:
    python backend/classify_samples.py
    python backend/classify_samples.py --explain --limit 2
    python backend/classify_samples.py --explain --limit 0 --output samples_labeled.json

The final command calls Gemini for every image and may incur API charges.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.forgery.sample_metadata import (  # noqa: E402
    IMAGE_EXTENSIONS,
    SAMPLES_DIR,
    category_for_path,
)
from app.forgery.sample_prompt import explain_labeled_sample  # noqa: E402


def collect_samples(samples_root: Path) -> list[tuple[Path, str, str]]:
    if not samples_root.is_dir():
        raise FileNotFoundError(f"Samples folder does not exist: {samples_root}")

    samples: list[tuple[Path, str, str]] = []
    unlabeled: list[str] = []
    for path in sorted(samples_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        category = category_for_path(path, samples_root)
        if category is None:
            unlabeled.append(str(path.relative_to(samples_root)))
            continue
        code, label = category
        samples.append((path, code, label))

    if unlabeled:
        names = "\n  ".join(unlabeled[:20])
        more = f"\n  ... and {len(unlabeled) - 20} more" if len(unlabeled) > 20 else ""
        raise ValueError(
            "Could not determine a category from a sample folder or filename. "
            "Move these images under a recognized category folder or add an explicit "
            f"mapping:\n  {names}{more}"
        )
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assign category labels from Samples folder names; optionally ask Gemini for visible reasons."
    )
    parser.add_argument("--samples", type=Path, default=SAMPLES_DIR, help="Samples folder (default: repository Samples/).")
    parser.add_argument("--explain", action="store_true", help="Call Gemini for image-grounded reasons. Uses API tokens.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum images to process; required with --explain. Use 0 for all.")
    parser.add_argument("--output", type=Path, help="Write the JSON results to this path instead of stdout.")
    args = parser.parse_args()

    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.explain and args.limit is None:
        parser.error("--explain requires --limit (for example, --limit 2; use --limit 0 for all images)")

    try:
        samples = collect_samples(args.samples.resolve())
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.limit and args.limit > 0:
        samples = samples[:args.limit]
    if not samples:
        print("No labeled images found.", file=sys.stderr)
        return 1

    api_key = ""
    model = ""
    if args.explain:
        from app.config import GEMINI_API_KEY, GEMINI_VISION_MODEL

        api_key = GEMINI_API_KEY
        model = GEMINI_VISION_MODEL
        if not api_key:
            print("ERROR: Set GEMINI_API_KEY in the environment or project .env to call Gemini.", file=sys.stderr)
            return 2

    results = []
    for path, code, label in samples:
        result = {
            "file": str(path.relative_to(args.samples.resolve())),
            "category": code,
            "category_label": label,
            "dataset_label": "genuine" if code == "no_forgery_detected" else "forged",
            "explanation": None,
        }
        if args.explain:
            with Image.open(path) as image:
                result["explanation"] = explain_labeled_sample(
                    image,
                    label,
                    result["dataset_label"],
                    api_key,
                    model,
                )
        results.append(result)

    output = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(output + os.linesep, encoding="utf-8")
        print(f"Wrote {len(results)} sample result(s) to {args.output}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
