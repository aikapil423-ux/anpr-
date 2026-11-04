"""
OCR Engine Module with Multi-Model Support:
- PaddleOCR PP-OCRv4 Server (88MB, <100MB SOTA)
- Awiros ANPR-OCR (37.3M PP-OCRv5 SVTR_HGNet, Indian Plate Specialist)
"""
from typing import Tuple, List, Optional, Dict, Any
import os
import re
import numpy as np
import cv2
from src.ocr.enhancer import PlateEnhancer
from src.ocr.awiros_client import AwirosOCRClient
from src.ocr.normalizer import IndianPlateNormalizer
from config import AWIROS_WEIGHTS_PATH, AWIROS_DICT_PATH, AWIROS_PADDLEOCR_DIR, DEFAULT_AWIROS_PYTHON


class OCREngine:
    def __init__(
        self,
        use_awiros: bool = True,
        awiros_python: Optional[str] = None,
        awiros_weights: Optional[str] = None,
        awiros_dict: Optional[str] = None,
        awiros_paddleocr_dir: Optional[str] = None,
        ocr_model: str = "paddleocr_v4_server"
    ):
        self.enhancer = PlateEnhancer()
        self.normalizer = IndianPlateNormalizer()
        self.active_model: str = ocr_model
        self.awiros_client: Optional[AwirosOCRClient] = None

        if use_awiros:
            self.awiros_client = AwirosOCRClient(
                python_exe=awiros_python or DEFAULT_AWIROS_PYTHON,
                weights_path=awiros_weights or AWIROS_WEIGHTS_PATH,
                dict_path=awiros_dict or AWIROS_DICT_PATH,
                paddleocr_dir=awiros_paddleocr_dir or AWIROS_PADDLEOCR_DIR,
                default_model=self.active_model
            )
        self.last_ocr_diagnostics: Dict[str, Any] = {}
        self._easyocr_reader = None

    def switch_ocr_model(self, model_key: str) -> bool:
        """Dynamically switches active OCR model across the engine and worker."""
        clean_key = str(model_key or "").strip()
        if not clean_key:
            return False
        self.active_model = clean_key
        if self.awiros_client is not None:
            return self.awiros_client.switch_model(clean_key)
        return True

    def _init_easyocr(self):
        """Lazy-loads EasyOCR reader on-demand as ultra-reliable fallback."""
        if self._easyocr_reader is None:
            try:
                import easyocr
                import torch
                has_cuda = torch.cuda.is_available()
                self._easyocr_reader = easyocr.Reader(['en'], gpu=has_cuda, verbose=False)
                print("[OCREngine] EasyOCR fallback reader successfully initialized.")
            except Exception as e:
                print(f"[OCREngine] EasyOCR fallback unavailable: {e}")
                self._easyocr_reader = None

    def _run_easyocr_single(self, img: np.ndarray) -> Tuple[str, float]:
        """Executes fallback EasyOCR inference on crop."""
        if img is None or getattr(img, "size", 0) == 0:
            return "", 0.0
        self._init_easyocr()
        if self._easyocr_reader is None:
            return "", 0.0
        try:
            results = self._easyocr_reader.readtext(
                img,
                detail=1,
                paragraph=False,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            )
            if not results:
                return "", 0.0
            results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))
            texts = [r[1].strip() for r in results if r[1].strip()]
            confs = [float(r[2]) for r in results if r[1].strip()]
            if not texts:
                return "", 0.0
            return "".join(texts), float(np.mean(confs)) if confs else 0.0
        except Exception as e:
            print(f"[OCREngine] EasyOCR reading error: {e}")
            return "", 0.0

    @staticmethod
    def _stitch_two_line(image: np.ndarray) -> Optional[np.ndarray]:
        """
        Splits a two-line / square plate into top (State/RTO) and bottom (Series/Number)
        halves and horizontally concatenates them with padding into a single horizontal strip.
        """
        if image is None or image.size == 0:
            return None
        h, w = image.shape[:2]
        if h < 20 or w < 20:
            return None

        mid_t = int(h * 0.48)
        mid_b = int(h * 0.44)
        top = image[:mid_t, :]
        bot = image[mid_b:, :]
        if top.shape[0] < 5 or bot.shape[0] < 5:
            return None

        target_h = 48
        top_w = max(int(top.shape[1] * (float(target_h) / top.shape[0])), 10)
        bot_w = max(int(bot.shape[1] * (float(target_h) / bot.shape[0])), 10)
        top_r = cv2.resize(top, (top_w, target_h), interpolation=cv2.INTER_CUBIC)
        bot_r = cv2.resize(bot, (bot_w, target_h), interpolation=cv2.INTER_CUBIC)

        pad_w = 20
        pad = np.ones((target_h, pad_w, image.shape[2]), dtype=image.dtype) * 255
        right_pad_w = 16
        right_pad = np.ones((target_h, right_pad_w, image.shape[2]), dtype=image.dtype) * 255

        stitched = np.hstack([top_r, pad, bot_r, right_pad])
        return stitched

    def close(self):
        if self.awiros_client:
            self.awiros_client.close()

    def _run_ocr_single(self, image: np.ndarray) -> Tuple[str, float]:
        """Runs OCR on plate crop using currently selected active OCR model."""
        if image is None or image.size == 0:
            return "", 0.0

        text, conf = "", 0.0
        strategy = self.active_model

        if self.active_model == "easyocr":
            text, conf = self._run_easyocr_single(image)
        else:
            if self.awiros_client is not None:
                text, conf = self.awiros_client.read_text(image, model=self.active_model)

            # Fallback to EasyOCR if active engine produced empty or very low confidence read
            if not text or conf < 0.20:
                fb_text, fb_conf = self._run_easyocr_single(image)
                if fb_text:
                    text, conf = fb_text, fb_conf
                    strategy = f"{self.active_model}_fallback_easyocr"

        self.last_ocr_diagnostics = {
            "raw_ocr_text": text or "",
            "raw_ocr_conf": round(conf * 100, 1) if conf else 0.0,
            "deskewed_ocr_text": text or "",
            "deskewed_ocr_conf": round(conf * 100, 1) if conf else 0.0,
            "selected_strategy": strategy,
            "enhanced_crop": image
        }
        return text, conf

    def _evaluate_hypotheses(self, candidates: List[np.ndarray]) -> Tuple[str, float]:
        """
        Evaluates candidate crops, scoring against Indian plate format and confidence.
        Prefers complete 10-character (4-digit) reads over incomplete 9-character reads.
        """
        scored_candidates = []
        for img in candidates:
            text, conf = self._run_ocr_single(img)
            if not text:
                continue
            is_valid, fmt, norm = self.normalizer.validate(text)
            has_4_digits = bool(re.search(r'[0-9]{4}$', norm))
            candidate = {
                "raw_text": text,
                "confidence": conf,
                "is_valid": is_valid,
                "norm": norm,
                "length": len(norm),
                "has_4_digits": has_4_digits
            }
            if is_valid and has_4_digits and len(norm) == 10 and conf >= 0.70:
                return norm, conf
            scored_candidates.append(candidate)

        if not scored_candidates:
            return "", 0.0

        valid_candidates = [c for c in scored_candidates if c["is_valid"]]
        if valid_candidates:
            valid_candidates.sort(
                key=lambda c: (c["has_4_digits"], c["length"] == 10, c["length"] == 9, c["confidence"]),
                reverse=True
            )
            best = valid_candidates[0]
            return best["norm"], best["confidence"]

        length_filtered = [
            c for c in scored_candidates 
            if self.normalizer.config.min_length <= c["length"] <= self.normalizer.config.max_length
        ]
        if length_filtered:
            length_filtered.sort(
                key=lambda c: (c["has_4_digits"], c["length"] == 10, c["confidence"]),
                reverse=True
            )
            best = length_filtered[0]
            return best["norm"], best["confidence"]

        return "", 0.0

    def read_text(self, image: np.ndarray) -> Tuple[str, float]:
        """
        Runs OCR on plate crop using currently selected active OCR model.
        For standard plates (aspect ratio >= 2.0), runs single-line OCR.
        For square/two-wheeler plates (aspect ratio < 2.0), uses horizontal stitching.
        """
        if image is None or image.size == 0:
            return "", 0.0

        h, w = image.shape[:2]
        aspect_ratio = w / float(h) if h > 0 else 3.0

        if aspect_ratio >= 2.0:
            raw_text, conf = self._run_ocr_single(image)
            is_valid, fmt, norm = self.normalizer.validate(raw_text) if raw_text else (False, "", "")

            if is_valid and conf >= 0.75 and len(norm) == 10:
                return (norm, conf)

            if not is_valid or conf < 0.65 or len(norm) < 9:
                pad_x = max(6, int(w * 0.10))
                pad_y = max(4, int(h * 0.10))
                padded_crop = cv2.copyMakeBorder(image, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=[255, 255, 255])
                pad_text, pad_conf = self._run_ocr_single(padded_crop)
                if pad_text:
                    p_valid, p_fmt, p_norm = self.normalizer.validate(pad_text)
                    if p_valid and (not is_valid or pad_conf >= conf):
                        return (p_norm, pad_conf)
                    elif not is_valid and pad_conf > conf:
                        raw_text, conf = pad_text, pad_conf
                        is_valid, fmt, norm = p_valid, p_fmt, p_norm

            # Wider two-line bus/bike plates may otherwise look like one-line crops.
            if not is_valid and aspect_ratio < 2.6:
                stitched = self._stitch_two_line(image)
                if stitched is not None:
                    alt_text, alt_conf = self._evaluate_hypotheses([stitched])
                    if alt_text and self.normalizer.validate(alt_text)[0]:
                        return alt_text, alt_conf
            cleaned = self.normalizer.clean_raw_text(raw_text)
            if len(cleaned) < self.normalizer.config.min_length or len(cleaned) > self.normalizer.config.max_length:
                return "", 0.0
            return (norm, conf) if is_valid else (norm if norm else cleaned, conf)

        candidates = []
        stitched = self._stitch_two_line(image)
        if stitched is not None:
            candidates.append(stitched)
        candidates.append(image)

        return self._evaluate_hypotheses(candidates)

    def read_batch(self, images: List[np.ndarray]) -> List[Tuple[str, float]]:
        """
        Runs vectorized batch OCR inference on candidate plate crops.
        """
        if not images:
            return []

        if self.active_model == "easyocr" or self.awiros_client is None or not getattr(self.awiros_client, "ready", False):
            return [self.read_text(img) if img is not None else ("", 0.0) for img in images]

        processed_candidates = []
        for img in images:
            if img is None or getattr(img, "size", 0) == 0:
                processed_candidates.append(None)
                continue
            h, w = img.shape[:2]
            aspect_ratio = w / float(h) if h > 0 else 3.0
            if aspect_ratio < 2.0:
                stitched = self._stitch_two_line(img)
                if stitched is not None:
                    processed_candidates.append(stitched)
                    continue
            processed_candidates.append(img)

        raw_results = self.awiros_client.read_batch(processed_candidates, model=self.active_model)
        final_results = []
        for raw_text, conf in raw_results:
            if not raw_text:
                final_results.append(("", 0.0))
                continue
            cleaned = self.normalizer.clean_raw_text(raw_text)
            if len(cleaned) < self.normalizer.config.min_length or len(cleaned) > self.normalizer.config.max_length:
                final_results.append(("", 0.0))
                continue
            is_valid, fmt, norm = self.normalizer.validate(raw_text)
            final_results.append((norm if is_valid else raw_text, conf))

        return final_results
