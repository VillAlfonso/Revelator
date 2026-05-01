"""
Pull a balanced sample of clean document images from public Hugging Face
datasets and drop them in a folder ready for synthesize.py.

The classic choice (RVL-CDIP) uses an old loading-script format that newer
`datasets` versions removed. This script uses modern Parquet-based mirrors
that work out of the box: CORD-v2 (receipts) and FUNSD (forms). Together
they cover ~950 unique real document images — enough for a solid
synthesize.py-driven dataset.

Usage:
    # Default — pull up to 500 images split across CORD + FUNSD
    python scripts/fetch_sources.py --out ./sources

    # Pull more (CORD has ~800 + FUNSD ~150 max)
    python scripts/fetch_sources.py --out ./sources --n 950

    # Single dataset:
    python scripts/fetch_sources.py --out ./sources --datasets cord

After this, run:
    python models/digital_cut_paste/synthesize.py \\
        --sources ./sources --count 12 \\
        --cross-source --scale-rotate --color-match \\
        --negatives 1 --source-split

Requirements:
    pip install datasets pillow
"""

import argparse
import sys
from pathlib import Path
from typing import List


# Modern Parquet-format datasets confirmed to work with datasets>=4.0
# and that contain document images Revelator's detector should generalize over.
KNOWN_DATASETS = {
    "cord": {
        "repo": "naver-clova-ix/cord-v2",
        "split": "train",
        "image_key": "image",
        "label": "receipt",
        "approx_size": 800,
    },
    "funsd": {
        "repo": "nielsr/funsd",
        "split": "train",
        "image_key": "image",
        "label": "form",
        "approx_size": 150,
    },
}

DEFAULT_DATASETS = ["cord", "funsd"]


def fetch_one_dataset(spec: dict, label: str, out_dir: Path, target: int, seed: int) -> int:
    """Stream `target` images from a single HF dataset; return how many were saved."""
    from datasets import load_dataset  # imported here so the module imports cleanly

    print(f"\n[{label}] streaming {spec['repo']}...")
    try:
        ds = load_dataset(spec["repo"], split=spec["split"], streaming=True)
    except Exception as e:
        print(f"  failed to open: {e}")
        return 0

    try:
        ds = ds.shuffle(seed=seed, buffer_size=1_000)
    except Exception:
        pass

    saved = 0
    for sample in ds:
        if saved >= target:
            break
        img = sample.get(spec["image_key"])
        if img is None:
            continue
        stem = f"{label}_{saved:04d}.jpg"
        try:
            img.convert("RGB").save(out_dir / stem, format="JPEG", quality=92)
        except Exception as e:
            print(f"  skip {stem}: {e}")
            continue
        saved += 1
        if saved % 50 == 0:
            print(f"  [{label}] saved {saved}/{target}")
    print(f"  [{label}] done — {saved} images")
    return saved


def fetch(out_dir: Path, n_total: int, dataset_names: List[str], seed: int) -> int:
    try:
        import datasets  # noqa: F401
    except ImportError:
        print("Missing dependency. Run:  pip install datasets pillow")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    chosen = []
    for name in dataset_names:
        if name not in KNOWN_DATASETS:
            print(f"Unknown dataset '{name}'. Available: {list(KNOWN_DATASETS)}")
            return 1
        chosen.append((name, KNOWN_DATASETS[name]))

    # Allocate target per dataset weighted by their approx_size, capped at the
    # caller's n_total. Each dataset still respects its own size ceiling.
    weights = [spec["approx_size"] for _, spec in chosen]
    weight_sum = sum(weights) or 1
    targets = []
    for (name, spec), w in zip(chosen, weights):
        ideal = max(1, int(n_total * w / weight_sum))
        capped = min(ideal, spec["approx_size"])
        targets.append(capped)

    print(f"Target: {n_total} images across {len(chosen)} dataset(s).")
    for (name, _), t in zip(chosen, targets):
        print(f"  {name:8s} target {t}")

    total_saved = 0
    try:
        for (name, spec), t in zip(chosen, targets):
            total_saved += fetch_one_dataset(spec, name, out_dir, t, seed)
    except KeyboardInterrupt:
        print("\nInterrupted — keeping what's been saved.")

    print()
    print(f"Done. {total_saved} images saved to {out_dir.resolve()}")
    if total_saved == 0:
        print("\nNothing saved. Verify network access.")
        return 1

    print("\nNext step:")
    print(f"  python models/digital_cut_paste/synthesize.py \\")
    print(f"      --sources {out_dir} --count 12 \\")
    print(f"      --cross-source --scale-rotate --color-match \\")
    print(f"      --negatives 1 --source-split")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("./sources"),
                    help="Output folder (default: ./sources)")
    ap.add_argument("--n", type=int, default=500,
                    help="Total images to fetch across all chosen datasets (default: 500).")
    ap.add_argument("--datasets", nargs="+", default=DEFAULT_DATASETS,
                    choices=list(KNOWN_DATASETS),
                    help=f"Which datasets to pull from. Default: "
                         f"{' '.join(DEFAULT_DATASETS)}")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    return fetch(args.out, args.n, args.datasets, args.seed)


if __name__ == "__main__":
    sys.exit(main())
