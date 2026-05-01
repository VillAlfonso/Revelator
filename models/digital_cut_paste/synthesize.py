"""
Synthesize a YOLOv8 cut-and-paste forgery dataset from clean source documents.

For each source image, this script generates N forged versions by copying a
random text-rich region and pasting it elsewhere — either onto the same
document (default) or onto a different source (--cross-source). Realistic
perturbations are applied so the cut-paste artifacts the model learns match
what real forgeries look like.

Output is written in standard Roboflow / YOLOv8 layout:
    <out>/train/images/, train/labels/
    <out>/valid/images/, valid/labels/
    <out>/test/images/,  test/labels/
    <out>/data.yaml

Quick usage (defaults match the old behavior):
    python synthesize.py --sources ./sources --count 8

Recommended usage (everything from DATASET_SPEC.md §5 enabled):
    python synthesize.py --sources ./sources --count 12 \\
        --cross-source --scale-rotate --color-match \\
        --multi-region-prob 0.15 --negatives 1 --source-split

Then run train.py — it picks up data.yaml automatically.

Citation context: this is the synthesis-based forgery training approach used
by MVSS-Net and ManTra-Net. Realistic perturbations are applied to avoid
overfitting to artificially clean paste edges.
"""

import argparse
import io
import math
import random
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

CLASS_NAME = "cut_paste"
IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")


# ─── Region selection ──────────────────────────────────────────────────────

def variance_score(crop: Image.Image) -> float:
    """Standard deviation of luminance — high = textured/text, low = blank."""
    arr = np.asarray(crop.convert("L"), dtype=np.float32)
    return float(arr.std())


def pick_text_rich_region(img, min_dim, max_dim, attempts=24):
    """Random search for a content-rich rectangular region. Returns (x,y,w,h) or None."""
    W, H = img.size
    upper_w = min(max_dim, W // 3)
    upper_h = min(max_dim, H // 3)
    if upper_w < min_dim or upper_h < min_dim:
        return None

    best, best_score = None, -1.0
    for _ in range(attempts):
        w = random.randint(min_dim, upper_w)
        h = random.randint(min_dim, upper_h)
        x = random.randint(0, W - w)
        y = random.randint(0, H - h)
        score = variance_score(img.crop((x, y, x + w, y + h)))
        if score > best_score:
            best, best_score = (x, y, w, h), score
    return best


def overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


# ─── Patch perturbations ──────────────────────────────────────────────────

def perturb_brightness(patch):
    return ImageEnhance.Brightness(patch).enhance(random.uniform(0.92, 1.08))


def perturb_color(patch):
    return ImageEnhance.Color(patch).enhance(random.uniform(0.92, 1.08))


def perturb_blur(patch):
    return patch.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.3, 0.9)))


def perturb_jpeg(patch):
    """Re-encode the patch at a different JPEG quality — produces the
    double-compression artifact that distinguishes real forgeries."""
    buf = io.BytesIO()
    patch.save(buf, format="JPEG", quality=random.randint(55, 85))
    buf.seek(0)
    return Image.open(buf).convert("RGB")


PERTURB_FNS = [perturb_brightness, perturb_color, perturb_blur, perturb_jpeg]


def apply_random_perturbations(patch):
    fns = random.sample(PERTURB_FNS, k=random.randint(1, 3))
    for fn in fns:
        patch = fn(patch)
    return patch


def scale_and_rotate(patch: Image.Image) -> Image.Image:
    """Random small scale + rotation. Models see real forgers' tell-tale
    anti-aliased edges from resize/rotate-to-fit."""
    if random.random() < 0.5:
        scale = random.uniform(0.85, 1.20)
        new_size = (max(8, int(patch.width * scale)), max(8, int(patch.height * scale)))
        patch = patch.resize(new_size, Image.LANCZOS)
    if random.random() < 0.5:
        angle = random.uniform(-3.0, 3.0)
        # expand=True grows the canvas to fit the rotated content; corners are transparent
        # but we paste back as RGB so pixels outside content are filled with mean color.
        patch = patch.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=None)
        if patch.mode != "RGB":
            patch = patch.convert("RGB")
    return patch


