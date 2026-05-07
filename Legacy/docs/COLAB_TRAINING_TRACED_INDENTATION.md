# Training Traced Indentation Model on Colab

Guide for training YOLOv8 on the traced indentation dataset using Google Colab (free GPU).

---

## **Step 1: Prepare Dataset Locally**

### Create YOLO Format Structure

Your dataset should be organized like this:
```
traced_indentation_dataset/
├── images/
│   ├── train/
│   │   ├── real_001.jpg
│   │   ├── syn_000_000.jpg
│   │   ├── clean_001.jpg
│   │   └── ...
│   ├── val/
│   └── test/
├── labels/
│   ├── train/
│   │   ├── real_001.txt (YOLO format)
│   │   ├── syn_000_000.txt
│   │   ├── clean_001.txt (empty for clean docs)
│   │   └── ...
│   ├── val/
│   └── test/
└── data.yaml
```

### Run This Script to Organize

```bash
python << 'EOF'
from pathlib import Path
import shutil
import random

# Paths
synthetic_dir = Path("/c/Revelator/models/traced_indentation/synthetic")
clean_dir = Path("/c/Revelator/Clean/Datasets1")
output_dir = Path("/c/Revelator/traced_indentation_dataset")

# Create output structure
for split in ["train", "val", "test"]:
    (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
    (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

# Gather all files
real_images = list(Path("/c/Revelator/models/traced_indentation/extracted_real/train/images").glob("*.jpg"))
synthetic_images = list(synthetic_dir.glob("**/*.jpg"))
clean_images = list(clean_dir.glob("*.jpg"))

print(f"Real: {len(real_images)}")
print(f"Synthetic: {len(synthetic_images)}")
print(f"Clean: {len(clean_images)}")

# Shuffle and split 70/20/10
all_data = [
    ("traced", img) for img in real_images + synthetic_images
] + [
    ("clean", img) for img in clean_images
]

random.shuffle(all_data)

train_split = int(len(all_data) * 0.7)
val_split = int(len(all_data) * 0.9)

splits = {
    "train": all_data[:train_split],
    "val": all_data[train_split:val_split],
    "test": all_data[val_split:],
}

# Copy files
for split, data in splits.items():
    for data_type, img_path in data:
        # Copy image
        dest_img = output_dir / "images" / split / img_path.name
        shutil.copy(img_path, dest_img)
        
        # Create label file
        label_path = output_dir / "labels" / split / img_path.stem + ".txt"
        
        if data_type == "traced":
            # Find corresponding label from synthetic
            orig_label = None
            for lbl in synthetic_dir.glob("**/*.txt"):
                if lbl.stem == img_path.stem:
                    orig_label = lbl
                    break
            
            if orig_label and orig_label.exists():
                shutil.copy(orig_label, label_path)
            else:
                # For real images, create label if missing
                label_path.write_text("0 0.5 0.5 0.8 0.8\n")  # placeholder
        else:
            # Clean docs = no objects (empty label)
            label_path.write_text("")

print(f"\nTrain: {len(list((output_dir / 'images' / 'train').glob('*')))}")
print(f"Val: {len(list((output_dir / 'images' / 'val').glob('*')))}")
print(f"Test: {len(list((output_dir / 'images' / 'test').glob('*')))}")
EOF
```

### Create data.yaml

```bash
cat > /c/Revelator/traced_indentation_dataset/data.yaml << 'EOF'
path: /content/gdrive/MyDrive/traced_indentation_dataset
train: images/train
val: images/val
test: images/test

nc: 1
names: ['traced_indentation']
EOF
```

---

## **Step 2: Upload to Google Drive**

1. Go to **Google Drive** → Create folder `traced_indentation_dataset`
2. Upload the folder structure:
   ```
   My Drive/
   └── traced_indentation_dataset/
       ├── images/
       ├── labels/
       └── data.yaml
   ```

