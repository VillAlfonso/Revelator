"""
Generate configuration files for all 16 forgery detection models.
Each model is a BINARY CLASSIFIER: detects ONE specific type of forgery.

Run this once to set up all model folders.
"""

import os
from pathlib import Path

# Define all 16 forgery types with metadata
FORGERY_TYPES = {
    # Traced Forgery (3 types)
    "traced_carbon": {
        "title": "Carbon Transfer Tracing",
        "category": "Traced",
        "description": "Forgery created by placing carbon paper between original and blank document, then tracing.",
        "visual_clues": [
            "Carbon residue deposits (dark smudges)",
            "Pressure marks from tracing tool",
            "Inconsistent line weight",
            "Faded or ghostly appearance"
        ],
        "lighting": "OBLIQUE (45° angle)",
        "public_data": False,
        "notes": "Look for carbon particles under magnification. Lines may appear hesitant or wavering."
    },
    "traced_indentation": {
        "title": "Indentation / Canal Light Tracing",
        "category": "Traced",
        "description": "Forgery where original was placed on top and traced with pressure, leaving grooves.",
        "visual_clues": [
            "Indented grooves in paper",
            "Shadow lines under oblique light",
            "Embossed texture",
            "No ink but visible depressions"
        ],
        "lighting": "OBLIQUE + ESDA",
        "public_data": False,
        "notes": "ESDA (Electrostatic Detection Apparatus) reveals indentations invisible to naked eye."
    },
    "traced_projection": {
        "title": "Projection Process Tracing",
        "category": "Traced",
        "description": "Forgery created using light box or projector to trace original onto new document.",
        "visual_clues": [
            "Very smooth, confident lines (no hesitation)",
            "Consistent line weight throughout",
            "May show retouching at start/stop points",
            "Ink only on surface (no pressure marks)"
        ],
        "lighting": "TRANSMITTED (backlight)",
        "public_data": False,
        "notes": "Often produces the most convincing traced forgeries. Look for lack of natural pen lifts."
    },
    
    # Alteration - Addition (2 types)
    "addition_insertion": {
        "title": "Addition: Insertion",
        "category": "Alteration",
        "description": "Text or characters inserted into existing spaces within a document.",
        "visual_clues": [
            "Crowded or cramped characters",
            "Different ink color/age",
            "Misaligned baseline",
            "Inconsistent spacing"
        ],
        "lighting": "MACRO + UV",
        "public_data": False,
        "notes": "Compare ink under UV - different inks fluoresce differently. Check character spacing."
    },
    "addition_interlineation": {
        "title": "Addition: Interlineation",
        "category": "Alteration",
        "description": "Text added between existing lines of writing.",
        "visual_clues": [
            "Writing between lines",
            "Smaller text to fit space",
            "Different pen pressure",
            "Ink crossing over existing text"
        ],
        "lighting": "MACRO + UV",
        "public_data": False,
        "notes": "Often used to add terms to contracts. Look for compressed vertical spacing."
    },
    
    # Alteration - Erasure (2 types)
    "erasure_chemical": {
        "title": "Erasure: Chemical",
        "category": "Alteration",
        "description": "Original text removed using chemical bleaching agents or solvents.",
        "visual_clues": [
            "Paper discoloration (yellowing, whitening)",
            "Damaged paper fibers",
            "Residual ink traces",
            "Different UV fluorescence in treated area"
        ],
        "lighting": "UV (primary) + TRANSMITTED",
        "public_data": False,
        "notes": "UV light reveals chemical damage invisible to naked eye. Paper may feel different in treated area."
    },
    "erasure_mechanical": {
        "title": "Erasure: Mechanical",
        "category": "Alteration",
        "description": "Original text removed by physical scraping, rubbing, or eraser.",
        "visual_clues": [
            "Disturbed paper fibers (fuzzy texture)",
            "Thinned paper (visible under transmitted light)",
            "Roughened surface",
            "Residual graphite or ink traces"
        ],
        "lighting": "OBLIQUE + TRANSMITTED",
        "public_data": False,
        "notes": "Run finger over surface - erased areas feel rough. Transmitted light shows thin spots."
    },
    
    # Digital Forgery (3 types)
    "digital_cut_paste": {
        "title": "Digital: Cut and Paste (Splicing)",
        "category": "Digital",
        "description": "Elements copied from one digital image and pasted into another.",
        "visual_clues": [
            "Edge artifacts around pasted elements",
            "Noise pattern inconsistency",
            "Lighting direction mismatch",
            "JPEG compression ghosts",
            "Resolution differences"
        ],
        "lighting": "MACRO + ELA (Error Level Analysis)",
        "public_data": True,  # CASIA, Roboflow have this!
        "notes": "Most studied digital forgery type. ELA reveals areas with different compression levels."
    },
    "digital_desktop": {
        "title": "Digital: Desktop Publishing",
        "category": "Digital",
        "description": "Entirely fake document created from scratch using software (Photoshop, Word, etc.).",
        "visual_clues": [
            "Perfect alignment (too perfect)",
            "Consistent font rendering",
            "No paper texture/grain",
            "Metadata inconsistencies",
            "Missing printing artifacts"
        ],
        "lighting": "MACRO + METADATA ANALYSIS",
        "public_data": False,  # No public datasets!
        "notes": "Compare against known authentic documents. Check EXIF data. Print quality analysis."
    },
    "digital_scanned": {
        "title": "Digital: Scanned Document Manipulation",
        "category": "Digital",
        "description": "Document scanned, digitally edited, then re-printed/re-scanned to hide manipulation.",
        "visual_clues": [
            "Double-scanning artifacts (moiré patterns)",
            "Resolution inconsistencies",
            "Scan line artifacts",
            "Generation loss in specific areas"
        ],
        "lighting": "MACRO + HISTOGRAM ANALYSIS",
        "public_data": False,  # No public datasets!
        "notes": "Each scan/print cycle degrades quality. Look for areas with less degradation than surroundings."
    },
    
    # Obliteration (3 types)
    "obliteration_ink": {
        "title": "Obliteration: Ink Stroke",
        "category": "Obliteration",
        "description": "Original content covered with heavy ink strokes or scribbles.",
        "visual_clues": [
            "Visible underlying text (sometimes)",
            "Ink buildup/thickness",
            "Stroke patterns not matching document",
            "Different ink properties"
        ],
        "lighting": "INFRARED (IR)",
        "public_data": False,
        "notes": "IR photography can see through some inks. Different inks have different IR transparency."
    },
    "obliteration_whiteout": {
        "title": "Obliteration: White Out / Correction Fluid",
        "category": "Obliteration",
        "description": "Original content covered with white correction fluid (Wite-Out, Liquid Paper).",
        "visual_clues": [
            "Raised surface texture",
            "Different color white than paper",
            "Visible edges of correction",
            "UV fluorescence difference"
        ],
        "lighting": "TRANSMITTED + UV",
        "public_data": False,
        "notes": "Transmitted light shows opaque spots clearly. Correction fluid often fluoresces differently."
    },
    "obliteration_pigment": {
        "title": "Obliteration: Opaque Pigment",
        "category": "Obliteration",
        "description": "Original content covered with paint, heavy marker, or other opaque pigment.",
        "visual_clues": [
            "Thick coating visible",
            "Color/texture mismatch with paper",
            "Cracking or flaking",
            "Pigment seeping through"
        ],
        "lighting": "TRANSMITTED + INFRARED",
        "public_data": False,
        "notes": "Strong transmitted light may reveal underlying content. Check for coating thickness."
    },
    
    # Sympathetic Ink (2 types)
    "sympathetic_indented": {
        "title": "Sympathetic: Indented Writing",
        "category": "Sympathetic Ink",
        "description": "Hidden writing revealed through indentations left by writing on pages above.",
        "visual_clues": [
            "Groove patterns without ink",
            "Shadow lines under oblique light",
            "ESDA reveals hidden text"
        ],
        "lighting": "OBLIQUE + ESDA",
        "public_data": False,
        "notes": "ESDA is the gold standard for revealing indented writing. Can recover multiple layers."
    },
    "sympathetic_special": {
        "title": "Sympathetic: Special Ink (Invisible Ink)",
        "category": "Sympathetic Ink",
        "description": "Text written with invisible ink that requires special conditions to reveal.",
        "visual_clues": [
            "Nothing visible to naked eye",
            "UV fluorescence reveals some inks",
            "Heat reveals some inks",
            "Chemical developers reveal others"
        ],
        "lighting": "UV (multiple wavelengths) + HEAT",
        "public_data": False,
        "notes": "Different invisible inks respond to different stimuli. May need multiple detection methods."
    },
    
    # Currency (1 type)
    "currency_analysis": {
        "title": "Currency Forgery Analysis",
        "category": "Currency",
        "description": "Detection of counterfeit currency through security feature analysis.",
        "visual_clues": [
            "Missing/poor security thread",
            "Incorrect watermark",
            "Wrong paper feel/texture",
            "Microprinting errors",
            "Color-shifting ink failure",
            "UV fluorescence incorrect"
        ],
        "lighting": "UV + TRANSMITTED + MAGNIFICATION",
        "public_data": False,  # Central banks don't release this
        "notes": "Compare against known genuine notes. Check ALL security features, not just one."
    },
}

