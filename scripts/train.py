"""
ForgeGuard YOLO Training Script
================================
Train YOLOv8 model for document forgery detection

Usage:
    python scripts/train.py --data data.yaml --epochs 100

For Google Colab:
    !pip install ultralytics
    !python scripts/train.py --data data.yaml --epochs 100 --device 0
"""

import argparse
from pathlib import Path
from ultralytics import YOLO


def train(
    data_yaml: str = "data.yaml",
    model: str = "yolov8n.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str = "",
    project: str = "runs/train",
    name: str = "forgeguard",
    resume: bool = False,
):
    """Train YOLOv8 model for forgery detection"""
    
    print("\n" + "="*50)
    print("ForgeGuard YOLO Training")
    print("="*50)
    print(f"Model: {model}")
    print(f"Data: {data_yaml}")
    print(f"Epochs: {epochs}")
    print(f"Image Size: {imgsz}")
    print(f"Batch Size: {batch}")
    print("="*50 + "\n")
    
    # Load model
    yolo = YOLO(model)
    
    # Train
    results = yolo.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device if device else None,
        project=project,
        name=name,
        resume=resume,
        
        # Augmentation settings
        hsv_h=0.015,      # Hue augmentation
        hsv_s=0.7,        # Saturation augmentation
        hsv_v=0.4,        # Value augmentation
        degrees=5.0,      # Rotation (small for documents)
        translate=0.1,    # Translation
        scale=0.2,        # Scale
        flipud=0.0,       # No vertical flip (documents have orientation)
        fliplr=0.5,       # Horizontal flip
        mosaic=1.0,       # Mosaic augmentation
        
        # Training settings
        patience=50,      # Early stopping patience
        save=True,
        save_period=10,
        val=True,
        plots=True,
        verbose=True,
    )
    
    print("\n" + "="*50)
    print("Training Complete!")
    print("="*50)
    print(f"Best weights: {project}/{name}/weights/best.pt")
    print(f"Last weights: {project}/{name}/weights/last.pt")
    print("="*50 + "\n")
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train ForgeGuard YOLO model")
    parser.add_argument("--data", type=str, default="data.yaml", help="Path to data.yaml")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--device", type=str, default="", help="Device (0 for GPU, '' for auto)")
    parser.add_argument("--project", type=str, default="runs/train", help="Project directory")
    parser.add_argument("--name", type=str, default="forgeguard", help="Run name")
    parser.add_argument("--resume", action="store_true", help="Resume training")
    
    args = parser.parse_args()
    train(**vars(args))
