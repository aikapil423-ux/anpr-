"""AWIROS ANPR-OCR engine (PaddlePaddle).

Adapted from the official ``test.py`` in ``Awiros/anpr-ocr``, restructured as a
reusable class.  This module runs only inside the dedicated ``ocr_env``
interpreter (Python 3.11), because PaddlePaddle publishes no Python 3.14
wheels.  It is imported by ``awiros_worker.py``; the main pipeline talks to
that worker over a pipe and never imports this file.

Model
-----
``Awiros/anpr-ocr`` - a PP-OCRv5 encoder-decoder (SVTR_HGNet backbone with
PPHGNetV2_B4) plus a MultiHead of CTCHead + NRTRHead, 37.3M parameters,
Apache-2.0.  The CTC head is what gets decoded here.  The NRTR head is present
in the weights, so the graph must be built with the same head widths or
``set_state_dict`` would reject the tensors.

Input is a fixed ``3 x 48 x 320`` tensor; the character set is
``0-9 A-Z a-z`` plus space (62 dict entries, so 64 CTC classes with blank).
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

# CTC head output: 64 classes (62 dict characters + space + blank).
CTC_NUM_CLASSES = 64
# NRTRHead internally appends one class, so 67 -> 68 matches the weights.
NRTR_NUM_CLASSES = 67

# Fixed recognition input size used by PP-OCRv5 rec models.
IMAGE_SHAPE = [3, 48, 320]

# Pinned so the ``ppocr`` API used below is the one the Awiros script targets;
# PaddleOCR 3.x reorganised its modelling internals.  Falls back to the default
# branch if the tag cannot be fetched.
PADDLEOCR_TAG = "v3.0.0"
PADDLEOCR_REPO = "https://github.com/PaddlePaddle/PaddleOCR.git"

# The weights are SafeTensors from PaddlePaddle params.
WEIGHTS_FILENAME = "model.safetensors"
DICT_FILENAME = "en_dict.txt"

MODEL_CONFIG: Dict[str, Any] = {
    "Architecture": {
        "model_type": "rec",
        "algorithm": "SVTR_HGNet",
        "Transform": None,
        "Backbone": {"name": "PPHGNetV2_B4", "text_rec": True},
        "Head": {
            "name": "MultiHead",
            "out_channels_list": {
                "CTCLabelDecode": CTC_NUM_CLASSES,
                "NRTRLabelDecode": NRTR_NUM_CLASSES,
            },
            "head_list": [
                {
                    "CTCHead": {
                        "Neck": {
                            "name": "svtr",
                            "dims": 120,
                            "depth": 2,
                            "hidden_dims": 120,
                            "kernel_size": [1, 3],
                            "use_guide": True,
                        },
                        "Head": {"fc_decay": 1e-05},
                    }
                },
                {"NRTRHead": {"nrtr_dim": 384, "max_text_length": 25}},
            ],
        },
    }
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _find_paddleocr(explicit: Optional[str] = None) -> Optional[Path]:
    """Find a directory containing the ``ppocr`` package."""
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates += [
        _script_dir() / "PaddleOCR",
        _script_dir(),
        Path.cwd(),
        Path.cwd() / "PaddleOCR",
        _script_dir().parent.parent / "models" / "awiros_anpr" / "PaddleOCR",
        Path.cwd() / "models" / "awiros_anpr" / "PaddleOCR",
    ]
    for candidate in candidates:
        if (candidate / "ppocr" / "__init__.py").is_file():
            return candidate
    return None


def ensure_paddleocr(
    explicit: Optional[str] = None, tag: str = PADDLEOCR_TAG
) -> Path:
    """Make ``ppocr`` importable, cloning PaddleOCR when necessary.

    Args:
        explicit: Existing clone to prefer.
        tag: Tag to pin the clone to, so the modelling API cannot drift under
            this script.  Falls back to the default branch if the tag cannot
            be fetched.

    Returns:
        The directory that was prepended to ``sys.path``.

    Raises:
        RuntimeError: No usable clone exists and ``git`` could not fetch one.
    """
    root = _find_paddleocr(explicit)
    if root is not None:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        return root

    import shutil

    target = _script_dir() / "PaddleOCR"
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error = "unknown error"

    for reference in (tag, None):
        try:
            command = ["git", "clone", "--depth", "1"]
            if reference:
                command += ["--branch", reference]
            command += [PADDLEOCR_REPO, str(target)]
            # stdout and stderr MUST be captured here: anything reaching the
            # worker's stdout would corrupt the JSON-lines protocol.
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            shutil.rmtree(target, ignore_errors=True)
    else:
        raise RuntimeError(
            f"could not clone PaddleOCR into {target}: {last_error}\n"
            "Clone it manually and pass --paddleocr-dir."
        )

    if str(target) not in sys.path:
        sys.path.insert(0, str(target))
    return target


def load_safetensors_to_paddle(paddle: Any, weights_path: str) -> Dict[str, Any]:
    """Load a SafeTensors file as a PaddlePaddle state dict."""
    from safetensors import safe_open

    state: Dict[str, Any] = {}
    with safe_open(weights_path, framework="np") as handle:
        for key in handle.keys():
            state[key] = paddle.to_tensor(handle.get_tensor(key))
    return state


def resize_for_rec(
    img_bgr: np.ndarray, target_shape: Sequence[int] = IMAGE_SHAPE
) -> np.ndarray:
    """Resize preserving aspect ratio, then right-pad with black.

    This mirrors PaddleOCR's own ``resize_norm_img``: the crop is squeezed to
    fit the target height and truncated if it would overflow the target width,
    rather than being distorted.  Keeping the same convention as the reference
    script matters - the model was trained against exactly this.
    """
    _, target_h, target_w = target_shape
    img_h, img_w = img_bgr.shape[:2]
    ratio = float(target_h) / float(img_h)
    new_w = min(int(round(img_w * ratio)), int(target_w))
    resized = cv2.resize(img_bgr, (max(1, new_w), int(target_h)))
    if new_w < int(target_w):
        padded = np.zeros((int(target_h), int(target_w), 3), dtype=np.uint8)
        padded[:, :new_w, :] = resized
        resized = padded
    return resized


def preprocess(
    img_bgr: np.ndarray, target_shape: Sequence[int] = IMAGE_SHAPE
) -> np.ndarray:
    """BGR crop -> CHW float32 normalised to [-1, 1]."""
    img = resize_for_rec(img_bgr, target_shape)
    img = img.astype(np.float32) / 255.0
    img = (img - 0.5) / 0.5
    return img.transpose((2, 0, 1))


class AwirosANPREngine:
    """The loaded AWIROS ANPR-OCR model.

    Example:
        >>> engine = AwirosANPREngine(weights, dict_path).load()
        >>> text, confidence = engine.recognize(plate_crop)
    """

    def __init__(
        self,
        weights: str | Path,
        dict_path: str | Path,
        device: str = "cpu",
        paddleocr_dir: Optional[str | Path] = None,
        tag: str = PADDLEOCR_TAG,
    ) -> None:
        self.weights = Path(weights)
        self.dict_path = Path(dict_path)
        self.device = str(device or "cpu")
        self.paddleocr_dir = paddleocr_dir
        self.tag = tag
        self._model: Any = None
        self._decoder: Any = None
        self.loaded = False

    # ------------------------------------------------------------------ setup
    def _setup_paddle(self) -> Any:
        """Import PaddlePaddle and select the device."""
        import paddle

        if self.device == "gpu" and not paddle.is_compiled_with_cuda():
            print(
                "[awiros] CUDA not available in this PaddlePaddle build, "
                "falling back to CPU",
                file=sys.stderr,
            )
            self.device = "cpu"
        paddle.set_device(self.device)

        # A plate crop is tiny; more CPU threads only add scheduling overhead.
        try:
            paddle.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
        except Exception:  # noqa: BLE001 - older paddle builds may not allow it
            pass

        return paddle

    def load(self) -> "AwirosANPREngine":
        """Build the graph, load the weights, and return ``self``.

        Raises:
            FileNotFoundError: Weights or dictionary are missing.
            RuntimeError: ``ppocr`` could not be made importable.
        """
        paddle = self._setup_paddle()
        ensure_paddleocr(self.paddleocr_dir, tag=self.tag)

        from ppocr.modeling.architectures import build_model
        from ppocr.postprocess import build_post_process

        if not self.weights.is_file():
            raise FileNotFoundError(f"AWIROS weights not found: {self.weights}")
        if not self.dict_path.is_file():
            raise FileNotFoundError(f"AWIROS dictionary not found: {self.dict_path}")

        self._decoder = build_post_process(
            {
                "name": "CTCLabelDecode",
                "character_dict_path": str(self.dict_path),
                "use_space_char": True,
            }
        )

        config = copy.deepcopy(MODEL_CONFIG)
        self._model = build_model(config["Architecture"])
        self._model.eval()

        state_dict = load_safetensors_to_paddle(paddle, str(self.weights))
        self._model.set_state_dict(state_dict)
        self.loaded = True
        return self


    # -------------------------------------------------------------- inference
    def warmup(self) -> None:
        """Run one dummy inference so the first real request is not slow."""
        if not self.loaded:
            return
        blank = np.zeros((48, 160, 3), dtype=np.uint8)
        try:
            self._forward([blank])
        except Exception:  # noqa: BLE001 - warmup is best effort
            pass

    def recognize(self, image: np.ndarray) -> Tuple[str, float]:
        """Recognise one plate crop.

        Args:
            image: A BGR plate crop.

        Returns:
            ``(text, confidence)``, upper-cased and stripped.
        """
        if not self.loaded:
            raise RuntimeError("engine is not loaded; call load() first")
        return self._forward([image])[0]

    def recognize_batch(
        self, images: Sequence[Optional[np.ndarray]]
    ) -> List[Tuple[str, float]]:
        """Recognise several crops in one forward pass.

        Returns:
            ``(text, confidence)`` per usable input, in input order.  Empty or
            missing images are skipped, so the result may be shorter.
        """
        if not self.loaded:
            raise RuntimeError("engine is not loaded; call load() first")
        return self._forward(images)

    # ----------------------------------------------------------------- helpers
    def _forward(
        self, images: Sequence[Optional[np.ndarray]]
    ) -> List[Tuple[str, float]]:
        """Batch-preprocess, run the graph, and CTC-decode the output."""
        import paddle

        usable = [
            img for img in images if img is not None and getattr(img, "size", 0) > 0
        ]
        if not usable:
            return []

        tensors = np.stack([preprocess(img, IMAGE_SHAPE) for img in usable])
        batch = paddle.to_tensor(tensors)

        with paddle.no_grad():
            predictions = self._model(batch)

        pred_tensor = self._ctc_tensor(predictions)
        decoded = self._decoder(pred_tensor.numpy())

        results: List[Tuple[str, float]] = []
        for item in decoded:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                text, confidence = item[0], item[1]
            else:
                text, confidence = "", 0.0
            results.append((str(text).strip().upper(), float(confidence)))

        # Pad so callers can zip() the output against their input safely.
        while len(results) < len(usable):
            results.append(("", 0.0))
        return results

    @staticmethod
    def _ctc_tensor(predictions: Any) -> Any:
        """Pull the CTC head out of whatever container the model returned."""
        if isinstance(predictions, dict):
            return predictions.get("ctc", next(iter(predictions.values())))
        if isinstance(predictions, (list, tuple)):
            return predictions[0]
        return predictions

    def describe(self) -> Dict[str, Any]:
        """A dict describing this engine, for the worker's startup banner."""
        return {
            "engine": "Awiros-ANPR-OCR",
            "architecture": "PP-OCRv5 SVTR_HGNet (PPHGNetV2_B4) MultiHead CTC",
            "params": "37.3M",
            "input_shape": list(IMAGE_SHAPE),
            "device": self.device,
            "weights": str(self.weights),
            "loaded": self.loaded,
        }


def collect_images(path: str | Path) -> List[Path]:
    """List image files at ``path`` - a single file, or a directory of them.

    Kept for parity with the reference ``test.py`` so the engine can also be
    driven standalone.
    """
    target = Path(path)
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(
            item
            for item in target.iterdir()
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
        )
    raise FileNotFoundError(f"path not found: {target}")