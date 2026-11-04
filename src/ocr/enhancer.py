"""
Image Enhancement Module for Number Plate Crops
Direct Raw Crop Pass-Through Module (CLAHE, bilateral smoothing, and deskewing
are bypassed to preserve native sensor sharpness and prevent interpolation blur before OCR).
"""
import cv2
import numpy as np

class PlateEnhancer:
    @staticmethod
    def detect_skew_angle(image: np.ndarray) -> float:
        """Returns 0.0 (natural raw angle)."""
        return 0.0

    @staticmethod
    def deskew(image: np.ndarray) -> np.ndarray:
        """Pass-through: preserves original plate crop without interpolation blur."""
        return image

    @staticmethod
    def enhance_color_plate(image: np.ndarray) -> np.ndarray:
        """Pass-through: preserves original plate crop without artificial unsharp noise."""
        return image

    @staticmethod
    def enhance_for_ocr(image: np.ndarray) -> np.ndarray:
        """Direct pass-through for OCR engine."""
        return image

    @staticmethod
    def get_preprocessing_diagnostics(image: np.ndarray, ocr_diag: dict = None) -> dict:
        """
        Calculates genuine raw image quality diagnostics without destructive warping:
        - raw_angle: 0.0
        - is_deskewed: False
        - corrected_angle: 0.0
        - raw_blur: Laplacian sharpness variance
        - enhanced_blur: Laplacian sharpness variance
        - enhanced_image: None (saves duplicate disk writes)
        - selected_strategy: 'raw'
        """
        if image is None or image.size == 0:
            return {
                "raw_angle": 0.0,
                "is_deskewed": False,
                "corrected_angle": 0.0,
                "raw_blur": 0.0,
                "enhanced_blur": 0.0,
                "enhanced_image": None,
                "raw_ocr_text": "",
                "raw_ocr_conf": 0.0,
                "deskewed_ocr_text": "",
                "deskewed_ocr_conf": 0.0,
                "selected_strategy": "raw"
            }

        gray_raw = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        raw_blur = round(float(cv2.Laplacian(gray_raw, cv2.CV_64F).var()), 1)

        o_diag = ocr_diag or {}
        raw_text = o_diag.get("raw_ocr_text", "")
        raw_conf = o_diag.get("raw_ocr_conf", 0.0)

        return {
            "raw_angle": 0.0,
            "is_deskewed": False,
            "corrected_angle": 0.0,
            "raw_blur": raw_blur,
            "enhanced_blur": raw_blur,
            "enhanced_image": None,
            "raw_ocr_text": raw_text,
            "raw_ocr_conf": raw_conf,
            "deskewed_ocr_text": raw_text,
            "deskewed_ocr_conf": raw_conf,
            "selected_strategy": "raw"
        }


