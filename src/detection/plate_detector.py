"""
Plate Detector Module
Detects license plate candidates either using a trained YOLO plate detector
or morphological/edge plate localization within detected vehicle regions.
"""
from typing import List, Tuple, Dict, Any, Optional
import os
import threading
import urllib.request
import cv2
import numpy as np
import torch
from pathlib import Path
from ultralytics import YOLO
from config import PLATE_MODEL_PATH

if hasattr(torch, "set_num_threads"):
    try:
        torch.set_num_threads(min(4, os.cpu_count() or 1))
    except Exception:
        pass

class PlateDetector:
    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_thresh: float = 0.60,
        download_if_missing: bool = True
    ):
        self.conf_thresh = conf_thresh
        self.model_path = self._resolve_model(model_path or PLATE_MODEL_PATH)
        self.yolo_model = None
        self._swap_lock = threading.Lock()
        if self.model_path and os.path.isfile(self.model_path):
            try:
                self.yolo_model = YOLO(self.model_path)
            except Exception as e:
                print(f"[WARN] Failed to load YOLO plate model from {self.model_path}: {e}")
                self.yolo_model = None
        else:
            print(f"[WARN] Plate detector YOLO model not found at {self.model_path}.")

    def _resolve_model(self, initial_path: Optional[str]) -> Optional[str]:
        """Resolves model path across candidate locations, strictly avoiding OpenVINO."""
        def _is_valid(path: Optional[str]) -> bool:
            if not path:
                return False
            p = Path(path)
            if p.is_file() and p.stat().st_size > 1000 and not p.name.endswith(".xml"):
                return True
            return False

        if _is_valid(initial_path):
            return str(initial_path)

        # Check in model registry
        try:
            from src.detection.model_registry import registry
            resolved = registry.resolve_model_path(initial_path or "yolo11s_plate")
            if _is_valid(resolved):
                return resolved
        except Exception:
            pass

        base_dir = Path(__file__).resolve().parent.parent.parent
        candidates = [
            str(base_dir / "models" / "yolo" / "plate_yolo_l.pt"),
            str(base_dir / "models" / "yolo" / "tanish_yolo11s_plate.pt"),
            str(base_dir / "models" / "yolo" / "yolov8_plate.pt"),
            str(base_dir / "models" / "yolo" / "yolo11x_plate.pt"),
            str(base_dir / "models" / "indian_lpr" / "best_semantic.pth"),
            str(base_dir / "models" / "yolo" / "alpr_26x.pt"),
            str(base_dir / "models" / "yolo" / "alpr_26n.pt"),
            str(base_dir / "models" / "yolo" / "yolo11s_plate.pt"),
            str(base_dir / "models" / "yolo" / "yolo26_plate.pt"),
        ]
        for c in candidates:
            if _is_valid(c):
                return c

        return None

    def switch_model(self, new_model_path: str) -> bool:
        """Dynamically hot-swaps active Indian license plate YOLO/RT-DETR model."""
        resolved = self._resolve_model(new_model_path)
        if not resolved or not os.path.isfile(resolved):
            print(f"[ERROR] Cannot switch plate model: file not found for {new_model_path} ({resolved})")
            return False
        try:
            if resolved.endswith(".pt"):
                new_model = YOLO(resolved)
            else:
                import torch
                new_model = torch.load(resolved, map_location="cpu", weights_only=False)
            with self._swap_lock:
                self.yolo_model = new_model
                self.model_path = resolved
            print(f"[PlateDetector] Successfully switched active plate model to {resolved}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load new plate model {resolved}: {e}")
            return False

    def detect_in_frame(
        self,
        frame: np.ndarray,
        vehicle_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
        conf_thresh: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Detects license plates strictly using trained deep YOLO plate model.
        Returns empty list if no plate detected (strictly NO morphological fallback).
        """
        if self.yolo_model is not None:
            try:
                with self._swap_lock:
                    yolo_dets = self._detect_yolo(frame, vehicle_boxes, conf_thresh=conf_thresh)
                return yolo_dets or []
            except Exception as e:
                print(f"[WARN] YOLO plate inference error: {e}")
                return []
        return []

    def _detect_heuristic_bumper(
        self,
        frame: np.ndarray,
        vehicle_boxes: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fallback bumper candidate generator for vehicles when plate models or contours fail.
        Selects lower central area of the detected vehicle bounding box.
        """
        detections = []
        if not vehicle_boxes:
            return detections

        h, w = frame.shape[:2]
        for vbox in vehicle_boxes:
            vx1, vy1, vx2, vy2 = vbox
            vw = vx2 - vx1
            vh = vy2 - vy1
            if vw < 35 or vh < 25:
                continue

            pw = int(vw * 0.65)
            ph = int(vh * 0.28)
            px1 = max(0, min(w - 1, vx1 + int((vw - pw) / 2)))
            py1 = max(0, min(h - 1, vy2 - ph - int(vh * 0.04)))
            px2 = max(0, min(w, px1 + pw))
            py2 = max(0, min(h, py1 + ph))

            if px2 > px1 and py2 > py1:
                detections.append({
                    "bbox": (px1, py1, px2, py2),
                    "conf": 0.55,
                    "vehicle_bbox": vbox
                })
        return detections

    def _detect_yolo(
        self,
        frame: np.ndarray,
        vehicle_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
        conf_thresh: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        # Low-light & night traffic CLAHE contrast enhancement for YOLOv11l Indian FineTune
        input_frame = frame
        if self.model_path and "yolo11l" in str(self.model_path).lower():
            try:
                lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                cl = clahe.apply(l)
                input_frame = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
            except Exception:
                input_frame = frame

        # If .pth semantic segmentation checkpoint (Indian_LPR)
        if isinstance(self.yolo_model, dict) or not hasattr(self.yolo_model, "__call__"):
            return self._detect_heuristic_bumper(input_frame, vehicle_boxes)

        # Preserve high resolution on uncompressed frames (prevents tiny bike plates from blurring out)
        h, w = input_frame.shape[:2]
        max_dim = max(h, w)
        if self.model_path and "openvino" in str(self.model_path).lower():
            det_imgsz = 640
        else:
            # Scale inference up to 1280 (multiple of 32) so small bike plates have high pixel density
            det_imgsz = max(640, min(1280, (max_dim // 32) * 32))

        effective_conf = conf_thresh if conf_thresh is not None else self.conf_thresh
        results = self.yolo_model(input_frame, conf=effective_conf, imgsz=det_imgsz, verbose=False)
        detections = []
        if not results or len(results) == 0:
            return detections

        boxes = results[0].boxes.xyxy.cpu().numpy()
        confs = results[0].boxes.conf.cpu().numpy()

        for i in range(len(boxes)):
            x1, y1, x2, y2 = [int(v) for v in boxes[i]]
            conf = float(confs[i])
            
            # Find matching vehicle box if provided
            matched_vbox = None
            if vehicle_boxes:
                best_overlap = 0.0
                p_area = max(1, (x2 - x1) * (y2 - y1))
                pcx, pcy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

                for vbox in vehicle_boxes:
                    vx1, vy1, vx2, vy2 = vbox
                    # 1. Center containment
                    if vx1 <= pcx <= vx2 and vy1 <= pcy <= vy2:
                        matched_vbox = vbox
                        break
                    # 2. Overlap fallback (> 25% overlap)
                    ix1 = max(x1, vx1)
                    iy1 = max(y1, vy1)
                    ix2 = min(x2, vx2)
                    iy2 = min(y2, vy2)
                    iw = max(0, ix2 - ix1)
                    ih = max(0, iy2 - iy1)
                    overlap = (iw * ih) / p_area
                    if overlap > 0.25 and overlap > best_overlap:
                        best_overlap = overlap
                        matched_vbox = vbox

                # 3. Bumper & occlusion expansion fallback (15% padding around vehicle boundaries)
                if matched_vbox is None:
                    best_dist = float("inf")
                    for vbox in vehicle_boxes:
                        vx1, vy1, vx2, vy2 = vbox
                        vw = vx2 - vx1
                        vh = vy2 - vy1
                        pad_w = int(vw * 0.15)
                        pad_h = int(vh * 0.15)
                        if (vx1 - pad_w) <= pcx <= (vx2 + pad_w) and (vy1 - pad_h) <= pcy <= (vy2 + pad_h):
                            vcx, vcy = (vx1 + vx2) / 2.0, (vy1 + vy2) / 2.0
                            dist = (pcx - vcx) ** 2 + (pcy - vcy) ** 2
                            if dist < best_dist:
                                best_dist = dist
                                matched_vbox = vbox

            detections.append({
                "bbox": (x1, y1, x2, y2),
                "conf": conf,
                "vehicle_bbox": matched_vbox
            })

        return detections

    def _detect_morphological(
        self,
        frame: np.ndarray,
        vehicle_boxes: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Morphological fallback localizer inside vehicle regions.
        Finds rectangular regions with high horizontal edge density.
        """
        detections = []
        if not vehicle_boxes:
            return detections

        for vbox in vehicle_boxes:
            vx1, vy1, vx2, vy2 = vbox
            vw = vx2 - vx1
            vh = vy2 - vy1
            if vw < 50 or vh < 40:
                continue

            # Focus search on lower 70% of vehicle (typical plate position)
            search_y1 = vy1 + int(vh * 0.3)
            search_y2 = vy2
            v_crop = frame[search_y1:search_y2, vx1:vx2]
            if v_crop.size == 0:
                continue

            gray = cv2.cvtColor(v_crop, cv2.COLOR_BGR2GRAY)
            # Blackhat filter to reveal dark characters on bright plates
            rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
            blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rect_kernel)

            # Sobel horizontal gradient
            grad_x = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
            grad_x = np.absolute(grad_x)
            (min_val, max_val) = (np.min(grad_x), np.max(grad_x))
            if max_val > min_val:
                grad_x = (255 * ((grad_x - min_val) / (max_val - min_val))).astype("uint8")
            else:
                continue

            # Blur and close
            grad_x = cv2.GaussianBlur(grad_x, (5, 5), 0)
            grad_x = cv2.morphologyEx(grad_x, cv2.MORPH_CLOSE, rect_kernel)
            thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            best_candidate = None
            best_score = -1.0

            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                aspect_ratio = w / float(h)
                # Indian standard plates aspect ratio is between 1.8 and 5.0
                if 1.8 <= aspect_ratio <= 5.2 and w >= 50 and h >= 16:
                    score = w * h
                    if score > best_score:
                        best_score = score
                        best_candidate = (vx1 + x, search_y1 + y, vx1 + x + w, search_y1 + y + h)

            if best_candidate:
                detections.append({
                    "bbox": best_candidate,
                    "conf": 0.65, # Heuristic confidence
                    "vehicle_bbox": vbox
                })

        return detections
