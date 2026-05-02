"""
Synthesize traced indentation forgeries from real samples + clean documents.

Strategy:
1. Extract visual characteristics from 24 real indentation samples
2. Generate synthetic indentation marks on clean documents:
   - Traced signature/text (simulate pen pressure)
   - Groove/shadow artifacts (visible under raking light)
3. Aggressive augmentation: lighting, scale, compression
4. Output in YOLO format with proper train/valid/test split

Usage:
    python synthesize_indentation.py \
        --real-dir ./train/images \
        --clean-dir ../../clean/Datasets1 \
        --output-dir ./synthetic \
        --count 100 \
        --negatives 300
"""

import argparse
import os
import random
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import cv2


def add_synthetic_indentation(clean_img_pil, region_box=None):
    """
    Add synthetic indentation marks to a clean document.
    Simulates traced indentation with groove artifacts and pressure marks.
    """
    img = clean_img_pil.copy()
    W, H = img.size

    # Choose region if not provided
    if region_box is None:
        w = random.randint(int(W * 0.1), int(W * 0.4))
        h = random.randint(int(H * 0.05), int(H * 0.15))
        x = random.randint(0, W - w)
        y = random.randint(int(H * 0.2), int(H * 0.8) - h)
        region_box = (x, y, w, h)

    x, y, w, h = region_box

    # Convert to numpy for processing
    img_array = np.array(img.convert('RGB'), dtype=np.float32)

    # Add shadow gradient (simulating groove/indentation depth from raking light)
    # Darker at edges, lighter in middle (typical of indentation grooves)
    for i in range(int(h)):
        for j in range(int(w)):
            px = int(x + j)
            py = int(y + i)
            if 0 <= px < W and 0 <= py < H:
                dist_from_edge = min(i, h - i, j, w - j)
                shadow_intensity = max(0, 1 - (dist_from_edge / (h/3)))
                shadow_value = int(shadow_intensity * 20)
                img_array[py, px] = np.clip(img_array[py, px] - shadow_value, 0, 255)

    img = Image.fromarray(np.uint8(img_array))

    # Step 3: Add blur to simulate indentation depth
    blur_radius = random.uniform(0.5, 1.5)
    region = img.crop((x, y, x+w, y+h))
    region = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    img.paste(region, (int(x), int(y)))

    # Step 4: Slight brightness adjustment (indentations appear slightly darker)
    brightness = ImageEnhance.Brightness(img)
    brightness_factor = random.uniform(0.95, 1.0)
    img = brightness.enhance(brightness_factor)

    # Generate polygon coordinates (normalized 0-1) for YOLO label
    # Expand region slightly to include shadow area
    expand = 0.05
    x_norm = max(0, (x - w*expand) / W)
    y_norm = max(0, (y - h*expand) / H)
    w_norm = min(1, (w + w*expand*2) / W)
    h_norm = min(1, (h + h*expand*2) / H)

    # Return as polygon (rectangle corners normalized)
    polygon = [
        x_norm, y_norm,
        x_norm + w_norm, y_norm,
        x_norm + w_norm, y_norm + h_norm,
        x_norm, y_norm + h_norm,
    ]

    return img, polygon


