# Digital Cut-and-Paste — Dataset Specification

This document is the operating manual for building the training dataset that
powers the `digital_cut_paste` YOLOv8 detector. It is written as a checklist
you can execute against, not as theory.

The detector has two equally important jobs:

1. **Detect** — when a document contains a cut-and-paste forgery, draw a
   bounding box around it.
2. **Stay quiet** — when a document does NOT contain one, output zero
   detections. No phantom boxes on signatures, stamps, watermarks, folds,
   coffee stains, or compression artifacts.

The single biggest mistake in detection training is optimizing only for (1).
A model that fires on every document is not a forensic tool — it's a stamp
that says FORGED on everything. The plan below treats positives and
negatives as equally important.

---

## 1. Headline Targets

| Metric                    | Minimum viable | **Recommended** | Strong |
|---------------------------|---------------:|----------------:|-------:|
| Unique source documents   | 150            | **300**         | 600+   |
| Synthesized forgeries     | 1,500          | **4,500**       | 9,000+ |
| Clean negatives (no fake) | 600            | **1,800**       | 3,600+ |
| **Total dataset size**    | **~2,100**     | **~6,300**      | **~12,600** |
| Train / valid / test      | 70 / 20 / 10   | 70 / 20 / 10    | 70 / 20 / 10 |
| Positive : negative ratio | ~2.5 : 1       | ~2.5 : 1        | ~2.5 : 1 |
| Per-source synth count    | 8–12           | 12–15           | 15–20  |

Why **2.5 : 1 positives-to-negatives**? YOLOv8 needs more positives to learn
the bbox regression head, but a 1:0 ratio (the default if you only run
synthesize.py) produces a model that hallucinates. ~30% negatives is the
sweet spot for high precision without starving the recall head.

Why "unique source documents" matters more than total image count: the model
generalizes across the variance in your *source set*, not across the
permutations synthesize.py produces from a single source. 1,000 forgeries
made from 10 sources will overfit. 1,000 forgeries made from 200 sources
will generalize.

---

## 2. Source Variance Grid

The source set must hit **every cell of this grid** at least 5 times. If a
cell is empty, you are deploying blind to that condition.

### 2.1 Document Type (rows)