def create_data_yaml(model_dir: Path, type_name: str, info: dict):
    """Create data.yaml for YOLO training - BINARY classification"""
    
    content = f"""# ForgeGuard - {info['title']}
# YOLO Training Configuration
# Category: {info['category']}
# 
# This is a BINARY CLASSIFIER:
#   Class 0: {type_name}_detected (forgery of this type found)
#
# {info['description']}

# Dataset paths (relative to this file)
path: ./dataset
train: images/train
val: images/val

# Single class - binary detection
nc: 1
names:
  0: {type_name}_detected

# Training notes:
# - Minimum 100 images recommended
# - 80/20 train/val split
# - Label format: YOLO (class x_center y_center width height)
# - All coordinates normalized 0-1
"""
    
    yaml_path = model_dir / "data.yaml"
    yaml_path.write_text(content)
    print(f"  Created: {yaml_path}")


def create_readme(model_dir: Path, type_name: str, info: dict):
    """Create README with detailed information about this forgery type"""
    
    visual_clues = "\n".join(f"- {clue}" for clue in info['visual_clues'])
    
    content = f"""# {info['title']}

**Category:** {info['category']}  
**Model ID:** `{type_name}`  
**Public Data Available:** {'✅ Yes' if info['public_data'] else '❌ No - requires client samples'}

---

## Description

{info['description']}

---

## Visual Clues to Look For

{visual_clues}

---

## Recommended Lighting

**{info['lighting']}**

---

## Forensic Notes

{info['notes']}

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
{type_name}/
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
cd models/{type_name}
python train.py
```

Or use Google Colab for free GPU.

---

## After Training

1. Copy `weights/best.pt` to main weights folder
2. Update `TRAINING_STATUS["{type_name}"] = True` in main.py
3. Restart server
"""
    
    readme_path = model_dir / "README.md"
    readme_path.write_text(content)
    print(f"  Created: {readme_path}")


