"""
Vehicle Detector & ByteTrack Integration Module
Uses YOLO11 for vehicle detection (classes: bicycle, car, motorcycle, bus, truck)
and Ultralytics ByteTrack for low-level frame-by-frame tracking.
"""
import os
import threading
import torch
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import cv2
from pathlib import Path
from ultralytics import YOLO
from config import VEHICLE_MODEL_PATH

# Optimize PyTorch CPU threading for maximum throughput
if hasattr(torch, "set_num_threads"):
    try:
        torch.set_num_threads(os.cpu_count() or 4)
    except Exception:
        pass

# COCO vehicle classes: 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck; person class: 0
DEFAULT_VEHICLE_CLASSES = [1, 2, 3, 5, 7]
DEFAULT_PERSON_CLASSES = [0]
DEFAULT_ALL_CLASSES = [0, 1, 2, 3, 5, 7]

class VehicleDetector:
    def __init__(
        self,
        model_name: Optional[str] = None,
        classes: Optional[List[int]] = None,
        conf_thresh: float = 0.22,
        iou_thresh: float = 0.45,
        enable_people: bool = True
    ):
        self.model_name = self._resolve_model(model_name or VEHICLE_MODEL_PATH)
        try:
            self.model = YOLO(self.model_name)
        except Exception as e:
            print(f"[WARN] Failed to load YOLO vehicle model from {self.model_name}: {e}. Retrying with yolo11n.pt")
            self.model = YOLO("yolo11n.pt")

        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        self.enable_people = enable_people
        self._setup_classes(classes)

        # Custom ByteTrack configuration for surveillance (60-frame buffer)
        custom_tracker = Path(__file__).resolve().parent / "bytetrack_surveillance.yaml"
        self.tracker_config = str(custom_tracker) if custom_tracker.is_file() else "bytetrack.yaml"

        # Cumulative tracking telemetry for people counting
        self.unique_person_tracks = set()
        self.last_persons = []

        self._swap_lock = threading.Lock()

    def _setup_classes(self, custom_classes: Optional[List[int]] = None):
        """Dynamically configures vehicle and person classes based on active YOLO model's class ontology."""
        if custom_classes is not None:
            self.vehicle_classes = [c for c in custom_classes if c != 0]
            self.person_classes = DEFAULT_PERSON_CLASSES if self.enable_people else []
        elif hasattr(self.model, "names") and self.model.names:
            names_dict = self.model.names
            person_synonyms = {"person", "pedestrian", "people", "human", "crowd"}
            self.person_classes = [
                k for k, v in names_dict.items()
                if str(v).lower() in person_synonyms
            ] if self.enable_people else []

            veh_synonyms = {
                "car", "motorcycle", "bus", "truck", "bicycle", "vehicle", "auto",
                "hatchback", "sedan", "suv", "muv", "three-wheeler", "two-wheeler",
                "lcv", "mini-bus", "tempo-traveller", "van", "tractor", "train"
            }
            matched_veh = [k for k, v in names_dict.items() if str(v).lower() in veh_synonyms]
            if matched_veh:
                if len(names_dict) <= 20:
                    self.vehicle_classes = [k for k in names_dict.keys() if k not in self.person_classes]
                else:
                    self.vehicle_classes = matched_veh
            else:
                self.vehicle_classes = [k for k in names_dict.keys() if k not in self.person_classes]

            if not self.vehicle_classes:
                self.vehicle_classes = [c for c in DEFAULT_VEHICLE_CLASSES if c != 0]
        else:
            self.vehicle_classes = [c for c in DEFAULT_VEHICLE_CLASSES if c != 0]
            self.person_classes = DEFAULT_PERSON_CLASSES if self.enable_people else []

        self.all_classes = sorted(list(set(self.vehicle_classes + self.person_classes)))
        self.classes = self.all_classes

    def _resolve_model(self, initial_path: Optional[str]) -> str:
        """Resolves model path across candidate locations, strictly avoiding OpenVINO."""
        def _is_valid(path: Optional[str]) -> bool:
            if not path:
                return False
            p = Path(path)
            # Strictly require .pt file, skip any OpenVINO directories
            if p.is_file() and p.stat().st_size > 1000 and not p.name.endswith(".xml"):
                return True
            return False

        if _is_valid(initial_path):
            return str(initial_path)

        # Check in model registry
        try:
            from src.detection.model_registry import registry
            resolved = registry.resolve_model_path(initial_path or "yolo26x")
            if _is_valid(resolved):
                return resolved
        except Exception:
            pass

        base_dir = Path(__file__).resolve().parent.parent.parent
        candidates = [
            str(base_dir / "models" / "yolo" / "uvh26_yolo11x.pt"),
            str(base_dir / "models" / "yolo" / "driveindia_tihan_yolov10x.pt"),
            str(base_dir / "models" / "yolo" / "driveindia_tihan_yolov10m.pt"),
            str(base_dir / "models" / "yolo" / "yolo26x.pt"),
            str(base_dir / "models" / "yolo" / "yolo26s.pt"),
            str(base_dir / "models" / "yolo" / "yolo11n.pt"),
            str(base_dir / "models" / "yolo" / "yolo11m.pt"),
            str(base_dir / "yolo26x.pt"),
            str(base_dir / "yolo11n.pt"),
        ]
        for c in candidates:
            if _is_valid(c):
                return c

        return "yolo26x.pt"

    def switch_model(self, new_model_name: str) -> bool:
        """Dynamically hot-swaps active vehicle YOLO model without resetting tracker states."""
        resolved = self._resolve_model(new_model_name)
        try:
            new_model = YOLO(resolved)
            with self._swap_lock:
                self.model = new_model
                self.model_name = resolved
                self._setup_classes()
            print(f"[VehicleDetector] Successfully switched active vehicle model to {resolved} (Veh classes: {len(self.vehicle_classes)}, Person classes: {len(self.person_classes)})")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to switch vehicle model to {new_model_name} ({resolved}): {e}")
            return False

    def reset(self):
        """Resets internal ByteTrack tracker states and people tracking telemetry."""
        try:
            if hasattr(self.model, "predictor") and self.model.predictor is not None:
                trackers = getattr(self.model.predictor, "trackers", [])
                for t in trackers:
                    if hasattr(t, "reset"):
                        t.reset()
                    if hasattr(t, "reset_id"):
                        t.reset_id()
        except Exception:
            pass
        self.unique_person_tracks.clear()
        self.last_persons = []

    def track_all(
        self,
        frame: np.ndarray,
        persist: bool = True
    ) -> Dict[str, Any]:
        """
        Runs YOLO11 + ByteTrack tracking for both vehicles and people in a single forward pass.
        Returns segregated dictionaries for vehicles and persons.
        """
        track_imgsz = 480 if "openvino" in str(self.model_name).lower() else 640
        results = self.model.track(
            frame,
            persist=persist,
            classes=self.all_classes,
            conf=self.conf_thresh,
            iou=self.iou_thresh,
            imgsz=track_imgsz,
            tracker=self.tracker_config,
            verbose=False
        )

        vehicles = []
        persons = []

        if not results or len(results) == 0:
            return {
                "vehicles": vehicles,
                "persons": persons,
                "people_count": 0,
                "total_unique_people": len(self.unique_person_tracks)
            }

        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            return {
                "vehicles": vehicles,
                "persons": persons,
                "people_count": 0,
                "total_unique_people": len(self.unique_person_tracks)
            }

        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy().astype(int)
        track_ids = r.boxes.id.cpu().numpy().astype(int) if r.boxes.id is not None else None

        h, w = frame.shape[:2]
        for i in range(len(boxes)):
            tid = int(track_ids[i]) if track_ids is not None else (i + 1)
            x1, y1, x2, y2 = [int(v) for v in boxes[i]]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)

            cls_id = int(classes[i])
            cls_name = self.model.names.get(cls_id, str(cls_id))

            det_obj = {
                "track_id": tid,
                "bbox": (x1, y1, x2, y2),
                "conf": float(confs[i]),
                "cls_id": cls_id,
                "cls_name": cls_name
            }

            if cls_id in self.person_classes:
                if track_ids is not None and tid >= 0:
                    self.unique_person_tracks.add(tid)
                persons.append(det_obj)
            elif cls_id in self.vehicle_classes:
                vehicles.append(det_obj)

        return {
            "vehicles": vehicles,
            "persons": persons,
            "people_count": len(persons),
            "total_unique_people": len(self.unique_person_tracks)
        }

    def track(
        self,
        frame: np.ndarray,
        persist: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Backwards-compatible tracking method returning only tracked vehicles for ANPR pipeline.
        Caches last_persons from the single YOLO pass to avoid redundant person inferences.
        """
        all_res = self.track_all(frame, persist=persist)
        self.last_persons = all_res.get("persons", [])
        return all_res["vehicles"]

    def detect_image(
        self,
        frame: np.ndarray
    ) -> Dict[str, Any]:
        """
        Runs non-tracked object prediction on a static photo (for single-image uploads).
        """
        pred_imgsz = 480 if "openvino" in str(self.model_name).lower() else 640
        results = self.model.predict(
            frame,
            classes=self.all_classes,
            conf=self.conf_thresh,
            iou=self.iou_thresh,
            imgsz=pred_imgsz,
            verbose=False
        )

        vehicles = []
        persons = []

        if not results or len(results) == 0:
            return {"vehicles": vehicles, "persons": persons}

        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            return {"vehicles": vehicles, "persons": persons}

        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy().astype(int)

        h, w = frame.shape[:2]
        for i in range(len(boxes)):
            x1, y1, x2, y2 = [int(v) for v in boxes[i]]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)

            cls_id = int(classes[i])
            cls_name = self.model.names.get(cls_id, str(cls_id))

            det_obj = {
                "track_id": i + 1,
                "bbox": (x1, y1, x2, y2),
                "conf": float(confs[i]),
                "cls_id": cls_id,
                "cls_name": cls_name
            }

            if cls_id in self.person_classes:
                persons.append(det_obj)
            elif cls_id in self.vehicle_classes:
                vehicles.append(det_obj)

        return {"vehicles": vehicles, "persons": persons}
