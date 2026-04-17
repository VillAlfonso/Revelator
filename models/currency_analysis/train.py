"""
ForgeGuard - Training Script
Model: Currency Forgery Analysis
Type: currency_analysis

This trains a BINARY CLASSIFIER to detect: Detection of counterfeit currency through security feature analysis....

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
    """Train the currency_analysis detection model"""
    
    from ultralytics import YOLO
    
    # Paths
    data_yaml = Path(__file__).parent / "data.yaml"
    weights_dir = Path(__file__).parent / "weights"
    
    # Validate dataset exists
    dataset_dir = Path(__file__).parent / "dataset" / "images" / "train"
    if not dataset_dir.exists() or not list(dataset_dir.glob("*")):
        print("❌ ERROR: No training images found!")
        print(f"   Put images in: {dataset_dir}")
        print(f"   Put labels in: {dataset_dir.parent.parent / 'labels' / 'train'}")
        return None
    
    image_count = len(list(dataset_dir.glob("*.*")))
    print(f"\n📊 Found {image_count} training images")
    
    if image_count < 50:
        print("⚠️  WARNING: Less than 50 images. Results may be poor.")
    
    print(f"\n🚀 Training: Currency Forgery Analysis")
    print(f"   Epochs: {epochs}")
    print(f"   Batch: {batch}")
    print(f"   Device: {'auto' if not device else device}")
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
        name="currency_analysis",
        
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
    best_src = weights_dir.parent / "runs" / "currency_analysis" / "weights" / "best.pt"
    best_dst = weights_dir / "best.pt"
    
    if best_src.exists():
        import shutil
        shutil.copy(best_src, best_dst)
        print(f"\n✅ Training complete!")
        print(f"   Best weights: {best_dst}")
    
    return results


def test(weights_path, image_path, conf=0.25):
    """Test trained model on an image"""
    
    from ultralytics import YOLO
    
    if not Path(weights_path).exists():
        print(f"❌ Weights not found: {weights_path}")
        return
    
    if not Path(image_path).exists():
        print(f"❌ Image not found: {image_path}")
        return
    
    model = YOLO(weights_path)
    results = model(image_path, conf=conf)
    
    for result in results:
        boxes = result.boxes
        if len(boxes) == 0:
            print("\n✅ No currency_analysis forgery detected")
        else:
            print(f"\n🚨 DETECTED: {len(boxes)} potential forgery region(s)")
            for i, box in enumerate(boxes):
                conf = float(box.conf[0])
                print(f"   [{i+1}] Confidence: {conf:.1%}")
        
        # Save result
        output = "test_result.jpg"
        result.save(output)
        print(f"\n📸 Saved: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Currency Forgery Analysis Training")
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
