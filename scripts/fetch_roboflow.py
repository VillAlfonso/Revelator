"""
Pull a Roboflow dataset down into the local YOLOv8 folder layout.

Use this for hand-crafted forgeries you've labeled on Roboflow that you want
to fold into the local training/validation/test splits.

Default usage (matches your existing project):
    python scripts/fetch_roboflow.py --out ./roboflow_dump

Then either:
  • Inspect ./roboflow_dump and copy what you want into
    models/digital_cut_paste/{train,valid,test}/, or
  • Use --merge-into to do that automatically:

    python scripts/fetch_roboflow.py \\
        --merge-into models/digital_cut_paste \\
        --target-split valid

The --merge-into mode appends Roboflow's images+labels into the named split
of an existing local dataset, prefixing filenames with `rf_` so they don't
collide with synthesize.py output.

Requirements:
    pip install roboflow

The API key is read from .env (ROBOFLOW_API_KEY).
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Allow running from anywhere — load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ENV_PATH)
except ImportError:
    pass


VALID_SPLITS = ("train", "valid", "test")


def parse_model_id(model_id: str):
    """ROBOFLOW_CUT_PASTE_MODEL is '<project>/<version>'. Split it."""
    if not model_id or "/" not in model_id:
        return None, None
    proj, ver = model_id.rsplit("/", 1)
    try:
        return proj, int(ver)
    except ValueError:
        return proj, None


def download(workspace: str, project: str, version: int, out_dir: Path) -> Path:
    api_key = os.getenv("ROBOFLOW_API_KEY", "")
    if not api_key:
        print("ROBOFLOW_API_KEY not set in .env. Add it and re-run.")
        sys.exit(1)

    try:
        from roboflow import Roboflow  # type: ignore
    except ImportError:
        print("Missing dependency. Run:  pip install roboflow")
        sys.exit(1)

    print(f"Connecting to Roboflow workspace='{workspace}' project='{project}' v{version}...")
    rf = Roboflow(api_key=api_key)
    rf_project = rf.workspace(workspace).project(project)
    rf_version = rf_project.version(version)

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading YOLOv8 export to {out_dir}/ (this may take a few minutes)...")
    dataset = rf_version.download("yolov8", location=str(out_dir))
    print(f"Done. Local path: {dataset.location}")

    # The SDK puts the dataset under <out_dir>/... varies by version.
    # Walk to find the actual data.yaml.
    yamls = list(Path(dataset.location).rglob("data.yaml"))
    if yamls:
        root = yamls[0].parent
        print(f"data.yaml: {yamls[0]}")
    else:
        root = Path(dataset.location)
    return root


def merge_into(source_root: Path, target_root: Path, target_split: str, prefix: str = "rf_"):
    """Copy source_root/<split>/{images,labels}/* into target_root/<target_split>/{images,labels}/.

    If target_split is 'auto', preserve Roboflow's own split structure.
    """
    if not source_root.exists():
        print(f"Source root not found: {source_root}")
        return

    splits_present = [s for s in VALID_SPLITS if (source_root / s).is_dir()]
    if not splits_present:
        print(f"No train/valid/test folders found in {source_root}.")
        return
    print(f"Roboflow splits present: {splits_present}")

    moved_total = 0
    for src_split in splits_present:
        dst_split = target_split if target_split != "auto" else src_split
        if dst_split not in VALID_SPLITS:
            print(f"Bad target-split '{dst_split}', skipping.")
            continue

        for kind in ("images", "labels"):
            src_dir = source_root / src_split / kind
            dst_dir = target_root / dst_split / kind
            if not src_dir.is_dir():
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            for f in src_dir.iterdir():
                if not f.is_file():
                    continue
                dst = dst_dir / f"{prefix}{f.name}"
                shutil.copy2(f, dst)
                moved_total += 1
        print(f"  {src_split} -> {dst_split}: copied images + labels")

    print(f"\nMerged {moved_total} files into {target_root}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workspace", default="ashenvales-workspace",
                    help="Roboflow workspace slug")
    ap.add_argument("--project", default=None,
                    help="Roboflow project slug. Default: parsed from "
                         "ROBOFLOW_CUT_PASTE_MODEL in .env.")
    ap.add_argument("--version", type=int, default=None,
                    help="Project version number. Default: parsed from "
                         "ROBOFLOW_CUT_PASTE_MODEL in .env.")
    ap.add_argument("--out", type=Path, default=Path("./roboflow_dump"),
                    help="Where to put the downloaded dataset.")
    ap.add_argument("--merge-into", type=Path, default=None,
                    help="If set, after download, copy the data into this "
                         "existing dataset root (e.g. models/digital_cut_paste).")
    ap.add_argument("--target-split", choices=("auto", "train", "valid", "test"),
                    default="valid",
                    help="When --merge-into is used, which split to drop the "
                         "files into. 'auto' preserves Roboflow's splits. "
                         "Default 'valid' is what DATASET_SPEC.md §6 recommends "
                         "for hand-crafted forgeries.")
    args = ap.parse_args()

    # Resolve project / version from env if not given
    if args.project is None or args.version is None:
        env_model = os.getenv("ROBOFLOW_CUT_PASTE_MODEL", "")
        proj, ver = parse_model_id(env_model)
        if args.project is None:
            args.project = proj
        if args.version is None:
            args.version = ver
    if not args.project or not args.version:
        print("Couldn't determine project/version. Pass --project and --version "
              "explicitly, or set ROBOFLOW_CUT_PASTE_MODEL in .env.")
        return 1

    root = download(args.workspace, args.project, args.version, args.out)

    if args.merge_into:
        print()
        merge_into(root, args.merge_into, args.target_split)
        print()
        print("Files prefixed with `rf_` so they won't collide with "
              "synthesize.py output.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
