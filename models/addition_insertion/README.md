# Addition: Insertion

**Category:** Alteration  
**Model ID:** `addition_insertion`  
**Public Data Available:** ❌ No - requires client samples

---

## Description

Text or characters inserted into existing spaces within a document.

---

## Visual Clues to Look For

- Crowded or cramped characters
- Different ink color/age
- Misaligned baseline
- Inconsistent spacing

---

## Recommended Lighting

**MACRO + UV**

---

## Forensic Notes

Compare ink under UV - different inks fluoresce differently. Check character spacing.

---

## Dataset Requirements

| Requirement | Value |
|-------------|-------|
| Minimum images | 100 |
| Recommended | 300+ |
| Train/Val split | 80/20 |
| Label format | YOLO |
| Image format | JPG, PNG |

---

## Folder Structure

```
addition_insertion/
├── data.yaml           ← Training config
├── train.py            ← Training script
├── README.md           ← This file
├── dataset/
│   ├── images/
│   │   ├── train/      ← Put 80% of images here
│   │   └── val/        ← Put 20% of images here
│   └── labels/
│       ├── train/      ← YOLO .txt labels for train
│       └── val/        ← YOLO .txt labels for val
└── weights/
    └── best.pt         ← Trained model (after training)
```

---

## How to Label

Each image needs a corresponding `.txt` file with same name:

```
image001.jpg  →  image001.txt
image002.png  →  image002.txt
```

Label format (one line per detection):
```
0 0.5 0.5 0.3 0.2
```
Where: `class_id x_center y_center width height` (all normalized 0-1)

Since this is binary detection, class_id is always `0`.

---

## Training

```bash
cd models/addition_insertion
python train.py
```

Or use Google Colab for free GPU.

---

## After Training

1. Copy `weights/best.pt` to main weights folder
2. Update `TRAINING_STATUS["addition_insertion"] = True` in main.py
3. Restart server