| # | Type | Why it matters |
|---|------|----------------|
| 1 | Government ID (driver's license, passport, national ID) | High-stakes target for forgery; rigid layout |
| 2 | Academic certificate / diploma / transcript | Common forgery target; handwriting + print mix |
| 3 | Bank cheque / financial form | Numerical fields are #1 forgery hotspot |
| 4 | Receipt (printed thermal, dot-matrix, modern POS) | Different ink technologies = different artifacts |
| 5 | Contract / legal letter (multi-paragraph print) | Tests the model on long-text body |
| 6 | Handwritten letter / note | Pure handwriting; very different texture from print |
| 7 | Form (tax, application, medical) | Mixed fields, checkboxes, signatures |
| 8 | Currency / banknote | Fine-line patterns; specific to currency forgery class but valuable here |
| 9 | Business card / small printed material | Tests small-input edge case |
| 10| Notarized document with stamps and seals | Stamps create texture similar to bad paste — critical for negatives |

### 2.2 Capture Modality (columns)

| # | Modality | Why it matters |
|---|----------|----------------|
| A | Flatbed scan, 300 DPI | Cleanest baseline |
| B | Flatbed scan, 600 DPI | High-res — different JPEG behavior |
| C | Mobile phone, well-lit overhead | Realistic real-world capture |
| D | Mobile phone, side-lit / shadowed | Shadow gradients — common false-positive trigger |
| E | Mobile phone, low light + flash | Flash hotspot artifacts — false-positive trigger |
| F | Mobile phone, screen photographed (moiré) | Moiré patterns can fool ELA |
| G | Compressed social-media re-share (Facebook, Messenger) | Triple-compression noise |
| H | Photocopy of document, then scanned | Copy-of-a-copy degradation |

### 2.3 Filling the Grid

For each (Type, Modality) pair you can fill, collect at least **5 unique
samples**. 10 types × 8 modalities × 5 = 400 unique sources at full
coverage. Recommended target of 300 means you can leave ~20% of cells
empty — pick which gaps you can live with based on use case (e.g. if
Revelator will mainly process mobile photos, weight C, D, E heavier and
let cell F slide).

### 2.4 Additional Variance Dimensions (sample broadly)

These are not separate cells — they're things to vary *within* each cell:

- **Languages / scripts:** at minimum, mix Tagalog, English, Filipino
  forms. Real Filipino forensic targets will be bilingual or trilingual.
- **Resolution:** spread from 1024×768 (low) to 4032×3024 (phone) to
  6000×4000 (DSLR/scanner). Don't normalize before training — YOLOv8
  resizes internally and you want it to see real-world resolution variance.
- **Background:** white, wood desk, fabric, cluttered, dark surface.
- **Document age / wear:** crisp new prints, folded, creased, slightly
  yellowed, stained.
- **Signatures present / absent:** signatures look texturally similar to
  forgery edges — the model MUST see signed clean documents.
- **Stamps & seals present / absent:** same reason. Critical for negatives.
- **Watermarks present:** translucent text/logos look like ghost paste-overs.

---

## 3. Negative Samples — The Single Most Important Section

A YOLOv8 dataset uses **empty label files** as negatives. If `image_001.jpg`
has no corresponding `.txt` (or a `.txt` with no lines), the trainer learns
"do not predict anything here." This is how you suppress false positives.

### 3.1 Three classes of negatives you need

**(a) Clean originals — ~30% of negatives**

For every source document you synthesize, also include the unmodified
original in the dataset with an empty label. This teaches the model
"clean version of THIS layout has no forgery", so when you process a
real submission of the same layout, the model trusts a clean instance.

**(b) Hard negatives — ~50% of negatives**

Documents with naturally-occurring artifacts that visually resemble
cut-paste seams. These are the false positives a poorly trained model
will produce on real data:

- Documents with **stamps or seals** — the embossed rectangle has hard
  edges similar to a paste boundary.
- Documents with **glued or stapled** add-ons (e.g. photo on an ID,
  receipt taped to a form).
- **Multi-language documents** where a different script abruptly appears.
- Documents on **patterned backgrounds** (lined paper, graph paper,
  letterhead with logo bands).
- Documents with **highlighter / colored ink annotations** — color shifts
  trigger ELA hotspots.
- Documents with **water damage, fold lines, creases, coffee stains**.
- **Photocopies** — already have block-grid recompression artifacts that
  look like cut-paste under naive ELA.
- Documents with **white-out or correction tape** — texturally similar to
  paste-over.

**(c) Out-of-domain negatives — ~20% of negatives**

A small sample of NON-document images mislabeled as documents (because the
document gate may fail open). This trains the YOLO head to also stay quiet
on these:

- Photos with text in them (street signs, food packaging, book covers
  on a shelf).
- Screenshots of websites/apps that contain text but aren't documents.
- Stock photos of people holding paperwork.

**Don't go overboard here — ~5% of total dataset is enough.**

### 3.2 Synthesize.py extension needed (recommended)

Currently `synthesize.py` only emits forged images. It needs a
`--negatives N` mode that copies the unmodified source into the dataset
with an empty `.txt` label. See §6.2 for the patch.

Until that exists, you can produce negatives manually:

```bash
# After running synthesize.py:
for img in sources/*.jpg; do
  cp "$img" train/images/$(basename "$img" .jpg)_clean.jpg
  : > train/labels/$(basename "$img" .jpg)_clean.txt   # empty file
done
```

(That bash works in Git Bash on Windows. PowerShell equivalent in §10.)

---

## 4. Per-Source Synthesize Count — Tuned for Quality

`synthesize.py --count N` controls how many forged versions to make per
source. Don't use a flat number across all sources — match the count to
the source's information density.

### 4.1 Decision table

| Source quality                          | Width      | Text density | **Count** | Notes |
|-----------------------------------------|-----------:|--------------|----------:|-------|
| Premium scan, dense text (contract)     | 2400px+    | High         | **18–20** | Lots of unique patches to extract |
| Standard scan / good phone photo        | 1500–2400  | Medium-high  | **12–15** | The default working tier |
| Mobile photo, decent                    | 1000–1500  | Medium       | **8–10**  | Limited region diversity |
| Lower-res or sparse content (ID card)   | 700–1000   | Low          | **5–7**   | Small canvas; few non-overlapping spots |
| Very low-res or near-blank              | <700       | Very low     | **2–3**   | Or skip entirely |

Reasoning: synthesize.py picks a random text-rich region per call. On a
dense contract there are ~50 distinct sentence-sized regions; on a thin
ID card there might be ~6. Generating 20 forgeries from an ID card
guarantees near-duplicates, which inflate apparent dataset size without
adding learning signal — and worse, can make the model overfit to that
specific layout.

### 4.2 Run synthesize.py multiple times per source-set with different patch sizes

Variety in **patch size** is one of the highest-leverage knobs. Real
cut-paste forgeries are not always 100×100 px — they're sometimes a single
word (50px) and sometimes a full address block (350px). Run the script
**three times** per source set with different sizes:

```bash
# Pass 1 — small patches: single words, dates, numbers
python synthesize.py --sources ./sources --out ./out_small \
    --patch-min 30 --patch-max 100 --count <half of recommended>

# Pass 2 — medium patches: sentences, signatures (DEFAULT band)
python synthesize.py --sources ./sources --out ./out_medium \
    --patch-min 80 --patch-max 220 --count <recommended>

# Pass 3 — large patches: paragraphs, address blocks, photo-on-ID
python synthesize.py --sources ./sources --out ./out_large \
    --patch-min 200 --patch-max 400 --count <half of recommended>
```

Then merge the three `out_*/train/images/` (etc.) into a single dataset
folder. Expected total per source = **2× the recommended count** (because
small + large together = roughly 1× of the medium pass).

### 4.3 Use multiple `--seed` values

Run each pass twice with different `--seed` values (e.g. 42 and 1337). The
random patch positions and perturbations differ per seed, doubling your
per-source variety without you needing more sources.

### 4.4 Ballpark formula

For a source set of S documents at recommended density:

```
Forgeries  = S × 12      (mid-tier per-source count)
            × 3           (small + medium + large patches)
            × 2           (two seeds)
           = S × 72
```

So 100 sources → ~7,200 forgeries. That's *more* than the 4,500 in §1's
"recommended" target, which means with 100 well-chosen sources you can
hit recommended-tier dataset size. Quality of source set still beats
quantity of synthesis.

---

## 5. Gaps in `synthesize.py` Worth Addressing

The current `synthesize.py` produces a solid baseline but five gaps
matter for the quality bar you're targeting. None block training; all
improve generalization.

### 5.1 Cross-source splicing (HIGH priority)

**Current:** Patches are cut from the same image they're pasted onto.

**Why it matters:** Real forgers paste content **from a different document**.
The artifacts are different — color cast mismatch, paper texture mismatch,
font subtly different, lighting from a different angle. A model trained
only on same-source splices will under-perform on real cross-source
forgeries because it never saw that distribution shift.

**Patch:** Add a `--cross-source` flag. When enabled, the donor patch is
sampled from a *different* source image in the folder. Implement by
keeping a list of all loaded sources and sampling `donor_img != current_img`
per forgery.

### 5.2 Scale and rotation perturbations (HIGH priority)

**Current:** Patches are pasted at original size, no rotation.

**Why it matters:** Real forgers resize/rotate to fit the target context.
The size mismatch creates a tell-tale anti-aliasing edge that the model
should learn.

**Patch:** Before pasting, with 50% probability:
- Resize patch by `random.uniform(0.85, 1.20)`
- Rotate patch by `random.uniform(-3, 3)` degrees with bilinear resampling

### 5.3 Color-matching (MEDIUM priority)

**Current:** Patches keep original color.

**Why it matters:** Sophisticated forgers color-correct the patch to match
the destination. The hardest forgeries to detect are color-matched. The
model needs to see this case to learn the *remaining* signals (compression
mismatch, edge halos) when color is no longer a tell.

**Patch:** With 25% probability, after picking the destination, sample the
mean RGB of a small region around the destination and shift the patch's
mean RGB toward it by 50%.

### 5.4 Multi-region forgeries (LOW priority)

**Current:** Each forgery has exactly one paste region.

**Why it matters:** Some real forgeries patch multiple fields (date AND
amount on a cheque, for instance). The detector should handle multi-bbox
output. YOLOv8 itself is fine with multi-instance per image, but it must
have seen multi-instance training examples.

**Patch:** With 15% probability, paste 2–3 regions per image. Emit
multiple bbox lines in the label file.

### 5.5 Negative-sample emission (HIGH priority — already mentioned in §3.2)

Add `--negatives N` flag: copies N unmodified source images into the
dataset with empty label files. Without this, you do the negative-sample
copying by hand.

### 5.6 Suggested signature line for the extended script

```
synthesize.py --sources DIR --count N
              [--patch-min INT] [--patch-max INT]
              [--cross-source]                 # 5.1
              [--scale-rotate]                 # 5.2
              [--color-match]                  # 5.3
              [--multi-region-prob FLOAT]      # 5.4
              [--negatives N]                  # 5.5  — copies clean originals
              [--seed INT]
```

I can implement these on request.

---

## 6. Real Forgeries — Don't Skip Them

Synthesized forgeries cover the distribution machine-learning models can
*recognize easily*. They miss the artifacts a determined human creates.
Your dataset should include **at least 100 hand-crafted real forgeries**
in the train/val sets:

1. Open clean documents in Photoshop / GIMP.
2. Manually splice content using normal forger workflow:
   - Copy a date from one receipt onto another.
   - Replace an amount on a cheque with content from a different cheque.
   - Swap a name or signature on a contract.
3. Save at typical web-quality JPEG (85–90).
4. Hand-annotate with the bbox where you placed the patch.

These should go in the **validation and test** splits primarily — use them
as the honest measure of whether the model generalizes from synthesized
to real forgeries.

**Recommended split:**
- Train: 0–20 real forgeries (kept low so synth dominates the gradient)
- Valid: 30–40 real forgeries (this is where you check overfitting)
- Test:  40–60 real forgeries (final reported numbers come from here)

---

## 7. Validation Set Design

The validation set is the most important part of the dataset because it's
the one you'll use to decide if a checkpoint is good. Get this wrong and
you ship a model that scored 95% on val but performs poorly in production.

### 7.1 Holdout principle

Never let a source document appear in both train and val. If
`drivers_license_007.jpg` is in train, every forgery synthesized from it
must be in train. If it's in val, every forgery must be in val. Otherwise
you're testing on near-identical layouts the model has memorized.

`synthesize.py` currently splits *forgeries*, not *sources*. Fix this by
either:
- Pre-splitting your sources folder into `sources/train/`, `sources/valid/`,
  `sources/test/` and running synthesize.py three times (one per split).
- Or post-processing: read the dataset, group by source-image stem, then
  reassign all forgeries from a given stem into a single split.

### 7.2 Validation set composition

The val set should mirror the real-world distribution you'll deploy to:

| Component | Recommended share | Source |
|-----------|------------------:|--------|
| Synthesized forgeries (held-out sources) | 50% | synthesize.py output |
| Hand-crafted real forgeries | 20% | §6 |
| Clean documents (negatives) | 25% | §3 |
| Hard-negative cases (stamps/seals/etc.) | 5%  | §3.1(b) |

### 7.3 Test set is sacred

Keep a **test set you never look at during development**. ~10% of the
dataset, drawn from the holdout-source pool. Run it once, before your
defense, and report those numbers. Looking at the test set during dev
defeats the entire point of having one.

---

## 8. Hallucination-Prevention Checklist

Concrete things you must do (or check) before you start training:

- [ ] **Negatives present in dataset.** Run
      `find train -name "*.txt" -size 0 | wc -l`. If the result is 0, you
      have no negatives and the model will hallucinate. Target: ~30% of
      `train/labels/*.txt` should be empty (size-0).

- [ ] **Source-level holdout.** No source-image basename appears in both
      `train/images/` and `valid/images/`.

- [ ] **Bounding boxes are tight.** Spot-check 20 random labels by drawing
      them on the image. Loose boxes (much larger than the actual patch)
      teach the model to predict large boxes everywhere.

- [ ] **Class imbalance is not extreme.** Should be roughly 70/30
      forged/clean in the train split, not 99/1.

- [ ] **Real forgeries in val and test.** §6.

- [ ] **Hard negatives present.** Stamps, signatures, watermarks, folds,
      photocopies — at least 10 examples of each type with empty labels.

- [ ] **Confidence threshold tuning.** After training, sweep `conf` from
      0.10 to 0.50 on the validation set. Pick the threshold that
      maximizes F1, not the one ultralytics defaults to. Set it as
      `CONFIDENCE_THRESHOLD` in `.env`.

- [ ] **Test on out-of-distribution images.** Run inference on 20 images
      that are NOT documents (memes, food photos, screenshots) and
      verify the YOLO head returns 0 boxes for all of them. The
      document gate should catch these earlier, but YOLO should still
      stay quiet as a second line of defense.

---

## 9. Annotation Quality Bar

`synthesize.py` produces perfect labels by construction (it knows exactly
where it pasted). For real forgeries (§6) and hard negatives where you
need bboxes, follow these rules:

- **Tight, not loose.** The bbox should hug the pasted region's outer
  edge. Don't pad.
- **Include any visible halo.** If the paste has a 5-pixel feather, the
  bbox includes it.
- **One bbox per region.** Don't use one big bbox to cover two separated
  pastes — split them.
- **Class id is always 0.** This is a single-class detector.
- **YOLO-normalized format.** `cls cx cy w h` all in `[0, 1]`. `synthesize.py`
  emits this; manual annotation tools (Roboflow Annotate, LabelImg,
  CVAT) all support YOLOv8 export.

Use Roboflow Annotate if you have an account — it's the smoothest path
and the export format matches `synthesize.py`'s output exactly.

---

## 10. Execution Plan

Concrete order of work:

### Phase 1 — Sources (1–3 days, the gating step)

1. Decide your three highest-priority document types (e.g. ID + receipt +
   contract for a Filipino capstone).
2. Collect 50 unique sources for each. Use the §2 grid — fill modality
   coverage as you collect, not after.
3. Verify with `pip-installable` tools or PIL that all images open and
   are RGB.

### Phase 2 — Source-level split (1 hour)

```
sources/
├── train/   ← 70% of your sources
├── valid/   ← 20%
└── test/    ← 10%
```

**Important:** assign by source basename, not randomly within a folder.
Use Python:

```python
import random, shutil
from pathlib import Path
random.seed(42)

src = Path("sources_unsplit")
all_files = sorted(src.glob("*.jpg"))
random.shuffle(all_files)
n = len(all_files)
splits = {"train": all_files[:int(n*0.7)],
          "valid": all_files[int(n*0.7):int(n*0.9)],
          "test":  all_files[int(n*0.9):]}
for name, files in splits.items():
    Path(f"sources/{name}").mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy(f, f"sources/{name}/{f.name}")
```

### Phase 3 — Synthesize (4–8 hours of compute, mostly unattended)

For each of train, valid, test, run §4.2's three passes. Example for the
train split:

```bash
python synthesize.py --sources ./sources/train --out ./datasets/dcp_small  --patch-min 30  --patch-max 100 --count 6  --seed 42
python synthesize.py --sources ./sources/train --out ./datasets/dcp_med    --patch-min 80  --patch-max 220 --count 12 --seed 42
python synthesize.py --sources ./sources/train --out ./datasets/dcp_large  --patch-min 200 --patch-max 400 --count 6  --seed 42

python synthesize.py --sources ./sources/train --out ./datasets/dcp_small2 --patch-min 30  --patch-max 100 --count 6  --seed 1337
python synthesize.py --sources ./sources/train --out ./datasets/dcp_med2   --patch-min 80  --patch-max 220 --count 12 --seed 1337
python synthesize.py --sources ./sources/train --out ./datasets/dcp_large2 --patch-min 200 --patch-max 400 --count 6  --seed 1337
```

Repeat for valid and test (smaller `--count`, e.g. 3/6/3 instead of 6/12/6).

### Phase 4 — Merge + Negatives (30 min)

Merge all `out_*/train/images/*.jpg` into a single
`models/digital_cut_paste/train/images/` (and the matching labels).
Then add negatives:

```bash
# Clean originals as negatives (~30% of negatives)
for img in sources/train/*.jpg; do
  base=$(basename "$img" .jpg)
  cp "$img" "models/digital_cut_paste/train/images/${base}_clean.jpg"
  : > "models/digital_cut_paste/train/labels/${base}_clean.txt"
done

# Hard negatives (you collect these separately and copy in)
# Out-of-domain negatives (handful of non-document images)
```

PowerShell version of the loop:
```powershell
Get-ChildItem sources/train/*.jpg | ForEach-Object {
    $base = $_.BaseName
    Copy-Item $_.FullName "models/digital_cut_paste/train/images/${base}_clean.jpg"
    New-Item "models/digital_cut_paste/train/labels/${base}_clean.txt" -ItemType File -Force | Out-Null
}
```

### Phase 5 — Sanity check (30 min)

Run the §8 hallucination-prevention checklist. Don't skip this —
catching a class-imbalance issue here saves a 4-hour wasted training run.

### Phase 6 — Train (4–8 hours on Colab T4)

```bash
cd models/digital_cut_paste
python train.py --epochs 150 --batch 16 --imgsz 640
```

150 epochs (vs. the default 100) because you have a larger dataset and
the held-out validation set will tell you when to stop via early
stopping (`patience=30` in train.py). Monitor val loss — if it climbs
for 30 consecutive epochs, the run terminates and the best checkpoint
is restored automatically.

### Phase 7 — Threshold tuning (1 hour)

After training, sweep confidence threshold on validation set:

```python
from ultralytics import YOLO
model = YOLO("weights/best.pt")
for conf in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    metrics = model.val(data="data.yaml", conf=conf, split="val")
    print(f"conf={conf:.2f}  P={metrics.box.mp:.3f}  R={metrics.box.mr:.3f}  F1={2*metrics.box.mp*metrics.box.mr/(metrics.box.mp+metrics.box.mr):.3f}")
```

Pick the threshold that maximizes F1 — typically around 0.20–0.30 for
forgery detectors. Set it in `.env` as `CONFIDENCE_THRESHOLD=...`.

### Phase 8 — Test set + Deploy (30 min)

Run the test set ONCE for your reported numbers. Copy `weights/best.pt`
to the location the runtime expects (`models/digital_cut_paste/weights/best.pt`
already, so no move needed) and restart the backend.

---

## 11. Expected Outcomes

With recommended-tier dataset (300 sources, 4,500 forgeries, 1,800
negatives) and the §5 synthesize.py extensions applied, expect:

| Metric (test set) | Realistic | Stretch |
|-------------------|-----------|---------|
| Precision (no false positives) | 0.80–0.88 | 0.92+ |
| Recall (catches forgeries)     | 0.72–0.82 | 0.88+ |
| F1                             | 0.78–0.84 | 0.90+ |
| mAP@50                         | 0.75–0.85 | 0.90+ |

If precision is below 0.75 in early runs, the fix is **more negatives**,
not more forgeries. If recall is below 0.65, the fix is **more source
diversity** (§2 grid coverage), not more synthesis count.

The model will not be perfect. Forgery detection at 0.95 precision on
real-world documents is a research-level result, not a capstone result.
Your defense should explicitly position the tool as a **screening
assistant** that complements human forensic examination, not as a
replacement for it. The About page (§verdict_meaning) already does this
correctly — keep that framing in any presentation slides.

---

## 12. After Cut-and-Paste — Reusing This Spec

This spec is written for `digital_cut_paste` but the structure transfers.
For other categories you'll change:

- §2 source types (e.g. for `obliteration_*` you need documents with
  white-out, ink scribbles, etc.)
- §5 synthesize.py extensions (each forgery type has a different
  artifact-generation strategy)
- §8 hallucination triggers (different per category)

The §3 negatives strategy and §7 validation-design rules are universal.
Re-apply them verbatim for every category.

---

*Last updated: keep this in sync with `synthesize.py` and `train.py`.
When the script gains new flags, list them in §5.6.*
