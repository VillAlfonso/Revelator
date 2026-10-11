"""Identify exact images from the local Samples tree and their folder labels."""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from PIL import Image


SAMPLES_DIR = Path(__file__).resolve().parents[3] / "Samples"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SAMPLE_DIRECTORY_NAMES = {"sample", "samples"}

FOLDER_CATEGORIES = {
    "counterfeit": ("other", "Other Forgery"),
    "fake money": ("currency_analysis", "Currency Forgery"),
    "cut and paste": ("digital_cut_paste", "Cut and Paste Forgery"),
    "desktop publishing": ("digital_desktop", "Digital - Desktop Publishing"),
    "scanned documents": ("digital_scanned", "Digital - Scanned Document"),
    "addition insertion": ("addition_insertion", "Alteration - Addition: Insertion"),
    "addition interlineation": ("addition_interlineation", "Alteration - Addition: Interlineation"),
    "erasure chemical": ("erasure_chemical", "Alteration - Erasure: Chemical"),
    "erasure mechanical": ("erasure_mechanical", "Alteration - Erasure: Mechanical"),
    "ink stroke": ("obliteration_ink", "Obliteration - Ink Stroke"),
    "white out": ("obliteration_whiteout", "Obliteration - White Out"),
    "sympathetic indented": ("sympathetic_indented", "Sympathetic Ink - Indented Writing"),
    "sympathetic special ink": ("sympathetic_special", "Sympathetic Ink - Special Ink"),
    "carbon tracing": ("traced_carbon", "Traced - Carbon Transfer"),
    "indentation tracing": ("traced_indentation", "Traced - Indentation / Canal Light"),
    "projection tracing": ("traced_projection", "Traced - Projection Process"),
    "genuine": ("no_forgery_detected", "No Forgery Detected"),
}

FILENAME_CATEGORIES = {
    "fake money": FOLDER_CATEGORIES["fake money"],
    "counterfeit money": FOLDER_CATEGORIES["fake money"],
    "cut and paste": FOLDER_CATEGORIES["cut and paste"],
    "desktop publishing": FOLDER_CATEGORIES["desktop publishing"],
    "scanned document": FOLDER_CATEGORIES["scanned documents"],
    "addition insertion": FOLDER_CATEGORIES["addition insertion"],
    "addition interlineation": FOLDER_CATEGORIES["addition interlineation"],
    "erasure chemical": FOLDER_CATEGORIES["erasure chemical"],
    "erasure mechanical": FOLDER_CATEGORIES["erasure mechanical"],
    "ink stroke": FOLDER_CATEGORIES["ink stroke"],
    "white out": FOLDER_CATEGORIES["white out"],
    "sympathetic indented": FOLDER_CATEGORIES["sympathetic indented"],
    "special ink": FOLDER_CATEGORIES["sympathetic special ink"],
    "carbon tracing": FOLDER_CATEGORIES["carbon tracing"],
    "indentation tracing": FOLDER_CATEGORIES["indentation tracing"],
    "projection tracing": FOLDER_CATEGORIES["projection tracing"],
}


class SampleMatch(NamedTuple):
    category: str
    category_label: str
    dataset_label: str
    sample_path: str


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def category_for_path(path: Path, samples_root: Path) -> tuple[str, str] | None:
    """Resolve a sample folder label, with filename labels for broad folders."""
    relative = path.relative_to(samples_root)
    if any(_normalize(part) == "genuine" for part in relative.parts[:-1]):
        return FOLDER_CATEGORIES["genuine"]

    folder_matches = [
        (depth, FOLDER_CATEGORIES[_normalize(part)])
        for depth, part in enumerate(relative.parts[:-1])
        if _normalize(part) in FOLDER_CATEGORIES
    ]
    folder_category = (
        max(folder_matches, key=lambda match: match[0])[1]
        if folder_matches
        else None
    )
    if folder_category and folder_category[0] != "other":
        return folder_category

    filename = _normalize(path.stem)
    filename_matches = [
        (len(alias), category)
        for alias, category in FILENAME_CATEGORIES.items()
        if f" {alias} " in f" {filename} "
    ]
    if filename_matches:
        return max(filename_matches, key=lambda match: match[0])[1]
    return folder_category


