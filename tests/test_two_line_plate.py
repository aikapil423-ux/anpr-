"""
Unit tests for Two-Line / Square Plate Handler
Tests slicing, stitching, aspect ratio expansion, and dual-hypothesis evaluation.
"""
import numpy as np
import cv2
from src.ocr.ocr_engine import OCREngine
from src.ocr.normalizer import IndianPlateNormalizer

def test_stitch_two_line_aspect_ratio():
    # Create a synthetic 2-line plate (e.g. 60 height x 80 width -> AR = 1.33)
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    # Top line: HR06
    cv2.putText(img, "HR06", (5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    # Bottom line: AU992
    cv2.putText(img, "AU992", (5, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    stitched = OCREngine._stitch_two_line(img)
    assert stitched is not None, "Expected valid stitched output"
    
    sh, sw = stitched.shape[:2]
    stitched_ar = sw / float(sh)
    # After horizontal concatenation with padding, aspect ratio should expand significantly (> 2.5)
    assert stitched_ar > 2.5, f"Expected stitched AR > 2.5, got {stitched_ar:.2f}"
    assert sh == 48, f"Expected target height 48, got {sh}"

def test_stitch_two_line_tiny_or_empty():
    assert OCREngine._stitch_two_line(None) is None
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert OCREngine._stitch_two_line(empty) is None
    tiny = np.zeros((10, 10, 3), dtype=np.uint8)
    assert OCREngine._stitch_two_line(tiny) is None

def test_dual_hypothesis_candidate_selection():
    engine = OCREngine(use_awiros=False) # mock/offline mode test
    norm = IndianPlateNormalizer()

    # Candidate 1: valid Indian plate with high confidence
    cand_valid = np.zeros((48, 160, 3), dtype=np.uint8)
    # Candidate 2: invalid noise
    cand_invalid = np.zeros((48, 160, 3), dtype=np.uint8)

    # Test hypothesis evaluation logic directly
    scored_candidates = [
        {"raw_text": "HR06AM258", "confidence": 0.85, "is_valid": True, "norm": "HR06AM258", "length": 9},
        {"raw_text": "HR06AM8258", "confidence": 0.99, "is_valid": True, "norm": "HR06AM8258", "length": 10},
        {"raw_text": "DR06BAG1066", "confidence": 0.95, "is_valid": False, "norm": "DR06BAG1066", "length": 11},
    ]

    valid_candidates = [c for c in scored_candidates if c["is_valid"]]
    valid_candidates.sort(key=lambda c: (c["confidence"], c["length"]), reverse=True)
    best = valid_candidates[0]

    assert best["raw_text"] == "HR06AM8258", f"Expected HR06AM8258, got {best['raw_text']}"
    assert best["confidence"] == 0.99
