# Train `digital_cut_paste` on Google Colab — Step-by-Step

Local training on your CPU + AMD iGPU would take days. Google Colab's free
T4 GPU finishes the same job in ~3-6 hours. This is the recommended path.

## What you'll need

- A Google account
- The `digital_cut_paste.zip` file (built locally, instructions below)
- ~10 minutes of attention spread across 6 hours of mostly-unattended
  training

---

## Step 1 — Bundle your dataset

In your Revelator repo:

```bash
python scripts/zip_for_colab.py --category digital_cut_paste
```

This produces `digital_cut_paste.zip` in the repo root. The default
behavior **resizes images to 640px max dimension and re-encodes at
JPEG Q85**, which is what YOLOv8 trains at anyway and shrinks the
zip ~5× without hurting model quality. Expect ~200–300 MB.

If you want full-size images for some reason: `--no-resize` (warning:
zip will be 1+ GB and far less reliable to upload).

---

## Step 2 — Open Colab

1. Go to https://colab.research.google.com/
2. **File → New notebook**
3. **Runtime → Change runtime type → Hardware accelerator: T4 GPU → Save**
   - If T4 isn't free at the moment, fall back to "GPU" with no specific
     model. CPU mode does not work for this dataset.

### Step 2a — Upload the zip (RECOMMENDED: via Google Drive)

Direct drag-and-drop into Colab silently fails on uploads >300 MB.
Use Google Drive instead — it has resumable uploads, so even on a
flaky connection it completes correctly.

1. Open https://drive.google.com → **+ New → File upload** → pick
   `digital_cut_paste.zip`. Wait until the progress bar finishes.
2. Note the file's location in Drive (the default is "My Drive").
3. In Colab, run this in the first cell:

   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   !cp "/content/drive/My Drive/digital_cut_paste.zip" /content/
   !ls -lh /content/digital_cut_paste.zip
   ```

   The size shown should match what `zip_for_colab.py` printed locally.
   If it doesn't, the upload was incomplete — re-upload to Drive.

If your dataset is small (<200 MB) and your connection is reliable,
direct drag-and-drop into the Colab file panel still works.

---

## Step 3 — Run these cells in order

Copy each block into a separate cell and press Shift+Enter to run.

### Cell 1 — Install dependencies

```python
!pip install -q ultralytics==8.1.0
import torch
print("CUDA available:", torch.cuda.is_available())
print("Device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")
```

If "CUDA available: True" — you're set. If False, recheck Step 2's GPU runtime.

### Cell 2 — Unzip dataset

```python
!unzip -q /content/digital_cut_paste.zip -d /content/
!ls /content/digital_cut_paste/
```

You should see `train/`, `valid/`, `test/`, and `data.yaml`.

### Cell 2.5 — Sanity check (DO NOT SKIP)

This catches the silent-truncation failure mode where most of the
dataset goes missing during upload. **Catches the bug that causes
mAP@50 ≈ 0.0008.**

```python
import os
from pathlib import Path

root = Path("/content/digital_cut_paste")
expected = {"train": (4500, 6000), "valid": (1200, 1500), "test": (600, 800)}

ok = True
for split, (lo, hi) in expected.items():
    img_count = len(list((root / split / "images").glob("*.jpg")))
    lbl_count = len(list((root / split / "labels").glob("*.txt")))
    forge_lbls = sum(1 for f in (root / split / "labels").glob("*.txt") if f.stat().st_size > 0)
    print(f"{split:6s}  images={img_count:5d}  labels={lbl_count:5d}  with-bboxes={forge_lbls:5d}", end="")
    if img_count < lo:
        print(f"  ⚠️  EXPECTED {lo}-{hi}, GOT {img_count}")
        ok = False
    else:
        print("  ✓")

if not ok:
    print("\n❌ DATASET INCOMPLETE — likely a truncated upload.")
    print("Check /content/digital_cut_paste.zip size matches what zip_for_colab.py printed.")
    print("If it doesn't, re-upload via Google Drive (Step 2a).")
else:
    print("\n✓ Dataset looks complete. Proceed.")
```

If the check fails, fix the upload before proceeding. Training on an
incomplete dataset wastes hours.

### Cell 3 — Fix data.yaml paths for Colab

```python
# data.yaml from synthesize.py uses an absolute Windows path; rewrite
# it to match the Colab filesystem.
yaml_path = "/content/digital_cut_paste/data.yaml"
with open(yaml_path, "w") as f:
    f.write(
        "path: /content/digital_cut_paste\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "\n"
        "nc: 1\n"
        "names:\n  0: cut_paste\n"
    )
print(open(yaml_path).read())
```

### Cell 4 — Train

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")          # nano = good speed/quality on T4
results = model.train(
    data="/content/digital_cut_paste/data.yaml",
    epochs=150,
    imgsz=640,
    batch=16,
    device=0,
    project="/content/runs",
    name="digital_cut_paste",

    # Document-tuned augmentation
    hsv_h=0.015, hsv_s=0.5, hsv_v=0.3,
    degrees=3.0, translate=0.1, scale=0.15,
    flipud=0.0, fliplr=0.3, mosaic=0.8,

    patience=30,
    save=True, save_period=10,
    val=True, plots=True, verbose=True,
)
```

