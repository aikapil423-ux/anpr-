"""
Unified Multi-Model OCR Client Module
Interacts with the dedicated Python 3.11 OCR worker over a JSON-lines pipe,
providing high-throughput, low-latency OCR across:
- PaddleOCR PP-OCRv4 Server (88MB, <100MB SOTA)
- Awiros ANPR-OCR PP-OCRv5 (142MB, Indian Plate Specialist)
- PaddleOCR PP-OCRv4 Mobile (9.8MB, Ultra-Fast Edge)
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
import cv2
import numpy as np

from config import AWIROS_WEIGHTS_PATH, AWIROS_DICT_PATH, AWIROS_PADDLEOCR_DIR, DEFAULT_AWIROS_PYTHON

PROTOCOL_VERSION = 1


def encode_crop_png(image: np.ndarray) -> str:
    """Encodes crop image as base64 PNG."""
    if image is None or image.size == 0:
        return ""
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        return ""
    return base64.b64encode(buffer.tobytes()).decode("ascii")


class AwirosOCRClient:
    def __init__(
        self,
        python_exe: Optional[str] = None,
        weights_path: Optional[str] = None,
        dict_path: Optional[str] = None,
        paddleocr_dir: Optional[str] = None,
        device: str = "cpu",
        default_model: str = "paddleocr_v4_server"
    ):
        self.python_exe = python_exe or DEFAULT_AWIROS_PYTHON
        self.weights_path = weights_path or AWIROS_WEIGHTS_PATH
        self.dict_path = dict_path or AWIROS_DICT_PATH
        self.paddleocr_dir = paddleocr_dir or AWIROS_PADDLEOCR_DIR
        self.device = device
        self.active_model: str = default_model
        
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_counter = 0
        self.ready = False
        self.last_error: Optional[str] = None
        self.stderr_lines: List[str] = []

    def switch_model(self, model_key: str) -> bool:
        """Hot-swaps active OCR model in the worker process."""
        clean_key = str(model_key or "").strip()
        if not clean_key:
            return False
        with self._lock:
            self.active_model = clean_key
            if not self.ready:
                return self.start_worker()

            self._request_counter += 1
            req_id = self._request_counter
            req = {
                "id": req_id,
                "action": "switch_model",
                "model": clean_key
            }
            try:
                self.process.stdin.write(json.dumps(req) + "\n")
                self.process.stdin.flush()
                line = self.process.stdout.readline()
                if line:
                    resp = json.loads(line)
                    if resp.get("status") == "success":
                        print(f"[AwirosOCRClient] Switched active OCR model to {clean_key}")
                        return True
            except Exception as e:
                print(f"[AwirosOCRClient] Error switching model: {e}")
                self.ready = False
        return True

    def _ensure_worker_environment(self) -> bool:
        """Checks if paddle is installed in target python, installs if missing."""
        try:
            res = subprocess.run(
                [self.python_exe, "-c", "import paddle"],
                capture_output=True,
                text=True,
                timeout=15
            )
            if res.returncode == 0:
                return True
        except Exception:
            pass

        print(f"[AwirosOCRClient] 'paddle' missing in {self.python_exe}. Auto-installing...")
        try:
            subprocess.run(
                [self.python_exe, "-m", "pip", "install", "--no-cache-dir", "paddlepaddle>=2.6.0"],
                capture_output=True,
                text=True,
                timeout=300
            )
            print("[AwirosOCRClient] Auto-install completed!")
            return True
        except Exception as e:
            print(f"[AwirosOCRClient] Auto-install warning: {e}")
            return False

    def is_available(self) -> bool:
        if not os.path.exists(self.python_exe):
            which_py = shutil.which(self.python_exe)
            if which_py and os.path.exists(which_py):
                self.python_exe = which_py
            elif os.path.exists(sys.executable):
                self.python_exe = sys.executable

        return os.path.exists(self.python_exe)

    def start_worker(self) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True

        self._ensure_worker_environment()
        if not self.is_available():
            self.last_error = f"Worker python interpreter not found: {self.python_exe}"
            print(f"[AwirosOCRClient] {self.last_error}")
            return False

        worker_script = os.path.join(os.path.dirname(__file__), "awiros_worker.py")
        cmd = [
            self.python_exe,
            worker_script,
            "--weights", self.weights_path,
            "--dict", self.dict_path,
            "--device", self.device,
            "--default-model", self.active_model
        ]
        if self.paddleocr_dir:
            cmd += ["--paddleocr-dir", self.paddleocr_dir]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            # Drain stderr asynchronously to prevent OS pipe deadlocks and capture worker errors
            def _drain_stderr(proc):
                try:
                    for err_line in iter(proc.stderr.readline, ''):
                        if err_line:
                            err_line_str = err_line.strip()
                            self.stderr_lines.append(err_line_str)
                            if len(self.stderr_lines) > 25:
                                self.stderr_lines.pop(0)
                            if any(w in err_line_str.lower() for w in ["error", "exception", "traceback", "failed"]):
                                print(f"[AwirosWorker:stderr] {err_line_str}", file=sys.stderr)
                except Exception:
                    pass

            t = threading.Thread(target=_drain_stderr, args=(self.process,), daemon=True)
            t.start()

            # Read lines until startup JSON banner
            for _ in range(40):
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    banner = json.loads(line)
                    if banner.get("event") == "ready":
                        self.ready = True
                        print(f"[AwirosOCRClient] OCR worker is ready! (Default model: {self.active_model})")
                        return True
                except Exception:
                    continue

            rc = self.process.poll()
            err_msg = " | ".join(self.stderr_lines)
            self.last_error = f"Worker failed to emit ready banner (exit code: {rc}). Stderr: {err_msg}"
            print(f"[AwirosOCRClient] {self.last_error}")
            return False
        except Exception as e:
            self.last_error = f"Failed to start worker: {e}"
            print(f"[AwirosOCRClient] {self.last_error}")
            return False

    def read_text(self, image: np.ndarray, model: Optional[str] = None) -> Tuple[str, float]:
        """
        Submits image crop to OCR worker and returns (text, confidence).
        """
        if image is None or image.size == 0:
            return "", 0.0

        with self._lock:
            if not self.ready:
                if not self.start_worker():
                    return "", 0.0

            encoded = encode_crop_png(image)
            if not encoded:
                return "", 0.0

            self._request_counter += 1
            req_id = self._request_counter
            req = {
                "id": req_id,
                "protocol": PROTOCOL_VERSION,
                "model": model or self.active_model,
                "images": [encoded]
            }

            try:
                self.process.stdin.write(json.dumps(req) + "\n")
                self.process.stdin.flush()

                line = self.process.stdout.readline()
                if not line:
                    return "", 0.0

                resp = json.loads(line)
                if resp.get("id") == req_id and "results" in resp:
                    results = resp["results"]
                    if results:
                        text = results[0].get("text", "")
                        conf = results[0].get("confidence", 0.0)
                        return text, float(conf)
            except Exception as e:
                print(f"[AwirosOCRClient] Error reading response: {e}")
                self.ready = False

        return "", 0.0

    def read_batch(self, images: List[np.ndarray], model: Optional[str] = None) -> List[Tuple[str, float]]:
        """
        Submits multiple image crops to OCR worker in one batch request
        and returns list of (text, confidence) in matching order.
        """
        if not images:
            return []

        # Filter and track indices of valid images
        valid_indices = []
        encoded_payloads = []
        for idx, img in enumerate(images):
            if img is not None and getattr(img, "size", 0) > 0:
                enc = encode_crop_png(img)
                if enc:
                    valid_indices.append(idx)
                    encoded_payloads.append(enc)

        if not encoded_payloads:
            return [("", 0.0) for _ in images]

        results_out: List[Tuple[str, float]] = [("", 0.0) for _ in images]

        with self._lock:
            if not self.ready:
                if not self.start_worker():
                    return results_out

            self._request_counter += 1
            req_id = self._request_counter
            req = {
                "id": req_id,
                "protocol": PROTOCOL_VERSION,
                "model": model or self.active_model,
                "images": encoded_payloads
            }

            try:
                self.process.stdin.write(json.dumps(req) + "\n")
                self.process.stdin.flush()

                line = self.process.stdout.readline()
                if line:
                    resp = json.loads(line)
                    if resp.get("id") == req_id and "results" in resp:
                        res_list = resp["results"]
                        for i, res_item in enumerate(res_list):
                            if i < len(valid_indices):
                                orig_idx = valid_indices[i]
                                txt = res_item.get("text", "")
                                conf = float(res_item.get("confidence", 0.0))
                                results_out[orig_idx] = (txt, conf)
            except Exception as e:
                print(f"[AwirosOCRClient] Error reading batch response: {e}")
                self.ready = False

        return results_out

    def close(self):
        with self._lock:
            if self.process is not None:
                try:
                    self.process.terminate()
                except Exception:
                    pass
                self.process = None
                self.ready = False

    def stop(self):
        self.close()