def color_match_to_destination(patch: Image.Image, canvas: Image.Image, dst_xy: Tuple[int, int]) -> Image.Image:
    """Shift patch mean RGB ~50% toward the destination region's mean.
    Simulates what a careful forger does to disguise a paste."""
    dx, dy = dst_xy
    pw, ph = patch.size
    W, H = canvas.size
    sample_box = (
        max(0, dx - 8),
        max(0, dy - 8),
        min(W, dx + pw + 8),
        min(H, dy + ph + 8),
    )
    dst_region = np.asarray(canvas.crop(sample_box).convert("RGB"), dtype=np.float32)
    dst_mean = dst_region.reshape(-1, 3).mean(axis=0)

    arr = np.asarray(patch.convert("RGB"), dtype=np.float32)
    patch_mean = arr.reshape(-1, 3).mean(axis=0)
    shift = (dst_mean - patch_mean) * 0.5
    arr = np.clip(arr + shift, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


# ─── Pasting (hard-edge or feathered) ─────────────────────────────────────

def make_feather_mask(size, feather: int):
    """Black border that fades to white in the middle, blurred for soft edges."""
    w, h = size
    mask = Image.new("L", size, 0)
    inset = max(1, feather)
    ImageDraw.Draw(mask).rectangle(
        [inset, inset, w - 1 - inset, h - 1 - inset], fill=255
    )
    return mask.filter(ImageFilter.GaussianBlur(radius=feather))


def paste_patch(canvas, patch, dst_xy, feather: int):
    if feather <= 0:
        canvas.paste(patch, dst_xy)
    else:
        canvas.paste(patch, dst_xy, make_feather_mask(patch.size, feather))


# ─── Main per-image synthesis ─────────────────────────────────────────────

def _make_one_paste(
    canvas: Image.Image,
    donor_img: Image.Image,
    patch_min: int,
    patch_max: int,
    avoid_boxes: List[Tuple[int, int, int, int]],
    scale_rotate: bool,
    color_match: bool,
) -> Optional[Tuple[int, int, int, int]]:
    """One paste operation in-place on `canvas`. Returns the bbox (x,y,w,h)
    that was pasted, or None if no valid region/destination was found."""
    src_box = pick_text_rich_region(donor_img, patch_min, patch_max)
    if src_box is None:
        return None
    sx, sy, sw, sh = src_box
    patch = donor_img.crop((sx, sy, sx + sw, sy + sh))
    patch = apply_random_perturbations(patch)
    if scale_rotate:
        patch = scale_and_rotate(patch)
    pw, ph = patch.size

    W, H = canvas.size
    if pw >= W or ph >= H:
        return None

    # Find a destination that doesn't overlap with previously-pasted regions
    # and (if donor == canvas) doesn't overlap the source either.
    same_source = donor_img is canvas or _images_identical(donor_img, canvas)
    own_box = (sx, sy, sw, sh) if same_source else None

    for _ in range(40):
        dx = random.randint(0, W - pw)
        dy = random.randint(0, H - ph)
        if own_box is not None and overlap(own_box, (dx, dy, pw, ph)):
            continue
        if any(overlap((dx, dy, pw, ph), b) for b in avoid_boxes):
            continue
        break
    else:
        return None

    if color_match:
        patch = color_match_to_destination(patch, canvas, (dx, dy))

    feather = random.choices([0, 0, 0, 1, 2, 3], k=1)[0]
    paste_patch(canvas, patch, (dx, dy), feather=feather)
    return (dx, dy, pw, ph)


def _images_identical(a: Image.Image, b: Image.Image) -> bool:
    """Cheap "same source?" check — only compares size + first scanline.
    Sufficient because we're checking object identity at the source level."""
    return a.size == b.size and bytes(a.tobytes()[:64]) == bytes(b.tobytes()[:64])


def synthesize_image(
    src_img: Image.Image,
    all_sources: List[Image.Image],
    patch_min: int,
    patch_max: int,
    *,
    cross_source_prob: float = 0.0,
    scale_rotate: bool = False,
    color_match: bool = False,
    n_regions: int = 1,
) -> Optional[Tuple[Image.Image, List[Tuple[int, int, int, int]]]]:
    """Generate one forged image with `n_regions` pasted patches.
    Returns (forged_canvas, list_of_bboxes) or None if no patch could be pasted."""
    canvas = src_img.copy()
    bboxes: List[Tuple[int, int, int, int]] = []

    for _ in range(n_regions):
        # Decide donor for this paste
        if cross_source_prob > 0 and len(all_sources) > 1 and random.random() < cross_source_prob:
            others = [s for s in all_sources if s is not src_img]
            donor = random.choice(others) if others else src_img
        else:
            donor = src_img

        bbox = _make_one_paste(
            canvas, donor, patch_min, patch_max,
            avoid_boxes=bboxes,
            scale_rotate=scale_rotate,
            color_match=color_match,
        )
        if bbox is not None:
            bboxes.append(bbox)

    if not bboxes:
        return None
    return canvas, bboxes


def to_yolo_label(bbox, img_w, img_h, cls_id=0):
    x, y, w, h = bbox
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    return f"{cls_id} {cx:.6f} {cy:.6f} {w / img_w:.6f} {h / img_h:.6f}"


def split_indices(n, ratios=(0.7, 0.2, 0.1)):
    idx = list(range(n))
    random.shuffle(idx)
    a = int(n * ratios[0])
    b = int(n * (ratios[0] + ratios[1]))
    return idx[:a], idx[a:b], idx[b:]


def assign_source_splits(sources: List[Path], ratios=(0.7, 0.2, 0.1)) -> dict:
    """Source-level holdout: every forgery from a given source ends up in
    the same split. Prevents the model from training on one forgery of a
    layout and validating on a different forgery of the same layout."""
    shuffled = sources[:]
    random.shuffle(shuffled)
    n = len(shuffled)
    a = int(n * ratios[0])
    b = int(n * (ratios[0] + ratios[1]))
    split_map = {}
    for p in shuffled[:a]:
        split_map[p] = "train"
    for p in shuffled[a:b]:
        split_map[p] = "valid"
    for p in shuffled[b:]:
        split_map[p] = "test"
    return split_map


# ─── CLI ───────────────────────────────────────────────────────────────────

def gather_sources(folder: Path):
    files = []
    for pat in IMAGE_GLOBS:
        files.extend(folder.glob(pat))
    return sorted(set(files))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sources", required=True, type=Path,
                    help="Folder of clean source images (jpg/png)")
    ap.add_argument("--out", default=".", type=Path, help="Dataset output root")
    ap.add_argument("--count", type=int, default=8,
                    help="Forgeries to generate per source image (default: 8)")
    ap.add_argument("--patch-min", type=int, default=40,
                    help="Min patch dimension in px (default: 40)")
    ap.add_argument("--patch-max", type=int, default=220,
                    help="Max patch dimension in px (default: 220)")
    ap.add_argument("--quality", type=int, default=88,
                    help="Output JPEG quality 1-100 (default: 88)")
    ap.add_argument("--seed", type=int, default=42)

    # New features (DATASET_SPEC.md §5)
    ap.add_argument("--cross-source", action="store_true",
                    help="With ~50%% probability, sample patches from a different "
                         "source image. Closer to real-world forgery distribution.")
    ap.add_argument("--scale-rotate", action="store_true",
                    help="Randomly resize and slightly rotate patches before paste.")
    ap.add_argument("--color-match", action="store_true",
                    help="Shift patch mean RGB toward destination — simulates "
                         "the hardest forgeries a model needs to learn.")
    ap.add_argument("--multi-region-prob", type=float, default=0.0,
                    help="Probability per image of pasting 2-3 regions instead of 1.")
    ap.add_argument("--negatives", type=int, default=0,
                    help="For each source, also emit N unmodified copies with "
                         "empty labels — these are the negative training samples "
                         "the model learns NOT to flag. Recommended: 1 with "
                         "--source-split.")
    ap.add_argument("--source-split", action="store_true",
                    help="Split by source image (every forgery from a given "
                         "source goes to the same split). Prevents train/val "
                         "leakage from layout memorization. Strongly recommended.")
    args = ap.parse_args()

    if not args.sources.is_dir():
        print(f"sources folder not found: {args.sources}")
        return 1

    random.seed(args.seed)
    np.random.seed(args.seed)

    source_paths = gather_sources(args.sources)
    if not source_paths:
        print(f"No images found in {args.sources}")
        return 1
    print(f"Found {len(source_paths)} source images.")

    # Load all sources up front so cross-source sampling is cheap.
    all_sources: List[Image.Image] = []
    valid_paths: List[Path] = []
    for p in source_paths:
        try:
            all_sources.append(Image.open(p).convert("RGB"))
            valid_paths.append(p)
        except Exception as e:
            print(f"  skip {p.name}: {e}")
    if not all_sources:
        print("No valid sources loaded.")
        return 1

    out = args.out
    for split in ("train", "valid", "test"):
        (out / split / "images").mkdir(parents=True, exist_ok=True)
        (out / split / "labels").mkdir(parents=True, exist_ok=True)

    # Splits — either source-level (recommended) or post-hoc random.
    source_split_map = assign_source_splits(valid_paths) if args.source_split else None
    if source_split_map:
        n_train = sum(1 for v in source_split_map.values() if v == "train")
        n_valid = sum(1 for v in source_split_map.values() if v == "valid")
        n_test  = sum(1 for v in source_split_map.values() if v == "test")
        print(f"Source-level split: {n_train} train / {n_valid} valid / {n_test} test sources.")

    cross_prob = 0.5 if args.cross_source else 0.0

    # Generate. If source-split, write directly to the target split folder;
    # otherwise accumulate and split post-hoc like the original behavior.
    examples = []        # (Image, label_text, basename, split_or_None)
    forgery_total = 0
    negative_total = 0

    for src_path, src_img in zip(valid_paths, all_sources):
        split_for_source = source_split_map.get(src_path) if source_split_map else None
        made = 0

        # ── Forgeries
        for k in range(args.count):
            n_regions = 1
            if args.multi_region_prob > 0 and random.random() < args.multi_region_prob:
                n_regions = random.choice([2, 3])

            r = synthesize_image(
                src_img, all_sources,
                args.patch_min, args.patch_max,
                cross_source_prob=cross_prob,
                scale_rotate=args.scale_rotate,
                color_match=args.color_match,
                n_regions=n_regions,
            )
            if r is None:
                continue
            forged, bboxes = r
            label = "\n".join(
                to_yolo_label(b, *forged.size) for b in bboxes
            )
            examples.append((forged, label, f"{src_path.stem}_forge_{k:03d}", split_for_source))
            made += 1
            forgery_total += 1

        # ── Negatives (clean originals with empty labels)
        for j in range(args.negatives):
            examples.append((src_img.copy(), "", f"{src_path.stem}_clean_{j:03d}", split_for_source))
            negative_total += 1

        suffix = f" (split={split_for_source})" if split_for_source else ""
        print(f"  {src_path.name}: {made}/{args.count} forgeries"
              f" + {args.negatives} negatives{suffix}")

    if not examples:
        print("No examples generated.")
        return 1

    # Write to disk
    if source_split_map:
        # Each example already has its split assigned
        counts = {"train": 0, "valid": 0, "test": 0}
        for img, label, name, split in examples:
            counts[split] += 1
            img.save(out / split / "images" / f"{name}.jpg",
                     format="JPEG", quality=args.quality)
            (out / split / "labels" / f"{name}.txt").write_text(
                (label + "\n") if label else ""
            )
        for s, c in counts.items():
            print(f"  {s}: {c} examples")
    else:
        # Old behavior: random shuffle across all examples
        train_idx, valid_idx, test_idx = split_indices(len(examples))
        splits = {"train": train_idx, "valid": valid_idx, "test": test_idx}
        for split_name, indices in splits.items():
            for i in indices:
                img, label, name, _ = examples[i]
                img.save(out / split_name / "images" / f"{name}.jpg",
                         format="JPEG", quality=args.quality)
                (out / split_name / "labels" / f"{name}.txt").write_text(
                    (label + "\n") if label else ""
                )
            print(f"  {split_name}: {len(indices)} examples")

    yaml_path = out / "data.yaml"
    yaml_path.write_text(
        f"path: {out.resolve()}\n"
        f"train: train/images\n"
        f"val: valid/images\n"
        f"test: test/images\n"
        f"\n"
        f"nc: 1\n"
        f"names:\n  0: {CLASS_NAME}\n"
    )
    print(f"\nTotal: {forgery_total} forgeries + {negative_total} negatives "
          f"across {len(valid_paths)} source images.")
    print(f"data.yaml written to {yaml_path}")
    print("\nReady to train. Run:\n  python train.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