This is the long-running cell — expect 3–6 hours on T4. Keep the tab
open or Colab will time out. Tip: open a YouTube tab playing background
audio in another window — that keeps the browser session active.

The `patience=30` setting means training auto-stops if validation loss
doesn't improve for 30 epochs in a row, so you may finish well before
150 epochs.

### Cell 5 — Tune the confidence threshold

After training, sweep the threshold on the validation set and pick the
one that maximizes F1.

```python
from ultralytics import YOLO

best = "/content/runs/digital_cut_paste/weights/best.pt"
m = YOLO(best)

print(f"{'conf':>6} {'P':>8} {'R':>8} {'F1':>8}  {'mAP50':>8}")
for c in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    metrics = m.val(
        data="/content/digital_cut_paste/data.yaml",
        conf=c, split="val", verbose=False, plots=False,
    )
    p, r = metrics.box.mp, metrics.box.mr
    f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    print(f"{c:6.2f} {p:8.3f} {r:8.3f} {f1:8.3f}  {metrics.box.map50:8.3f}")
```

**Pick the conf with the highest F1.** Forgery detectors usually peak
around 0.20–0.30.

### Cell 6 — Final test set numbers (run ONCE)

This is the honest measure of how the model generalizes — including
your 18 hand-crafted real forgeries that live in test/.

```python
from ultralytics import YOLO

best = "/content/runs/digital_cut_paste/weights/best.pt"
m = YOLO(best)

# Use the conf you picked from Cell 5
chosen_conf = 0.25  # ← CHANGE THIS to your Cell 5 winner

metrics = m.val(
    data="/content/digital_cut_paste/data.yaml",
    conf=chosen_conf, split="test", verbose=True, plots=True,
)
print(f"\n=== TEST SET RESULTS @ conf={chosen_conf} ===")
print(f"Precision : {metrics.box.mp:.3f}")
print(f"Recall    : {metrics.box.mr:.3f}")
print(f"mAP@50    : {metrics.box.map50:.3f}")
print(f"mAP@50-95 : {metrics.box.map:.3f}")
```

**Don't run this cell more than once.** The whole point of a test set
is that you only look at it once, after picking the conf threshold —
otherwise you've contaminated the test set with hyperparameter
selection bias and the numbers stop being honest.

### Cell 7 — Download the trained weights

```python
from google.colab import files
files.download("/content/runs/digital_cut_paste/weights/best.pt")
```

This downloads `best.pt` (~6 MB) to your local Downloads folder.

---

## Step 4 — Drop the weights into your local Revelator

Copy the downloaded `best.pt` into:

```
C:\Revelator\models\digital_cut_paste\weights\best.pt
```

(create the `weights/` folder if it doesn't exist).

The Revelator runtime auto-detects local weights on next backend
startup. The dispatch order — local YOLO first, Roboflow only as
fallback — means your trained model immediately replaces the Roboflow
hosted call for `digital_cut_paste`. No `.env` change required.

Also write down your chosen conf threshold from Cell 5. Update
`.env` with:

```
CONFIDENCE_THRESHOLD=0.25   # or whatever your Cell 5 winner was
```

Restart the backend. Your locally-trained, tuned model is live.

---

## Expected results

With the current dataset (~6,500 examples, source-split, all
synthesize.py extensions enabled, 18 hand-crafted real forgeries in
val and test), realistic test-set numbers:

| Metric | Realistic | Stretch |
|---|---|---|
| Precision | 0.78–0.86 | 0.90+ |
| Recall    | 0.72–0.82 | 0.88+ |
| F1        | 0.77–0.83 | 0.89+ |
| mAP@50    | 0.75–0.85 | 0.90+ |

If your numbers are dramatically worse than these — say P < 0.65 — the
likely cause is too few negatives, not too few forgeries. Re-run
`synthesize.py` with `--negatives 2` (instead of 1) and re-train.

If your numbers on the test set are dramatically *better* than on
validation, the test set may have leaked into training — verify that
the `rf_*` files only appear in valid/test, never in train.

---

## Troubleshooting

**"CUDA out of memory" during training**
Reduce batch size: `batch=8` or `batch=4`.

**"Disconnected" warning**
Colab disconnects idle sessions. Stay on the tab, or use the
"keep-alive" trick (play YouTube in a side tab).

**Training stalls / loss isn't decreasing**
Verify the dataset unzipped correctly — `!ls /content/digital_cut_paste/train/images | wc -l` should report ~4,500. If far fewer, the unzip
failed (zip likely corrupted on upload — try again).

**"No labels found"**
The data.yaml in Cell 3 didn't get written. Re-run Cell 3.

**Want to resume after disconnect**
Last checkpoint is in `/content/runs/digital_cut_paste/weights/last.pt`.
Pass `model = YOLO("/content/runs/digital_cut_paste/weights/last.pt")` and
`resume=True` to `model.train(...)`.
