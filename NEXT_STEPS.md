# Next Steps After Synthesis Complete

## 1. Train Indentation Model

Once `models/traced_indentation/synthetic/data.yaml` exists:

```bash
cd models/traced_indentation
python train_indentation.py --epochs 50 --imgsz 640 --batch 16 --device 0
```

**Expected:**
- Training time: 30-60 minutes (with GPU)
- Output: `./weights/traced_indentation_model/weights/best.pt`
- Metrics: mAP50 around 75-85% on synthetic validation

## 2. Hold Out Real Test Samples

The 4-5 real indentation samples NOT used in training are in:
- `models/traced_indentation/train/images/` (original 24 samples)

You can manually test the trained model on these to get real-world accuracy.

## 3. Test Phase 2 Auto-Detection

Once model is trained:

```bash
cd models
python phase2_auto_detect.py --image <path/to/test/image.jpg> \
                             --cut-paste-model digital_cut_paste/weights/best.pt \
                             --indentation-model traced_indentation/weights/traced_indentation_model/weights/best.pt \
                             --conf 0.5
```

**Returns:**
```json
{
  "verdict": "digital_cut_paste" | "traced_indentation" | "no_forgery_detected",
  "confidence": 0.85,
  "details": {...}
}
```

## 4. Gather Thesis Numbers

Collect these for Chapter 4 (Results):
- [ ] Indentation model mAP50 (synthetic validation)
- [ ] Indentation model accuracy on 4-5 held-out real samples
- [ ] Cut-paste model accuracy (already trained)
- [ ] Phase 2 POC test results (25 mixed documents)
  - How many correctly auto-identified as cut-paste?
  - How many as indentation?
  - How many as clean?

## 5. Write Chapter 3 & 4

Use template from `docs/CAPSTONE_PREP.md`:
- Data composition tables
- Synthesis methodology explanation
- Accuracy results with honest limitations
- Phase 2 POC demonstration

## File Locations

- Synthesis script: `models/traced_indentation/synthesize_indentation.py`
- Training script: `models/traced_indentation/train_indentation.py`
- Phase 2 script: `models/phase2_auto_detect.py`
- Real samples: `models/traced_indentation/train/images/` (24 original)
- Synthetic dataset: `models/traced_indentation/synthetic/`
- Documentation: `docs/CAPSTONE_PREP.md`

---

**Total time estimate:**
- Synthesis: ~25 minutes (in progress)
- Training: 30-60 minutes
- Testing Phase 2: 5-10 minutes
- **Total: ~1.5-2 hours**