def create_train_script(model_dir: Path, type_name: str, info: dict):
    """Create training script for this specific model"""
    
    content = f'''"""
ForgeGuard - Training Script
Model: {info['title']}
Type: {type_name}

This trains a BINARY CLASSIFIER to detect: {info['description'][:80]}...

Usage:
    python train.py                    # Train with defaults
    python train.py --epochs 200       # More epochs
    python train.py --device cpu       # Force CPU
    python train.py test image.jpg     # Test trained model
"""

import argparse
import os
from pathlib import Path

def train(epochs=100, batch=16, device="", imgsz=640):
    """Train the {type_name} detection model"""
    
    from ultralytics import YOLO
    
    # Paths
    data_yaml = Path(__file__).parent / "data.yaml"
    weights_dir = Path(__file__).parent / "weights"
    
    # Validate dataset exists
    dataset_dir = Path(__file__).parent / "dataset" / "images" / "train"
    if not dataset_dir.exists() or not list(dataset_dir.glob("*")):
        print("❌ ERROR: No training images found!")
        print(f"   Put images in: {{dataset_dir}}")
        print(f"   Put labels in: {{dataset_dir.parent.parent / 'labels' / 'train'}}")
        return None
    
    image_count = len(list(dataset_dir.glob("*.*")))
    print(f"\\n📊 Found {{image_count}} training images")
    
    if image_count < 50:
        print("⚠️  WARNING: Less than 50 images. Results may be poor.")
    
    print(f"\\n🚀 Training: {info['title']}")
    print(f"   Epochs: {{epochs}}")
    print(f"   Batch: {{batch}}")
    print(f"   Device: {{'auto' if not device else device}}")
    print("-" * 50)
    
    # Load base model
    model = YOLO("yolov8n.pt")
    
    # Train
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device if device else None,
        project=str(weights_dir.parent / "runs"),
        name="{type_name}",
        
        # Augmentation (tuned for documents)
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        degrees=3.0,        # Slight rotation only
        translate=0.1,
        scale=0.15,
        flipud=0.0,         # No vertical flip for documents
        fliplr=0.3,         # Some horizontal flip OK
        mosaic=0.8,
        
        # Training behavior
        patience=30,
        save=True,
        save_period=10,
        val=True,
        plots=True,
        verbose=True,
    )
    
    # Copy best weights
    best_src = weights_dir.parent / "runs" / "{type_name}" / "weights" / "best.pt"
    best_dst = weights_dir / "best.pt"
    
    if best_src.exists():
        import shutil
        shutil.copy(best_src, best_dst)
        print(f"\\n✅ Training complete!")
        print(f"   Best weights: {{best_dst}}")
    
    return results


def test(weights_path, image_path, conf=0.25):
    """Test trained model on an image"""
    
    from ultralytics import YOLO
    
    if not Path(weights_path).exists():
        print(f"❌ Weights not found: {{weights_path}}")
        return
    
    if not Path(image_path).exists():
        print(f"❌ Image not found: {{image_path}}")
        return
    
    model = YOLO(weights_path)
    results = model(image_path, conf=conf)
    
    for result in results:
        boxes = result.boxes
        if len(boxes) == 0:
            print("\\n✅ No {type_name} forgery detected")
        else:
            print(f"\\n🚨 DETECTED: {{len(boxes)}} potential forgery region(s)")
            for i, box in enumerate(boxes):
                conf = float(box.conf[0])
                print(f"   [{{i+1}}] Confidence: {{conf:.1%}}")
        
        # Save result
        output = "test_result.jpg"
        result.save(output)
        print(f"\\n📸 Saved: {{output}}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="{info['title']} Training")
    parser.add_argument("command", nargs="?", default="train", choices=["train", "test"])
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", type=str, default="")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--weights", type=str, default="weights/best.pt")
    parser.add_argument("--image", type=str, default="")
    parser.add_argument("--conf", type=float, default=0.25)
    
    # Handle positional test arguments
    args, unknown = parser.parse_known_args()
    
    if args.command == "test" or (len(unknown) >= 1 and unknown[0] == "test"):
        # Test mode
        weights = args.weights
        image = args.image or (unknown[1] if len(unknown) > 1 else "")
        if not image:
            print("Usage: python train.py test --weights best.pt --image test.jpg")
        else:
            test(weights, image, args.conf)
    else:
        # Train mode
        train(args.epochs, args.batch, args.device, args.imgsz)
'''
    
    script_path = model_dir / "train.py"
    script_path.write_text(content)
    print(f"  Created: {script_path}")


def main():
    """Generate all config files for all 16 models"""
    
    models_dir = Path(__file__).parent / "models"
    
    print("=" * 60)
    print("ForgeGuard - Generating Model Configurations")
    print("=" * 60)
    
    for type_name, info in FORGERY_TYPES.items():
        model_dir = models_dir / type_name
        
        if not model_dir.exists():
            print(f"⚠️  Skipping {type_name} - folder not found")
            continue
        
        print(f"\n📁 {type_name}/")
        
        create_data_yaml(model_dir, type_name, info)
        create_readme(model_dir, type_name, info)
        create_train_script(model_dir, type_name, info)
    
    print("\n" + "=" * 60)
    print(f"✅ Generated configs for {len(FORGERY_TYPES)} models")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Add images to models/<type>/dataset/images/train/")
    print("2. Add labels to models/<type>/dataset/labels/train/")
    print("3. Run: cd models/<type> && python train.py")


if __name__ == "__main__":
    main()
