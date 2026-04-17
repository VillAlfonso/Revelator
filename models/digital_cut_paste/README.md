# Digital: Cut and Paste (Splicing)

**Category:** Digital  
**Model ID:** `digital_cut_paste`  
**Public Data Available:** ✅ Yes

---

## Description

Elements copied from one digital image and pasted into another.

---

## Visual Clues to Look For

- Edge artifacts around pasted elements
- Noise pattern inconsistency
- Lighting direction mismatch
- JPEG compression ghosts
- Resolution differences

---

## Recommended Lighting

**MACRO + ELA (Error Level Analysis)**

---

## Forensic Notes

Most studied digital forgery type. ELA reveals areas with different compression levels.

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
digital_cut_paste/
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
cd models/digital_cut_paste
python train.py
```

Or use Google Colab for free GPU.

---

## After Training

1. Copy `weights/best.pt` to main weights folder
2. Update `TRAINING_STATUS["digital_cut_paste"] = True` in main.py
3. Restart server
