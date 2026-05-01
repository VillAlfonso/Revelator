"""
Bundle a category's dataset into a single ZIP so it can be uploaded to
Google Colab.

Default behavior resizes all images to 640px max dimension and re-encodes
at JPEG quality 85, which typically shrinks the zip 5-10× without hurting
training (YOLOv8 trains at 640px anyway, and bbox labels are normalized
[0,1] so resize doesn't break them).

Usage:
    python scripts/zip_for_colab.py
    python scripts/zip_for_colab.py --category digital_cut_paste --max-dim 640
    python scripts/zip_for_colab.py --no-resize        # keep original sizes

What gets included:
    train/images/, train/labels/
    valid/images/, valid/labels/
    test/images/,  test/labels/
    data.yaml

What gets excluded:
    weights/, runs/, __pycache__/, *.pt, *.pyc
"""

import argparse
import io
import sys
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {"weights", "runs", "__pycache__"}
EXCLUDE_SUFFIXES = {".pt", ".pyc"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if rel.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def resized_image_bytes(path: Path, max_dim: int, quality: int) -> bytes:
    """Open an image, resize so longest edge == max_dim if larger, return JPEG bytes."""
    from PIL import Image  # imported lazily so non-resize mode has zero deps

    img = Image.open(path).convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--category", default="digital_cut_paste",
                    help="Folder under models/ to zip (default: digital_cut_paste)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output zip path (default: ./<category>.zip in repo root)")
    ap.add_argument("--max-dim", type=int, default=640,
                    help="Resize images so longest edge == this. Default 640 "
                         "(matches YOLOv8 default training size). 0 = no resize.")
    ap.add_argument("--quality", type=int, default=85,
                    help="JPEG quality 1-100 (default: 85)")
    ap.add_argument("--no-resize", action="store_true",
                    help="Keep original image sizes (much larger zip).")
    args = ap.parse_args()

    if args.no_resize:
        args.max_dim = 0

    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "models" / args.category
    if not src.is_dir():
        print(f"Source folder not found: {src}")
        return 1

    out = args.out or (repo_root / f"{args.category}.zip")
    mode = f"resize to {args.max_dim}px / Q{args.quality}" if args.max_dim else "original"
    print(f"Zipping {src}  ({mode})")
    print(f"     -> {out}")

    files_to_zip = []
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if should_skip(rel):
            continue
        files_to_zip.append((p, rel))

    if not files_to_zip:
        print("Nothing to zip — does the dataset exist yet?")
        return 1

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for i, (p, rel) in enumerate(files_to_zip, 1):
            arcname = str(Path(args.category) / rel)
            if args.max_dim and rel.suffix.lower() in IMAGE_SUFFIXES:
                try:
                    zf.writestr(arcname, resized_image_bytes(p, args.max_dim, args.quality))
                except Exception as e:
                    print(f"  resize failed for {rel} ({e}); copying as-is")
                    zf.write(p, arcname=arcname)
            else:
                zf.write(p, arcname=arcname)
            if i % 1000 == 0:
                print(f"  zipped {i}/{len(files_to_zip)}")

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nDone. {len(files_to_zip)} files, {size_mb:.1f} MB.")
    print(f"\nNext: open {out.name} in Google Colab — see")
    print(f"      models/{args.category}/COLAB_TRAINING.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
