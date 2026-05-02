"""
Train YOLOv8 model for traced indentation detection.

Usage:
    python train_indentation.py --data ./synthetic/data.yaml --epochs 50 --imgsz 640
"""

import argparse
from pathlib import Path
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='./synthetic/data.yaml',
                        help='Path to data.yaml')
    parser.add_argument('--epochs', type=int, default=50,
                        help='Number of training epochs')
    parser.add_argument('--imgsz', type=int, default=640,
                        help='Image size for training')
    parser.add_argument('--batch', type=int, default=16,
                        help='Batch size')
    parser.add_argument('--device', type=int, default=0,
                        help='GPU device (0) or CPU (-1)')
    args = parser.parse_args()

    # Load pre-trained YOLOv8n model
    model = YOLO('yolov8n.pt')

    print("Starting training...")
    print(f"  Data: {args.data}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Image size: {args.imgsz}")
    print(f"  Batch size: {args.batch}")

    # Train
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        patience=10,  # Early stopping
        save=True,
        project='./weights',
        name='traced_indentation_model',
        pretrained=True,
        verbose=True,
    )

    print("\n✓ Training complete!")
    print(f"Best model saved at: ./weights/traced_indentation_model/weights/best.pt")

    # Validate
    print("\nValidating on test set...")
    metrics = model.val()
    print(f"mAP50: {metrics.box.map50:.3f}")
    print(f"mAP50-95: {metrics.box.map:.3f}")


if __name__ == '__main__':
    main()
