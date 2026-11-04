"""
Crop Quality Gate Module
Performs pre-OCR validation and filtering to reject:
- Low detection confidence
- Very small resolutions
- Excessive blur (Laplacian variance)
- Invalid aspect ratios
- Watermark / camera timestamp / banner overlaps
Also cleans and masks watermark/overlay areas before OCR.
"""
from typing import Tuple, Optional
import cv2
import numpy as np
from config import QualityGateConfig

class CropQualityFilter:
    def __init__(self, config: Optional[QualityGateConfig] = None):
        self.config = config or QualityGateConfig()

    def compute_blur_score(self, img: np.ndarray) -> float:
        """
        Computes the variance of the Laplacian of the image.
        Higher values indicate sharp edges, lower values indicate blur.
        """
        if img is None or img.size == 0:
            return 0.0
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        return float(lap.var())

    def check_watermark_overlap(
        self,
        bbox: Optional[Tuple[int, int, int, int]],
        frame_shape: Optional[Tuple[int, int, ...]]
    ) -> bool:
        """
        Checks if the bounding box lies in common camera watermark / banner regions
        (e.g., top 5% or bottom 5% of the frame where timestamps and camera IDs are printed).
        bbox: (x1, y1, x2, y2)
        frame_shape: (H, W, ...)
        """
        if bbox is None or frame_shape is None:
            return False
        
        frame_h, frame_w = frame_shape[0], frame_shape[1]
        x1, y1, x2, y2 = bbox
        
        top_banner_h = int(frame_h * self.config.overlay_top_percent)
        bottom_banner_y = int(frame_h * (1.0 - self.config.overlay_bottom_percent))
        
        # If crop is mostly inside top or bottom banner area
        if y1 < top_banner_h and y2 < top_banner_h * 1.5:
            return True
        if y2 > bottom_banner_y and y1 > bottom_banner_y - (frame_h * 0.05):
            return True
        
        return False

    def mask_and_clean_crop(self, crop: np.ndarray) -> np.ndarray:
        """
        Detects and masks border artifacts, camera overlay lines, or channel tags
        at the margins of the crop before sending to OCR.
        """
        if crop is None or crop.size == 0:
            return crop
            
        cleaned = crop.copy()
        h, w = cleaned.shape[:2]
        
        # Upscale smaller crops (e.g. distant highway cameras) so PaddleOCR can extract character features
        if w < 96 or h < 32:
            scale_w = max(1.0, 140.0 / float(max(1, w)))
            scale_h = max(1.0, 48.0 / float(max(1, h)))
            scale = max(scale_w, scale_h)
            new_w = min(480, int(w * scale))
            new_h = min(160, int(h * scale))
            cleaned = cv2.resize(cleaned, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            h, w = cleaned.shape[:2]

        # Trim extreme top or bottom border lines if they contain solid overlay bars
        margin_y = max(1, int(h * 0.04))
        margin_x = max(1, int(w * 0.03))
        
        # Detect solid banner bars at top/bottom (often found in synthetic feeds or CCTV)
        gray = cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY) if len(cleaned.shape) == 3 else cleaned
        
        # Check top row variance vs bottom row variance
        if gray[:margin_y, :].std() < 3.0: # Uniform color banner
            cleaned[:margin_y, :] = 255
        if gray[h - margin_y:, :].std() < 3.0:
            cleaned[h - margin_y:, :] = 255
            
        return cleaned

    def validate(
        self,
        crop: np.ndarray,
        det_conf: float,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        frame_shape: Optional[Tuple[int, int, ...]] = None,
        is_photo: bool = False,
        min_conf: Optional[float] = None
    ) -> Tuple[bool, str, float, np.ndarray]:
        """
        Validates a candidate plate crop.
        Returns:
            (is_valid, reason, blur_score, cleaned_crop)
        """
        if crop is None or crop.size == 0:
            return False, "Empty crop", 0.0, crop

        # 1. Detection confidence: 0.30 for photo/image inspection; 0.60 for video and live feed
        req_conf = min_conf if min_conf is not None else (0.20 if is_photo else self.config.min_confidence)
        if det_conf < req_conf:
            return False, f"Low plate detection confidence: {det_conf:.2f} < {req_conf:.2f}", 0.0, crop

        # 2. Frame margin / border truncation check (Plates cut in half entering/exiting frame)
        if bbox is not None and frame_shape is not None:
            fh, fw = frame_shape[:2]
            px1, py1, px2, py2 = bbox
            margin = 4 if is_photo else 8
            if px1 <= margin or py1 <= margin or px2 >= (fw - margin) or py2 >= (fh - margin):
                return False, f"Border truncated plate (touching frame margin: [{px1},{py1},{px2},{py2}])", 0.0, crop

        # 3. Watermark / Camera overlay location check
        if self.config.mask_camera_overlay and bbox is not None and frame_shape is not None:
            if self.check_watermark_overlap(bbox, frame_shape):
                return False, "Crop overlaps camera watermark/banner overlay", 0.0, crop

        # 3. Resolution check
        h, w = crop.shape[:2]
        if w < self.config.min_width or h < self.config.min_height:
            return False, f"Crop resolution too small ({w}x{h} < {self.config.min_width}x{self.config.min_height})", 0.0, crop

        # 4. Aspect ratio check (support 0.90 to 5.5 for Indian 2-line square & 1-line rectangular plates)
        aspect_ratio = w / float(h)
        min_ar = 0.90 if is_photo else min(1.0, self.config.min_aspect_ratio)
        max_ar = max(5.5, self.config.max_aspect_ratio)
        if aspect_ratio < min_ar or aspect_ratio > max_ar:
            return False, f"Invalid aspect ratio: {aspect_ratio:.2f} not in [{min_ar}, {max_ar}]", 0.0, crop

        # 5. Blur check
        blur_score = self.compute_blur_score(crop)
        if blur_score < self.config.min_laplacian_var:
            return False, f"Excessive blur (Laplacian var {blur_score:.1f} < {self.config.min_laplacian_var:.1f})", blur_score, crop

        # 6. Clean / mask any edge watermarks
        cleaned_crop = self.mask_and_clean_crop(crop)

        return True, "Valid plate crop", blur_score, cleaned_crop