def augment_image(img_pil):
    """Apply augmentations to simulate different capture conditions."""
    img = img_pil.copy()

    # Random brightness/contrast
    if random.random() < 0.6:
        brightness = ImageEnhance.Brightness(img)
        img = brightness.enhance(random.uniform(0.9, 1.1))

    if random.random() < 0.6:
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(random.uniform(0.9, 1.1))

    # Random blur (simulating camera focus)
    if random.random() < 0.4:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.3, 0.8)))

    # Random rotation (slight, like hand-held photo)
    if random.random() < 0.5:
        angle = random.uniform(-2, 2)
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False)

    # Random JPEG compression (simulate photo quality)
    if random.random() < 0.6:
        import io
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=random.randint(70, 95))
        buf.seek(0)
        img = Image.open(buf).convert('RGB')

    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real-dir', default='./train/images',
                        help='Directory with 24 real indentation samples')
    parser.add_argument('--clean-dir', default='../../clean/Datasets1',
                        help='Directory with clean documents')
    parser.add_argument('--output-dir', default='./synthetic',
                        help='Output directory for synthetic dataset')
    parser.add_argument('--count', type=int, default=100,
                        help='Synthetic forgeries per clean document')
    parser.add_argument('--negatives', type=int, default=300,
                        help='Number of clean documents to copy as negatives')
    args = parser.parse_args()

    # Setup output dirs
    for subdir in ['train/images', 'train/labels', 'valid/images', 'valid/labels',
                   'test/images', 'test/labels']:
        Path(args.output_dir).joinpath(subdir).mkdir(parents=True, exist_ok=True)

    # Get clean documents
    clean_dir = Path(args.clean_dir)
    clean_files = list(clean_dir.glob('*.jpg')) + list(clean_dir.glob('*.jpeg')) + \
                  list(clean_dir.glob('*.png'))
    print(f"Found {len(clean_files)} clean documents")

    # Analyze real indentation samples for reference
    real_dir = Path(args.real_dir)
    real_files = list(real_dir.glob('*.jpg')) + list(real_dir.glob('*.jpeg')) + \
                 list(real_dir.glob('*.png'))
    print(f"Found {len(real_files)} real indentation samples (will use as reference)")

    # Generate synthetic forgeries
    print(f"\nGenerating {args.count} synthetic forgeries per clean document...")
    synthetic_count = 0

    for clean_idx, clean_file in enumerate(clean_files):

        try:
            clean_img = Image.open(clean_file).convert('RGB')

            for syn_idx in range(args.count):
                # Create synthetic indentation (simulates grooves from traced indentation)
                forged_img, polygon = add_synthetic_indentation(clean_img)

                # Augment
                forged_img = augment_image(forged_img)

                # Decide split (70% train, 20% valid, 10% test)
                split_rand = random.random()
                if split_rand < 0.7:
                    split = 'train'
                elif split_rand < 0.9:
                    split = 'valid'
                else:
                    split = 'test'

                # Save image
                img_name = f"syn_{clean_idx:03d}_{syn_idx:03d}.jpg"
                img_path = Path(args.output_dir) / split / 'images' / img_name
                forged_img.save(img_path, quality=85)

                # Save YOLO label (polygon format, class 0 = indentation)
                label_path = Path(args.output_dir) / split / 'labels' / img_name.replace('.jpg', '.txt')
                label_str = "0 " + " ".join(f"{coord:.6f}" for coord in polygon)
                with open(label_path, 'w') as f:
                    f.write(label_str)

                synthetic_count += 1
                if synthetic_count % 100 == 0:
                    print(f"  Generated {synthetic_count} synthetic images...")

        except Exception as e:
            print(f"Error processing {clean_file}: {e}")
            continue

    print(f"\nTotal synthetic forgeries: {synthetic_count}")

    # Copy clean documents as negatives
    print(f"\nCopying up to {args.negatives} clean documents as negatives...")
    negatives_copied = 0

    for clean_file in random.sample(clean_files, min(args.negatives, len(clean_files))):
        try:
            img = Image.open(clean_file).convert('RGB')

            # Decide split
            split_rand = random.random()
            if split_rand < 0.7:
                split = 'train'
            elif split_rand < 0.9:
                split = 'valid'
            else:
                split = 'test'

            # Save image with clean prefix
            img_name = f"clean_{negatives_copied:03d}.jpg"
            img_path = Path(args.output_dir) / split / 'images' / img_name
            img.save(img_path, quality=85)

            # Create empty label (no indentation)
            label_path = Path(args.output_dir) / split / 'labels' / img_name.replace('.jpg', '.txt')
            label_path.write_text('')

            negatives_copied += 1
        except Exception as e:
            print(f"Error copying {clean_file}: {e}")
            continue

    print(f"Total negatives: {negatives_copied}")

    # Count final dataset
    train_imgs = len(list(Path(args.output_dir).glob('train/images/*')))
    valid_imgs = len(list(Path(args.output_dir).glob('valid/images/*')))
    test_imgs = len(list(Path(args.output_dir).glob('test/images/*')))
    total = train_imgs + valid_imgs + test_imgs

    print(f"\n=== FINAL DATASET ===")
    print(f"Train: {train_imgs}")
    print(f"Valid: {valid_imgs}")
    print(f"Test: {test_imgs}")
    print(f"Total: {total}")

    # Create data.yaml for YOLO
    yaml_content = f"""path: {Path(args.output_dir).absolute()}
train: train/images
val: valid/images
test: test/images

nc: 1
names:
  0: traced_indentation
"""

    with open(Path(args.output_dir) / 'data.yaml', 'w') as f:
        f.write(yaml_content)

    print(f"\ndata.yaml created at {Path(args.output_dir) / 'data.yaml'}")
    print("Ready to train!")


if __name__ == '__main__':
    main()
