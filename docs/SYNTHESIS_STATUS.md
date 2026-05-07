# Indentation Synthesis & Training Status

## Current Progress (May 2, 2026)

### 1. Dataset Generation (IN PROGRESS)
- **Synthesis script**: `models/traced_indentation/synthesize_indentation.py`
- **Real samples**: 24 authenticated indentation samples (from Roboflow)
- **Clean documents**: 49 original + ~150 augmented variations
- **Synthetic forgeries**: ~7,350 (150 variants per clean document)
- **Negatives**: ~30 clean documents with empty labels
- **Status**: Generating images (171+ files created so far)
- **ETA**: ~5-10 minutes total

### 2. Clean Document Augmentation (RUNNING)
- Augmenting 49 existing clean docs to create 200+ total
- Variations: brightness, contrast, blur, rotation
- Will improve negative sample diversity

### 3. Training Ready (NEXT)
Once synthesis completes:
```bash
cd models/traced_indentation
python train_indentation.py --epochs 50 --imgsz 640 --batch 16
```

**Expected results:**
- mAP50: 70-80% (on synthetic validation)
- Real test accuracy: 65-75% (on 4-5 held-out real samples)
- Model saved: `./weights/traced_indentation_model/weights/best.pt`

### 4. Phase 2 Testing (AFTER TRAINING)
Test the single "Scan Document" button with mixed real documents:
```bash
python ../phase2_auto_detect.py --image <test_image.jpg> \
                               --cut-paste-model ../digital_cut_paste/weights/best.pt \
                               --indentation-model ./weights/traced_indentation_model/weights/best.pt
```

Returns: `digital_cut_paste` | `traced_indentation` | `no_forgery_detected`

## Timeline
- **Synthesis**: Running now (~5-10 min)
- **Training**: ~30-60 min (depending on GPU)
- **Phase 2 test**: ~2-3 min per image
- **Total ETA**: 45-75 minutes from now

## For Capstone
All documented in `docs/CAPSTONE_PREP.md`:
- Data sources and ratios
- Synthesis methodology
- Expected accuracy ranges
- How to frame in thesis (Chapters 3 & 4)
- Honest limitations and future work
