"""Unified OCR Worker - Multi-model JSON-lines OCR service on stdin/stdout.

Supports:
- paddleocr_v4_server: PP-OCRv4 Server (88MB, <100MB SOTA)
- awiros_anpr: Awiros PP-OCRv5 SVTR_HGNet (142MB, Indian Plate Specialist)

Protocol
--------
One JSON object per line.
The startup banner::
    {"event": "ready", "engine": "Unified-OCR-Worker", "default_model": "paddleocr_v4_server"}

Requests can be::
    {"id": 1, "protocol": 1, "model": "paddleocr_v4_server", "images": ["<base64>", ...]}
or model switch::
    {"id": 2, "action": "switch_model", "model": "paddleocr_v4_server"}
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cv2
import numpy as np

from awiros_engine import AwirosANPREngine, collect_images
from paddleocr_engine import PaddleOCRInferenceEngine

PROTOCOL_VERSION = 1
MAX_BATCH = 64


def decode_image(payload: str) -> Optional[np.ndarray]:
    """Decode one base64-encoded image, or None when it cannot be read."""
    if not payload:
        return None
    try:
        raw = np.frombuffer(base64.b64decode(payload), dtype=np.uint8)
    except Exception:
        return None
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


def emit(payload: Dict[str, Any]) -> None:
    """Write one JSON line to stdout and flush it immediately."""
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


class MultiModelManager:
    """Manages lazy-loaded OCR model instances."""
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.engines: Dict[str, Any] = {}
        self.active_model: str = "paddleocr_v4_server"

    def get_engine(self, model_key: Optional[str] = None) -> Any:
        m = model_key or self.active_model
        if m in self.engines:
            return self.engines[m]

        if m in ("paddleocr_v4_server"):
            engine = PaddleOCRInferenceEngine(
                model_key=m,
                device=self.args.device,
                paddleocr_dir=self.args.paddleocr_dir
            ).load()
            engine.warmup()
            self.engines[m] = engine
            return engine
        elif m == "awiros_anpr":
            engine = AwirosANPREngine(
                weights=self.args.weights,
                dict_path=self.args.dict,
                device=self.args.device,
                paddleocr_dir=self.args.paddleocr_dir,
            ).load()
            engine.warmup()
            self.engines[m] = engine
            return engine
        else:
            # Fallback to server model
            return self.get_engine("paddleocr_v4_server")

    def switch_model(self, model_key: str) -> bool:
        try:
            self.get_engine(model_key)
            self.active_model = model_key
            return True
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return False


def serve(mgr: MultiModelManager) -> int:
    """Read requests from stdin until EOF."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            emit({"id": None, "error": f"bad JSON: {exc}"})
            continue

        request_id = request.get("id")
        action = request.get("action")

        if action == "switch_model":
            target_model = request.get("model", "paddleocr_v4_server")
            ok = mgr.switch_model(target_model)
            emit({"id": request_id, "status": "success" if ok else "error", "active_model": mgr.active_model})
            continue

        if request.get("protocol", PROTOCOL_VERSION) != PROTOCOL_VERSION:
            emit(
                {
                    "id": request_id,
                    "error": f"unsupported protocol {request.get('protocol')!r}",
                }
            )
            continue

        req_model = request.get("model") or mgr.active_model
        payloads = request.get("images") or []
        if not isinstance(payloads, list):
            emit({"id": request_id, "error": "'images' must be a list"})
            continue
        if len(payloads) > MAX_BATCH:
            emit(
                {
                    "id": request_id,
                    "error": f"batch too large: {len(payloads)} > {MAX_BATCH}",
                }
            )
            continue

        try:
            engine = mgr.get_engine(req_model)
            images = [decode_image(payload) for payload in payloads]
            decoded = engine.recognize_batch(images)
            emit(
                {
                    "id": request_id,
                    "model_used": req_model,
                    "results": [
                        {"text": text, "confidence": round(float(conf), 4)}
                        for text, conf in decoded
                    ],
                }
            )
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({"id": request_id, "error": f"{type(exc).__name__}: {exc}"})

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Unified Multi-Model OCR worker")
    parser.add_argument("--weights", default="models/awiros_anpr/model.safetensors", help="model.safetensors path")
    parser.add_argument("--dict", default="models/awiros_anpr/en_dict.txt", help="en_dict.txt path")
    parser.add_argument("--device", default="cpu", help="paddle device: cpu | gpu")
    parser.add_argument("--paddleocr-dir", default=None, help="existing PaddleOCR clone")
    parser.add_argument("--default-model", default="paddleocr_v4_server", help="initial active model")
    parser.add_argument("--image-path", default=None, help="standalone mode: recognise a file or directory")
    parser.add_argument("--output-json", default=None, help="standalone mode: where to write results")
    args = parser.parse_args(argv)

    mgr = MultiModelManager(args)
    mgr.active_model = args.default_model

    # Pre-warm default model
    try:
        mgr.get_engine(args.default_model)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)

    emit({
        "event": "ready",
        "engine": "Unified-OCR-Worker",
        "default_model": mgr.active_model,
        "available_models": ["paddleocr_v4_server", "awiros_anpr"]
    })

    if args.image_path:
        try:
            images = [cv2.imread(str(path)) for path in collect_images(args.image_path)]
            engine = mgr.get_engine(args.default_model)
            decoded = engine.recognize_batch(images)
            results = [
                {"text": text, "confidence": round(float(conf), 4)}
                for text, conf in decoded
            ]
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
            return 1

        if args.output_json:
            Path(args.output_json).write_text(
                json.dumps(results, indent=2), encoding="utf-8"
            )
        for item in results:
            print(f"{item['text']}\t{item['confidence']:.4f}", file=sys.stderr)
        return 0

    return serve(mgr)


if __name__ == "__main__":
    raise SystemExit(main())
