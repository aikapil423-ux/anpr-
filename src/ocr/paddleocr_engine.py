"""
PaddleOCR Recognition Engine Module
Provides high-performance inference for PP-OCRv4 Server (88MB, <100MB SOTA)
and PP-OCRv4 Mobile (9.8MB, Ultra-Fast Edge).
"""
from __future__ import annotations

import os
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Sequence, Optional, List, Tuple, Dict, Any
import cv2
import numpy as np

_HERE = Path(__file__).resolve().parent
BASE_DIR = _HERE.parent.parent

# Official PaddleOCR model download links
PADDLEOCR_MODELS_INFO = {
    "paddleocr_v4_server": {
        "dir_name": "ch_PP-OCRv4_rec_server_infer",
        "url": "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_server_infer.tar",
        "dict": "ppocr_keys_v1.txt",
        "size_mb": 88.1,
    },
    "paddleocr_v4_mobile": {
        "dir_name": "en_PP-OCRv4_rec_infer",
        "url": "https://paddleocr.bj.bcebos.com/PP-OCRv4/english/en_PP-OCRv4_rec_infer.tar",
        "dict": "en_dict.txt",
        "size_mb": 9.8,
    }
}


def _find_dict_path(dict_filename: str) -> Path:
    """Finds path to character dictionary file."""
    candidates = [
        BASE_DIR / "models" / "awiros_anpr" / "PaddleOCR" / "ppocr" / "utils" / dict_filename,
        BASE_DIR / "models" / "awiros_anpr" / dict_filename,
        BASE_DIR / "models" / "ocr" / dict_filename,
        _HERE / "PaddleOCR" / "ppocr" / "utils" / dict_filename,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


class PaddleOCRInferenceEngine:
    """
    Paddle inference engine for PP-OCRv4 models.
    Supports on-the-fly loading, automatic weights download, batching, and CTC greedy decoding.
    """
    def __init__(
        self,
        model_key: str = "paddleocr_v4_server",
        device: str = "cpu",
        paddleocr_dir: Optional[str | Path] = None
    ):
        self.model_key = model_key
        self.device = str(device or "cpu")
        self.paddleocr_dir = paddleocr_dir
        
        info = PADDLEOCR_MODELS_INFO.get(model_key, PADDLEOCR_MODELS_INFO["paddleocr_v4_server"])
        self.dir_name = info["dir_name"]
        self.download_url = info["url"]
        self.dict_filename = info["dict"]
        
        self.model_dir = BASE_DIR / "models" / "ocr" / self.dir_name
        self.dict_path = _find_dict_path(self.dict_filename)
        
        self.predictor = None
        self.input_tensor = None
        self.output_tensor = None
        self.decoder = None
        self.loaded = False

    def _ensure_weights(self) -> bool:
        """Auto-downloads model tar archive if missing and extracts into models/ocr/."""
        pdmodel = self.model_dir / "inference.pdmodel"
        pdparams = self.model_dir / "inference.pdiparams"
        if pdmodel.is_file() and pdparams.is_file() and pdparams.stat().st_size > 1000000:
            return True

        self.model_dir.parent.mkdir(parents=True, exist_ok=True)
        tar_path = self.model_dir.parent / f"{self.dir_name}.tar"
        print(f"[PaddleOCR] Model missing at {self.model_dir}. Downloading from {self.download_url}...", file=sys.stderr)
        try:
            req = urllib.request.Request(self.download_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(tar_path, "wb") as f_out:
                f_out.write(resp.read())
            print(f"[PaddleOCR] Extracting {tar_path}...", file=sys.stderr)
            with tarfile.open(tar_path) as tar:
                tar.extractall(path=self.model_dir.parent)
            if tar_path.is_file():
                tar_path.unlink()
            print(f"[PaddleOCR] Model successfully unpacked at {self.model_dir}", file=sys.stderr)
            return pdmodel.is_file() and pdparams.is_file()
        except Exception as e:
            print(f"[PaddleOCR] Failed to download/extract {self.model_key}: {e}", file=sys.stderr)
            return False

    def load(self) -> "PaddleOCRInferenceEngine":
        """Initializes Paddle Inference predictor and CTC label decoder."""
        self._ensure_weights()
        
        # Ensure PaddleOCR ppocr is in sys.path
        ppocr_candidates = [
            BASE_DIR / "models" / "awiros_anpr" / "PaddleOCR",
            _HERE / "PaddleOCR",
            Path(self.paddleocr_dir) if self.paddleocr_dir else None
        ]
        for p in ppocr_candidates:
            if p and (p / "ppocr" / "__init__.py").is_file():
                if str(p) not in sys.path:
                    sys.path.insert(0, str(p))
                break

        import paddle.inference as paddle_infer
        from ppocr.postprocess import build_post_process

        model_file = str(self.model_dir / "inference.pdmodel")
        params_file = str(self.model_dir / "inference.pdiparams")

        config = paddle_infer.Config(model_file, params_file)
        if self.device == "gpu":
            config.enable_use_gpu(100, 0)
        else:
            config.disable_gpu()
            # CRITICAL: Disable IR optimization pass on CPU to avoid OneDnnContext fused_conv2d issue
            config.switch_ir_optim(False)

        self.predictor = paddle_infer.create_predictor(config)
        self.input_tensor = self.predictor.get_input_handle(self.predictor.get_input_names()[0])
        self.output_tensor = self.predictor.get_output_handle(self.predictor.get_output_names()[0])

        self.decoder = build_post_process({
            "name": "CTCLabelDecode",
            "character_dict_path": str(self.dict_path),
            "use_space_char": True
        })
        self.loaded = True
        return self

    def warmup(self) -> None:
        if not self.loaded:
            return
        dummy = np.zeros((48, 160, 3), dtype=np.uint8)
        try:
            self.recognize(dummy)
        except Exception:
            pass

    def recognize(self, image: np.ndarray) -> Tuple[str, float]:
        batch_res = self.recognize_batch([image])
        return batch_res[0] if batch_res else ("", 0.0)

    def recognize_batch(
        self, images: Sequence[Optional[np.ndarray]]
    ) -> List[Tuple[str, float]]:
        if not self.loaded or not self.predictor:
            raise RuntimeError(f"PaddleOCR Engine for {self.model_key} is not loaded.")

        usable_indices: List[int] = []
        preprocessed: List[np.ndarray] = []

        for i, img in enumerate(images):
            if img is not None and getattr(img, "size", 0) > 0:
                h, w = img.shape[:2]
                target_h, target_w = 48, 320
                ratio = float(target_h) / float(h)
                new_w = min(int(round(w * ratio)), target_w)
                resized = cv2.resize(img, (max(1, new_w), target_h))
                padded = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                padded[:, :new_w, :] = resized
                norm = ((padded.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose((2, 0, 1))
                preprocessed.append(norm)
                usable_indices.append(i)

        if not preprocessed:
            return [("", 0.0)] * len(images)

        inp_batch = np.stack(preprocessed)
        self.input_tensor.reshape(inp_batch.shape)
        self.input_tensor.copy_from_cpu(inp_batch)
        self.predictor.run()
        out = self.output_tensor.copy_to_cpu()

        decoded_batch = self.decoder(out)
        results = [("", 0.0)] * len(images)
        for idx, (text, conf) in zip(usable_indices, decoded_batch):
            clean_text = str(text).upper().replace(" ", "").strip()
            results[idx] = (clean_text, float(conf))
        return results
