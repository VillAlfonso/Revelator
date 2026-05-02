"""
Phase 2 POC: Auto-detection button testing

Demonstrates single "Scan Document" button that runs both detectors in parallel
and automatically identifies the forgery type (or none).

Usage:
    python phase2_auto_detect.py --image <path> \
                                 --cut-paste-model <model.pt> \
                                 --indentation-model <model.pt> \
                                 --conf 0.5
"""

import argparse
from pathlib import Path
from PIL import Image
from ultralytics import YOLO
import json


class ForgeryDetectionSystem:
    """Single-button auto-detection system for multiple forgery types."""

    def __init__(self, cut_paste_model_path, indentation_model_path, confidence_threshold=0.5):
        """Initialize both detectors."""
        self.cut_paste_model = YOLO(cut_paste_model_path)
        self.indentation_model = YOLO(indentation_model_path)
        self.confidence_threshold = confidence_threshold

        self.category_names = {
            'cut_paste': 'digital_cut_paste',
            'indentation': 'traced_indentation',
        }

    def scan_document(self, image_path):
        """
        Single button: scan document and auto-detect forgery type.

        Returns:
            {
                'verdict': 'digital_cut_paste' | 'traced_indentation' | 'no_forgery_detected',
                'confidence': float,
                'cut_paste': {...detection results...},
                'indentation': {...detection results...},
            }
        """
        image = Image.open(image_path).convert('RGB')

        # Run both detectors in parallel
        cut_paste_result = self.cut_paste_model(image)
        indentation_result = self.indentation_model(image)

        # Extract confidence scores
        cut_paste_conf = self._get_max_confidence(cut_paste_result)
        indentation_conf = self._get_max_confidence(indentation_result)

        # Decide verdict
        verdict = 'no_forgery_detected'
        confidence = 0.0

        if cut_paste_conf > self.confidence_threshold and cut_paste_conf >= indentation_conf:
            verdict = 'digital_cut_paste'
            confidence = cut_paste_conf
        elif indentation_conf > self.confidence_threshold:
            verdict = 'traced_indentation'
            confidence = indentation_conf

        # Return detailed result
        return {
            'verdict': verdict,
            'confidence': float(confidence),
            'details': {
                'cut_paste': {
                    'detected': cut_paste_conf > self.confidence_threshold,
                    'confidence': float(cut_paste_conf),
                    'boxes': len(cut_paste_result[0].boxes) if cut_paste_result else 0,
                },
                'indentation': {
                    'detected': indentation_conf > self.confidence_threshold,
                    'confidence': float(indentation_conf),
                    'boxes': len(indentation_result[0].boxes) if indentation_result else 0,
                },
            }
        }

    def _get_max_confidence(self, result):
        """Extract maximum confidence from YOLO result."""
        if not result or not result[0].boxes:
            return 0.0
        return float(result[0].boxes.conf.max())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True, help='Image to scan')
    parser.add_argument('--cut-paste-model',
                        default='../digital_cut_paste/weights/best.pt',
                        help='Path to cut-paste model')
    parser.add_argument('--indentation-model',
                        default='./weights/traced_indentation_model/weights/best.pt',
                        help='Path to indentation model')
    parser.add_argument('--conf', type=float, default=0.5,
                        help='Confidence threshold')
    args = parser.parse_args()

    # Initialize system
    print("Loading models...")
    system = ForgeryDetectionSystem(
        args.cut_paste_model,
        args.indentation_model,
        args.conf
    )

    # Scan document
    print(f"Scanning: {args.image}")
    result = system.scan_document(args.image)

    # Display result
    print("\n" + "="*60)
    print("REVELATOR FORENSIC ANALYSIS")
    print("="*60)
    print(f"\nVERDICT: {result['verdict'].upper()}")
    print(f"Confidence: {result['confidence']:.1%}")
    print("\nDetailed Results:")
    print(f"  Cut-Paste:    {result['details']['cut_paste']['confidence']:.1%} ({result['details']['cut_paste']['boxes']} regions)")
    print(f"  Indentation:  {result['details']['indentation']['confidence']:.1%} ({result['details']['indentation']['boxes']} regions)")
    print("="*60)

    # Save result
    result_json = Path(args.image).stem + '_result.json'
    with open(result_json, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nResult saved to: {result_json}")


if __name__ == '__main__':
    main()
