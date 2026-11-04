"""
Triple Riding & Helmet Violation Detection Engine
Production-grade 2-stage spatial correlation:
1. Detects two-wheelers (motorcycle / scooter).
2. Extracts expanded rider catchment corridor (including head & seated torso zone).
3. Evaluates rider counts via localized person/head detector (>= 3 riders = Triple Riding under Sec 128/194C).
4. Evaluates helmet compliance via helmet_violation_yolov8.pt (bare head = Violation under Sec 129/194D).
5. Links detected number plate with the violator vehicle.
6. Returns structured violation payload + visual annotated evidence.
"""
from typing import List, Dict, Any, Tuple, Optional
import os
import cv2
import numpy as np
from ultralytics import YOLO

class TripleRidingDetector:
    def __init__(
        self,
        vehicle_model_path: str = "models/yolo/yolo11n.pt",
        rider_model_path: str = "models/yolo/yolo11n.pt",
        helmet_model_path: str = "models/yolo/helmet_violation_yolov8.pt",
        plate_model_path: str = "models/yolo/yolov8_plate.pt",
        conf_thresh: float = 0.25
    ):
        self.conf_thresh = conf_thresh
        self.veh_model = YOLO(vehicle_model_path) if os.path.exists(vehicle_model_path) else None
        self.rider_model = YOLO(rider_model_path) if os.path.exists(rider_model_path) else None
        self.helmet_model = YOLO(helmet_model_path) if os.path.exists(helmet_model_path) else None
        self.plate_model = YOLO(plate_model_path) if os.path.exists(plate_model_path) else None

    def evaluate_motorcycle(
        self,
        frame: np.ndarray,
        bike_bbox: List[int],
        detected_persons: Optional[List[Dict[str, Any]]] = None,
        plate_text: str = "",
        plate_conf: float = 0.0
    ) -> Dict[str, Any]:
        """
        Evaluates a specific detected motorcycle/scooter for Triple Riding and Helmet Violations.
        Hooked directly into ANPRPipeline.process_frame().
        """
        fh, fw = frame.shape[:2]
        mx1, my1, mx2, my2 = [int(v) for v in bike_bbox]
        mw, mh = mx2 - mx1, my2 - my1

        # Rider corridor bounding box
        cx1 = max(0, mx1 - int(mw * 0.15))
        cy1 = max(0, my1 - int(mh * 0.90))
        cx2 = min(fw, mx2 + int(mw * 0.15))
        cy2 = min(fh, my2 + int(mh * 0.10))

        # 1. Spatial catchment for seated riders
        bike_riders = []
        if detected_persons:
            for p in detected_persons:
                px1, py1, px2, py2 = [int(v) for v in p["box"]]
                overlap_x = max(0, min(mx2, px2) - max(mx1, px1))
                if overlap_x > 0.30 * (px2 - px1):
                    if py2 >= my1 - mh * 0.25 and py1 <= my2:
                        bike_riders.append(p)
        elif self.rider_model:
            # Crop seat zone and detect persons
            crop = frame[cy1:cy2, cx1:cx2]
            if crop.size > 0:
                r_res = self.rider_model.predict(crop, conf=0.25, verbose=False)[0]
                for b in r_res.boxes:
                    c_name = self.rider_model.names.get(int(b.cls[0]), "").lower()
                    if c_name in ["person", "rider"]:
                        r_conf = float(b.conf[0])
                        r_rel = b.xyxy[0].cpu().numpy().astype(int).tolist()
                        bike_riders.append({
                            "box": [cx1 + r_rel[0], cy1 + r_rel[1], cx1 + r_rel[2], cy1 + r_rel[3]],
                            "conf": r_conf
                        })

        rider_count = max(1, len(bike_riders))

        # 2. Helmet Detection: Evaluate Rider Context
        helmet_status = "UNKNOWN"
        helmet_conf = 0.0
        unhelmeted_count = 0
        helmeted_count = 0
        max_no_helmet_conf = 0.0
        max_with_helmet_conf = 0.0

        if self.helmet_model:
            # If explicit riders were detected, evaluate each rider crop
            if bike_riders:
                for p in bike_riders:
                    rx1, ry1, rx2, ry2 = p["box"]
                    rcrop = frame[max(0, ry1):min(fh, ry2), max(0, rx1):min(fw, rx2)]
                    if rcrop.size > 0:
                        h_res = self.helmet_model.predict(rcrop, conf=0.25, verbose=False)[0]
                        r_has_no_helmet = False
                        r_has_helmet = False
                        r_no_conf = 0.0
                        r_with_conf = 0.0
                        for hb in h_res.boxes:
                            raw_name = self.helmet_model.names[int(hb.cls[0].item())]
                            clean_name = raw_name.strip().lower()
                            c_val = float(hb.conf[0].item())
                            if "without" in clean_name or "no helmet" in clean_name:
                                if c_val > r_no_conf:
                                    r_no_conf = c_val
                            elif "with" in clean_name:
                                if c_val > r_with_conf:
                                    r_with_conf = c_val

                        if r_no_conf > max_no_helmet_conf:
                            max_no_helmet_conf = r_no_conf
                        if r_with_conf > max_with_helmet_conf:
                            max_with_helmet_conf = r_with_conf

                        if r_no_conf >= 0.35 and r_no_conf >= r_with_conf:
                            unhelmeted_count += 1
                        elif r_with_conf >= 0.35:
                            helmeted_count += 1
            else:
                # Fallback to corridor crop if no explicit person boxes
                corridor_crop = frame[cy1:cy2, cx1:cx2]
                if corridor_crop.size > 0:
                    h_res = self.helmet_model.predict(corridor_crop, conf=0.25, verbose=False)[0]
                    for hb in h_res.boxes:
                        raw_name = self.helmet_model.names[int(hb.cls[0].item())]
                        clean_name = raw_name.strip().lower()
                        c_val = float(hb.conf[0].item())
                        if "without" in clean_name or "no helmet" in clean_name:
                            if c_val > max_no_helmet_conf:
                                max_no_helmet_conf = c_val
                        elif "with" in clean_name:
                            if c_val > max_with_helmet_conf:
                                max_with_helmet_conf = c_val

                    if max_no_helmet_conf >= 0.35 and max_no_helmet_conf >= max_with_helmet_conf:
                        unhelmeted_count = 1
                    elif max_with_helmet_conf >= 0.35:
                        helmeted_count = 1

        if unhelmeted_count > 0:
            helmet_status = "Without helmet"
            helmet_conf = max_no_helmet_conf
        elif helmeted_count > 0:
            helmet_status = "With helmet"
            helmet_conf = max_with_helmet_conf

        # 3. Violation Logic
        is_triple = (rider_count >= 3)
        is_no_helmet = (unhelmeted_count > 0)
        is_violation = is_triple or is_no_helmet

        applied_sections = []
        triple_fine = 1000 if is_triple else 0
        helmet_fine = 1000 if is_no_helmet else 0

        if is_triple and is_no_helmet:
            violation_type = f"TRIPLE RIDING & NO HELMET ({rider_count} RIDERS, {unhelmeted_count} NO HELMET)" if rider_count > 1 else "TRIPLE RIDING & NO HELMET"
            applied_sections = [
                {"code": "Sec 128 r/w 194C", "title": "Overloading Two-Wheeler / Triple Riding", "fine": 1000},
                {"code": "Sec 129 r/w 194D", "title": f"Riding Without Helmet / Headgear ({unhelmeted_count} violator{'s' if unhelmeted_count > 1 else ''})", "fine": 1000 * unhelmeted_count}
            ]
        elif is_triple:
            violation_type = f"TRIPLE RIDING ({rider_count} RIDERS)"
            applied_sections = [
                {"code": "Sec 128 r/w 194C", "title": "Overloading Two-Wheeler / Triple Riding", "fine": 1000}
            ]
        elif is_no_helmet:
            violation_type = "SOLO DRIVER WITHOUT HELMET" if rider_count == 1 else f"RIDING WITHOUT HELMET ({unhelmeted_count} RIDERS)"
            applied_sections = [
                {"code": "Sec 129 r/w 194D", "title": f"Riding Without Helmet / Headgear ({unhelmeted_count} violator{'s' if unhelmeted_count > 1 else ''})", "fine": 1000 * unhelmeted_count}
            ]
        else:
            violation_type = "COMPLIANT"

        total_fine = triple_fine + (unhelmeted_count * helmet_fine)

        return {
            "is_violation": is_violation,
            "violation_type": violation_type,
            "rider_count": rider_count,
            "unhelmeted_count": unhelmeted_count,
            "helmet_status": helmet_status,
            "helmet_conf": round(helmet_conf * 100, 1),
            "triple_fine": triple_fine,
            "helmet_fine": helmet_fine,
            "applied_sections": applied_sections,
            "total_fine": total_fine,
            "plate_number": plate_text or "UNKNOWN",
            "plate_conf": plate_conf,
            "bike_bbox": [mx1, my1, mx2, my2]
        }