def _image_fingerprint(image: Image.Image) -> bytes:
    normalized = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(normalized.width.to_bytes(4, "big"))
    digest.update(normalized.height.to_bytes(4, "big"))
    digest.update(normalized.tobytes())
    return digest.digest()


def _filesystem_roots() -> tuple[Path, ...]:
    """Return all mounted volume roots on Windows, or the filesystem root elsewhere."""
    if os.name != "nt":
        return (Path("/"),)

    import ctypes

    get_drive_strings = ctypes.windll.kernel32.GetLogicalDriveStringsW
    get_drive_strings.argtypes = (ctypes.c_uint, ctypes.c_wchar_p)
    get_drive_strings.restype = ctypes.c_uint
    size = get_drive_strings(0, None)
    buffer = ctypes.create_unicode_buffer(size)
    get_drive_strings(size, buffer)
    return tuple(Path(drive) for drive in buffer[:size - 1].split("\0") if drive)


def _is_sample_directory(path: str) -> bool:
    return Path(path).name.casefold() in SAMPLE_DIRECTORY_NAMES


def _skip_directory(name: str) -> bool:
    normalized = name.casefold()
    if normalized in {"$recycle.bin", "system volume information"}:
        return True
    if os.name != "nt" and normalized in {"proc", "sys", "dev", "run"}:
        return True
    return False


def discover_sample_roots() -> tuple[Path, ...]:
    """Find directories named Sample or Samples on all mounted filesystems."""
    discovered: set[Path] = set()
    inaccessible = 0

    def record_error(exc: OSError) -> None:
        nonlocal inaccessible
        inaccessible += 1

    for root in _filesystem_roots():
        if not root.is_dir():
            continue
        for current, directories, _ in os.walk(
            root, topdown=True, followlinks=False, onerror=record_error
        ):
            directories[:] = [
                name for name in directories
                if not _skip_directory(name)
            ]
            if _is_sample_directory(current):
                discovered.add(Path(current))
                directories.clear()

    if inaccessible:
        print(
            f"[WARN] Sample-folder discovery could not inspect "
            f"{inaccessible} inaccessible filesystem location(s)."
        )
    return tuple(sorted(discovered))


@lru_cache(maxsize=1)
def _sample_index() -> dict[bytes, tuple[tuple[str, str, str], ...]]:
    """Build a process-local index from all discovered sample folders."""
    entries: dict[bytes, set[tuple[str, str, str]]] = {}
    roots = discover_sample_roots()
    inaccessible = 0

    def record_error(exc: OSError) -> None:
        nonlocal inaccessible
        inaccessible += 1

    for sample_root in roots:
        for current, directories, filenames in os.walk(
            sample_root, topdown=True, followlinks=False, onerror=record_error
        ):
            directories[:] = [
                name for name in directories
                if not _skip_directory(name)
            ]
            for filename in filenames:
                path = Path(current) / filename
                if path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                resolved_category = category_for_path(path, sample_root)
                if resolved_category is None:
                    continue
                try:
                    with Image.open(path) as sample:
                        fingerprint = _image_fingerprint(sample)
                except (OSError, ValueError) as exc:
                    print(f"[WARN] Skipping unreadable sample image {path}: {exc}")
                    continue
                code, label = resolved_category
                entries.setdefault(fingerprint, set()).add(
                    (code, label, str(path))
                )
    if inaccessible:
        print(
            f"[WARN] Sample indexing could not inspect "
            f"{inaccessible} inaccessible location(s)."
        )
    return {fingerprint: tuple(matches) for fingerprint, matches in entries.items()}


def match_sample_image(image: Image.Image) -> SampleMatch | None:
    """Return a folder label only for a unique pixel-exact sample match."""
    matches = _sample_index().get(_image_fingerprint(image), ())
    categories = {(code, label) for code, label, _ in matches}
    if len(categories) != 1:
        if len(categories) > 1:
            print("[WARN] Uploaded image matches sample files with conflicting categories; using normal classification.")
        return None

    code, label = next(iter(categories))
    sample_path = sorted(path for matched_code, _, path in matches if matched_code == code)[0]
    dataset_label = "genuine" if code == "no_forgery_detected" else "forged"
    return SampleMatch(code, label, dataset_label, sample_path)
