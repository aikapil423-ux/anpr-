"""
Unit tests for Pre-OCR Crop Quality Gate
Tests blur rejection, aspect ratio filtering, resolution constraints,
and watermark/overlay banner detection and masking.
"""
import numpy as np
import cv2
from src.quality.crop_filter import CropQualityFilter
from config import QualityGateConfig

def test_resolution_filter():
    filter_gate = CropQualityFilter(QualityGateConfig(min_width=60, min_height=20))
    
    # Too small crop
    small_crop = np.zeros((15, 50, 3), dtype=np.uint8)
    valid, reason, _, _ = filter_gate.validate(small_crop, det_conf=0.9)
    assert not valid
    assert "resolution too small" in reason.lower()

    # Valid size
    ok_crop = np.zeros((30, 90, 3), dtype=np.uint8)
    # Add high contrast edges so blur check passes
    cv2.putText(ok_crop, "TEST", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    valid, reason, _, _ = filter_gate.validate(ok_crop, det_conf=0.9)
    assert valid

def test_blur_filter():
    filter_gate = CropQualityFilter(QualityGateConfig(min_laplacian_var=45.0))
    
    # Completely blurry/uniform crop
    blurry_crop = np.full((30, 90, 3), 128, dtype=np.uint8)
    # Add minimal Gaussian blur on soft noise
    valid, reason, blur_score, _ = filter_gate.validate(blurry_crop, det_conf=0.9)
    assert not valid
    assert "excessive blur" in reason.lower()

    # Sharp image with sharp edges
    sharp_crop = np.zeros((40, 120, 3), dtype=np.uint8)
    for i in range(0, 120, 10):
        cv2.line(sharp_crop, (i, 0), (i, 40), (255, 255, 255), 2)
    valid, reason, blur_score, _ = filter_gate.validate(sharp_crop, det_conf=0.9)
    assert valid
    assert blur_score > 45.0

def test_aspect_ratio_filter():
    filter_gate = CropQualityFilter(QualityGateConfig(min_aspect_ratio=1.2, max_aspect_ratio=5.5))
    
    # Extreme aspect ratio: tall and narrow (e.g. 100 high, 60 wide -> ratio = 0.60 < 1.2)
    tall_crop = np.zeros((100, 60, 3), dtype=np.uint8)
    valid, reason, _, _ = filter_gate.validate(tall_crop, det_conf=0.9)
    assert not valid
    assert "aspect ratio" in reason.lower()

    # Extremely long banner (e.g. 25 high, 200 wide -> ratio = 8.0 > 5.5)
    wide_crop = np.zeros((25, 200, 3), dtype=np.uint8)
    valid, reason, _, _ = filter_gate.validate(wide_crop, det_conf=0.9)
    assert not valid
    assert "aspect ratio" in reason.lower()

def test_watermark_overlap():
    filter_gate = CropQualityFilter(QualityGateConfig(mask_camera_overlay=True, overlay_top_percent=0.05))
    frame_shape = (1080, 1920, 3)
    
    # Box in top 5% banner region (e.g. y1=10, y2=40)
    banner_bbox = (100, 10, 300, 40)
    crop = np.zeros((30, 200, 3), dtype=np.uint8)
    cv2.putText(crop, "CAM01 2026-09-20", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    
    valid, reason, _, _ = filter_gate.validate(crop, det_conf=0.9, bbox=banner_bbox, frame_shape=frame_shape)
    assert not valid
    assert "watermark/banner overlay" in reason.lower()

def test_low_confidence_rejection():
    filter_gate = CropQualityFilter(QualityGateConfig(min_confidence=0.40))
    crop = np.zeros((30, 90, 3), dtype=np.uint8)
    valid, reason, _, _ = filter_gate.validate(crop, det_conf=0.25)
    assert not valid
    assert "low plate detection confidence" in reason.lower()
