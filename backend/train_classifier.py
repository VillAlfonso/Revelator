"""
Train a local image classifier on the SPECIMEN PICTURES set.

Predicts the specimen CATEGORY (the 14 top-level folder names). At scan time the
app maps the prediction to a Gemini category code (or "other" for categories
outside the 15) and hands it to Gemini as a strong hint, so Gemini only has to
explain / refine -> fewer tokens, category-locked answers.

Goal per the maintainer: near-100% on the specimen folder itself. That is achieved
by memorizing the set (deterministic transform, no augmentation). This is
OVERFITTING by design - great for a demo on these exact images, not a measure of
generalization. Use --val-split > 0 to also see an honest held-out number.

Usage (from backend/, after `pip install torch torchvision`):
    python train_classifier.py                 # train on everything, ~100% on the set
    python train_classifier.py --epochs 20 --batch 48
    python train_classifier.py --val-split 0.15   # also report held-out accuracy

Saves: backend/app/data/specimen_classifier.pt  (weights + class names + metadata)
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image
import torchvision.transforms as T
from torchvision import models

ROOT = Path(__file__).resolve().parent.parent
SPECIMEN_DIR = ROOT / "SPECIMEN PICTURES"
OUT = Path(__file__).resolve().parent / "app" / "data" / "specimen_classifier.pt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# Folders without method subfolders map straight to a class code.
_FOLDER_DEFAULT = {
    "ADDITION": "addition",
    "OBLITERATED WRITING": "obliteration",
    "INDENTED WRITINGS": "sympathetic_indented",
    "SECRET WRITING": "sympathetic_special",
    "COUNTERFEITED-FALSIFIED DOCUMENTS": "counterfeit",
    "CHARRED DOCUMENTS": "charred",
    "WATER SOAKED DOCUMENTS_": "water_soaked",
    "PAPER FOLD": "paper_fold",
    "EMBOSING PRINT": "embossing",
    "TYPEWRITING IDENTIFICAITON": "typewriting",
    "CONTACT WRITING": "contact_writing",
}


def class_for(rel_parts):
    """Map an image path (parts relative to SPECIMEN_DIR) to a forgery-code class.
    The three multi-code folders split by their method subfolders."""
    top = rel_parts[0]
    up = [p.upper() for p in rel_parts]
    if top == "TRACED FORGERY":
        if any("CARBON" in p for p in up): return "traced_carbon"
        if any("CANAL" in p for p in up): return "traced_indentation"
        if any("TRANSMITTED" in p for p in up): return "traced_projection"
        return "traced_carbon"  # images directly under Forged/Genuine: default to primary
    if top == "ERASURE":
        if any("MECHANICAL" in p for p in up): return "erasure_mechanical"
        if any("CHEMICAL" in p for p in up): return "erasure_chemical"
        return "erasure_chemical"
    if top == "MODERN FORGERY":
        if any("CUT" in p for p in up): return "digital_cut_paste"
        if any("DESKTOP" in p for p in up): return "digital_desktop"
        if any("SCAN" in p for p in up): return "digital_scanned"
        return "digital_cut_paste"
    return _FOLDER_DEFAULT.get(top, top)


def build_manifest():
    """Return (samples, classes). samples = [(path, class_idx)]; classes = code names."""
    label_of = {}
    for top in sorted(d.name for d in SPECIMEN_DIR.iterdir() if d.is_dir()):
        for p in (SPECIMEN_DIR / top).rglob("*"):
            if p.suffix.lower() in IMAGE_EXTS and p.is_file():
                label_of[str(p)] = class_for(p.relative_to(SPECIMEN_DIR).parts)
    classes = sorted(set(label_of.values()))
    idx = {c: i for i, c in enumerate(classes)}
    samples = [(path, idx[c]) for path, c in label_of.items()]
    return samples, classes


class SpecimenDataset(Dataset):
    def __init__(self, samples, train: bool):
        self.samples = samples
        # Deterministic transform (no augmentation) so the model can memorize the
        # exact specimen images -> near-100% on the folder.
        self.tf = T.Compose([
            T.Resize((IMG_SIZE, IMG_SIZE)),
            T.ToTensor(),
            T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        path, label = self.samples[i]
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            # Corrupt/unreadable file: fall back to the first sample so the batch
            # stays intact (rare; logged once by the loader if it happens a lot).
            img = Image.open(self.samples[0][0]).convert("RGB")
            label = self.samples[0][1]
        return self.tf(img), label


def build_model(num_classes: int):
    m = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.IMAGENET1K_V2)
    m.classifier[2].p = 0.0  # drop the dropout so the model can fully memorize the set
    in_features = m.classifier[3].in_features
    m.classifier[3] = nn.Linear(in_features, num_classes)
    return m


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    correct = total = 0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        pred = model(x).argmax(1)
        correct += (pred == y).sum().item()
        total += y.numel()
    return correct / max(total, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=35)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--val-split", type=float, default=0.0, help="held-out fraction for an honest number")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not SPECIMEN_DIR.is_dir():
        print(f"ERROR: {SPECIMEN_DIR} not found"); return 2

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", "-", torch.cuda.get_device_name(0) if device == "cuda" else "CPU (slow)")

    samples, classes = build_manifest()
    random.Random(args.seed).shuffle(samples)
    print(f"Classes ({len(classes)}): {classes}")
    print(f"Images: {len(samples)}")

    val = []
    if args.val_split > 0:
        n_val = int(len(samples) * args.val_split)
        val, samples = samples[:n_val], samples[n_val:]
        print(f"Train/val split: {len(samples)} / {len(val)}")

    train_loader = DataLoader(
        SpecimenDataset(samples, train=True), batch_size=args.batch, shuffle=True,
        num_workers=args.workers, pin_memory=(device == "cuda"),
        persistent_workers=args.workers > 0,
    )
    full_loader = DataLoader(  # for the "accuracy on the whole set" report
        SpecimenDataset(samples + val, train=False), batch_size=args.batch, shuffle=False,
        num_workers=args.workers, pin_memory=(device == "cuda"),
    )
    val_loader = DataLoader(
        SpecimenDataset(val, train=False), batch_size=args.batch, shuffle=False,
        num_workers=args.workers, pin_memory=(device == "cuda"),
    ) if val else None

    model = build_model(len(classes)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler(device) if device == "cuda" else None

    print("Training...")
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0 = time.time()
        running = correct = total = 0
        for x, y in train_loader:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            if scaler:
                with torch.amp.autocast("cuda"):
                    out = model(x); loss = loss_fn(out, y)
                scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            else:
                out = model(x); loss = loss_fn(out, y)
                loss.backward(); opt.step()
            running += loss.item() * y.numel()
            correct += (out.argmax(1) == y).sum().item(); total += y.numel()
        tr_acc = correct / max(total, 1)
        msg = f"epoch {epoch:2d}/{args.epochs}  loss {running/max(total,1):.4f}  train-acc {tr_acc:.3f}  ({time.time()-t0:.0f}s)"
        if val_loader:
            msg += f"  val-acc {evaluate(model, val_loader, device):.3f}"
        print(msg)
        sched.step()
        if tr_acc >= 0.999 and not val_loader:
            print("  train accuracy saturated - stopping early."); break

    whole = evaluate(model, full_loader, device)
    print(f"\nAccuracy on the whole specimen set: {whole*100:.1f}%")
    if val_loader:
        print(f"Held-out accuracy (honest): {evaluate(model, val_loader, device)*100:.1f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "classes": classes,
        "arch": "mobilenet_v3_large",
        "img_size": IMG_SIZE,
        "mean": IMAGENET_MEAN, "std": IMAGENET_STD,
        "whole_set_acc": whole,
    }, OUT)
    print(f"Saved -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