**Quick upload:**
```bash
# If you have rclone set up
rclone copy /c/Revelator/traced_indentation_dataset "gdrive:My Drive/traced_indentation_dataset"
```

Or use the Drive web UI to drag-and-drop.

---

## **Step 3: Open Colab Notebook**

Go to **https://colab.research.google.com** and create new notebook.

### Cell 1: Mount Drive & Install YOLOv8

```python
from google.colab import drive
drive.mount('/content/gdrive')

!pip install -U ultralytics opencv-python
```

### Cell 2: Train Model

```python
from ultralytics import YOLO

# Load model
model = YOLO("yolov8m.pt")

# Train
results = model.train(
    data="/content/gdrive/MyDrive/traced_indentation_dataset/data.yaml",
    epochs=50,
    imgsz=640,
    device=0,  # GPU
    patience=10,  # Early stopping
    save=True,
)
```

### Cell 3: Show Results

```python
# Display training results
from IPython.display import Image
Image("/content/gdrive/MyDrive/traced_indentation_dataset/runs/detect/train/results.png")

# Print metrics
print(f"mAP50: {results.results_dict.get('metrics/mAP50(B)', 'N/A')}")
```

### Cell 4: Download Best Weights

```python
from google.colab import files
files.download("/content/gdrive/MyDrive/traced_indentation_dataset/runs/detect/train/weights/best.pt")
```

---

## **Step 4: Save Weights**

Once downloaded, save to:
```
C:\Revelator\models\traced_indentation\weights\best.pt
```

---

## **Step 5: Test Locally**

```python
from ultralytics import YOLO

model = YOLO("C:/Revelator/models/traced_indentation/weights/best.pt")

# Test on image
results = model.predict("path/to/test/image.jpg", conf=0.5)

# View results
for result in results:
    print(f"Detections: {len(result.boxes)}")
    for box in result.boxes:
        print(f"  Confidence: {box.conf:.2f}, Class: {box.cls}")
```

---

## **Step 6: Integrate into App**

Update backend to use new model:

**File:** `backend/app/forgery/detector.py`

```python
# In load_yolo_models():
yolo_models["traced_indentation"] = YOLO("models/traced_indentation/weights/best.pt")
```

---

## **Training Tips**

| Setting | Value | Notes |
|---------|-------|-------|
| Model Size | `yolov8m` | Medium (good balance) |
| Epochs | 50 | Increase to 100 if underfitting |
| Image Size | 640 | Standard for documents |
| Batch Size | 16 | Auto (Colab handles it) |
| Patience | 10 | Early stopping if no improvement |

---

## **Expected Results**

- **Training time:** ~30 minutes on Colab GPU
- **mAP50:** Should be 70-85% (good for synthetic data)
- **File size:** ~50 MB (`best.pt`)

If mAP is below 60%, try:
- Increase epochs to 100
- Use larger model: `yolov8l`
- Check data.yaml path is correct

---

## **Common Issues**

### "Dataset not found"
- Check path in `data.yaml` matches your Drive structure
- Verify `images/` and `labels/` folders exist

### "Out of memory"
- Reduce `imgsz` to 416
- Use `yolov8s` instead of `yolov8m`

### "Validation accuracy very low"
- May indicate label format issue
- Check label files are YOLO format (normalized coords)

### "GPU not available"
- Restart runtime: Runtime → Restart runtime
- Verify GPU is enabled: Runtime → Change runtime type → GPU

---

## **After Training**

1. Download `best.pt`
2. Save to `models/traced_indentation/weights/`
3. Test locally with sample images
4. Update backend config if needed
5. Commit to git with model weights (optional: use Git LFS for large files)

---

## **Useful Colab Resources**

- YOLOv8 Docs: https://docs.ultralytics.com
- Colab GPU Info: https://colab.research.google.com (Tools → Settings → Hardware accelerator)
- Drive API: https://developers.google.com/drive/api

---

**Estimated Total Time:** 45 minutes (30 min training + 15 min setup/download)
