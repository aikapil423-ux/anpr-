"""
Behavior Intelligence Lab - Stage 1 Pose & Kinetic Heuristic Engine
Runs 24x7 real-time pose tracking using YOLO-Pose.
Calculates kinetic velocity, inter-person proximity, and interaction overlap.
ONLY flags candidates when strict mathematical thresholds are met.
"""
import os
import torch
if hasattr(torch, "set_num_threads"):
    try:
        torch.set_num_threads(os.cpu_count() or 4)
    except Exception:
        pass
import numpy as np
import cv2
from typing import List, Dict, Any, Tuple, Optional
from ultralytics import YOLO

# COCO Keypoint Indices for Reference:
# 0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear
# 5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow
# 9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip
# 13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle

class PoseBehaviorDetector:
    def __init__(
        self,
        model_path: str = "yolo11m-pose.pt",
        conf_thresh: float = 0.35,
        target_imgsz: int = 640
    ):
        print(f"[Stage 1 Detector] Initializing Local Pose Model: {model_path}...")
        self.model = YOLO(model_path)
        self.conf_thresh = conf_thresh
        self.imgsz = target_imgsz

        # History tracking across consecutive frames
        # track_id -> deque of (timestamp, centroid, wrist_positions, bbox)
        self.person_history: Dict[int, List[Dict[str, Any]]] = {}
        self.max_history_len = 30  # keep ~1-1.5 seconds history

        # Fight candidate persistence counter
        self.fight_candidate_frames = 0
        self.fight_trigger_threshold = 12  # Must persist for ~12-15 consecutive frames

    def _compute_iou(self, boxA, boxB) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        denom = float(boxAArea + boxBArea - interArea)
        return interArea / denom if denom > 0 else 0.0

    def analyze_frame(
        self,
        frame: np.ndarray,
        frame_idx: int,
        timestamp: float
    ) -> Dict[str, Any]:
        """
        Processes a single frame:
        Returns:
        - persons: List of detected persons with keypoints
        - is_fight_candidate: bool (True only if multi-rule kinetic criteria met)
        - candidate_metadata: Dict with metrics (wrist velocity, overlap, etc.)
        - annotated_frame: visual overlay
        """
        results = self.model.track(
            frame,
            persist=True,
            conf=self.conf_thresh,
            imgsz=self.imgsz,
            verbose=False
        )

        detected_persons = []
        annotated = frame.copy()

        if not results or len(results) == 0 or results[0].boxes is None:
            return {
                "detected_count": 0,
                "is_fight_candidate": False,
                "candidate_metadata": None,
                "annotated_frame": annotated
            }

        r = results[0]
        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        track_ids = r.boxes.id.cpu().numpy().astype(int) if r.boxes.id is not None else list(range(len(boxes)))

        has_keypoints = r.keypoints is not None and r.keypoints.data is not None
        keypoints_data = r.keypoints.data.cpu().numpy() if has_keypoints else None

        for i in range(len(boxes)):
            tid = int(track_ids[i])
            bbox = [int(v) for v in boxes[i]]
            conf = float(confs[i])
            kpts = keypoints_data[i] if (keypoints_data is not None and i < len(keypoints_data)) else None

            # Calculate centroid
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0

            # Extract wrists (9=left, 10=right)
            lwrist = kpts[9][:2] if (kpts is not None and len(kpts) > 9 and kpts[9][2] > 0.3) else None
            rwrist = kpts[10][:2] if (kpts is not None and len(kpts) > 10 and kpts[10][2] > 0.3) else None

            p_obj = {
                "track_id": tid,
                "bbox": bbox,
                "centroid": (cx, cy),
                "conf": conf,
                "lwrist": lwrist,
                "rwrist": rwrist,
                "keypoints": kpts
            }
            detected_persons.append(p_obj)

            # Update historical trajectory
            if tid not in self.person_history:
                self.person_history[tid] = []
            self.person_history[tid].append({
                "time": timestamp,
                "frame": frame_idx,
                "centroid": (cx, cy),
                "lwrist": lwrist,
                "rwrist": rwrist,
                "bbox": bbox
            })
            if len(self.person_history[tid]) > self.max_history_len:
                self.person_history[tid].pop(0)

            # Draw basic box on annotated frame
            cv2.rectangle(annotated, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 128), 2)
            cv2.putText(annotated, f"Person #{tid}", (bbox[0], max(18, bbox[1] - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 128), 2)

        # -------------------------------------------------------------
        # Pairwise Interaction & Kinetic Anomaly Check (The Gatekeeper)
        # -------------------------------------------------------------
        is_suspicious_interaction = False
        highest_kinetic_score = 0.0
        interaction_meta = {}

        n_p = len(detected_persons)
        for i in range(n_p):
            for j in range(i + 1, n_p):
                pA = detected_persons[i]
                pB = detected_persons[j]

                # 1. Proximity Check
                c1 = pA["centroid"]
                c2 = pB["centroid"]
                dist = np.sqrt((c1[0] - c2[0])**2 + (c1[1] - c2[1])**2)
                avg_height = ((pA["bbox"][3] - pA["bbox"][1]) + (pB["bbox"][3] - pB["bbox"][1])) / 2.0

                # Must be in striking distance (within ~1.2x body height)
                if dist > (avg_height * 1.3):
                    continue

                # 2. Bounding Box Overlap (Grappling/Clash)
                overlap_iou = self._compute_iou(pA["bbox"], pB["bbox"])

                # 3. Kinetic Velocity of Wrists
                vA_wrist = self._calculate_max_wrist_velocity(pA["track_id"])
                vB_wrist = self._calculate_max_wrist_velocity(pB["track_id"])
                peak_wrist_vel = max(vA_wrist, vB_wrist)

                # Combined Suspicion Score
                # High velocity + High overlap in striking range = High Fight Suspicion
                kinetic_score = 0.0
                if overlap_iou > 0.15:
                    kinetic_score += (overlap_iou * 40.0)  # up to 40 pts
                if peak_wrist_vel > 80.0:  # Fast hand swing
                    kinetic_score += min(50.0, (peak_wrist_vel - 80.0) * 0.5)

                if kinetic_score > 45.0 or (overlap_iou > 0.35 and peak_wrist_vel > 60.0):
                    is_suspicious_interaction = True
                    highest_kinetic_score = max(highest_kinetic_score, kinetic_score)
                    interaction_meta = {
                        "person_A_id": pA["track_id"],
                        "person_B_id": pB["track_id"],
                        "overlap_iou": round(float(overlap_iou), 2),
                        "wrist_velocity_px_s": round(float(peak_wrist_vel), 1),
                        "kinetic_score": round(float(highest_kinetic_score), 1),
                        "proximity_dist_px": round(float(dist), 1)
                    }

        # -------------------------------------------------------------
        # Consecutive Persistence Gate
        # -------------------------------------------------------------
        if is_suspicious_interaction:
            self.fight_candidate_frames += 1
        else:
            self.fight_candidate_frames = max(0, self.fight_candidate_frames - 2)

        # Trigger candidate ONLY if sustained over consecutive frames
        trigger_confirmed = (self.fight_candidate_frames >= self.fight_trigger_threshold)

        if is_suspicious_interaction:
            cv2.putText(annotated, f"KINETIC SUSPICION: {highest_kinetic_score:.1f} (Frames: {self.fight_candidate_frames}/{self.fight_trigger_threshold})",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

        if trigger_confirmed:
            cv2.putText(annotated, "STAGE 1 TRIGGER: SENDING TO AI VERIFIER!",
                        (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)

        return {
            "detected_count": n_p,
            "is_fight_candidate": trigger_confirmed,
            "candidate_metadata": interaction_meta if trigger_confirmed else None,
            "annotated_frame": annotated
        }

    def _calculate_max_wrist_velocity(self, track_id: int) -> float:
        """Computes pixel velocity of wrists over recent history"""
        hist = self.person_history.get(track_id, [])
        if len(hist) < 3:
            return 0.0

        latest = hist[-1]
        previous = hist[-3]
        dt = latest["time"] - previous["time"]
        if dt <= 0:
            return 0.0

        max_vel = 0.0
        for side in ["lwrist", "rwrist"]:
            if latest[side] is not None and previous[side] is not None:
                p1 = latest[side]
                p0 = previous[side]
                disp = np.sqrt((p1[0] - p0[0])**2 + (p1[1] - p0[1])**2)
                vel = disp / dt
                max_vel = max(max_vel, vel)

        return max_vel

    def reset_trigger(self):
        """Resets candidate persistence counter after an event is handed off"""
        self.fight_candidate_frames = 0
        self.person_history.clear()
