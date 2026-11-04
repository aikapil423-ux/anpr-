"""
Track Merger Module
Implements the Vehicle-Level Identity Layer above ByteTrack.
Associates and merges discontinuous ByteTrack IDs into coherent vehicle identities
using appearance, kinematics, spatial continuity, plate location, and OCR similarity.
"""
from typing import List, Dict, Optional, Tuple
import cv2
import numpy as np
from config import IdentityMergerConfig
from src.identity.vehicle_identity import VehicleRecord, CandidateReading
from src.ocr.normalizer import IndianPlateNormalizer

class TrackMerger:
    def __init__(self, config: Optional[IdentityMergerConfig] = None):
        self.config = config or IdentityMergerConfig()
        self.normalizer = IndianPlateNormalizer()
        self._next_vehicle_id = 1
        
        # Vehicle records: vehicle_id -> VehicleRecord
        self.vehicles: Dict[int, VehicleRecord] = {}
        # Mapping from ByteTrack track_id -> vehicle_id
        self.track_to_vehicle: Dict[int, int] = {}
        # Inactive / recently lost vehicles for reconnection: vehicle_id -> VehicleRecord
        self.lost_vehicles: Dict[int, VehicleRecord] = {}

    def extract_appearance_hist(self, vehicle_crop: np.ndarray) -> Optional[np.ndarray]:
        """
        Extracts normalized Hue-Saturation 2D histogram as an appearance signature.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None
        try:
            hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)
            # Hue: 18 bins, Saturation: 16 bins
            hist = cv2.calcHist([hsv], [0, 1], None, [18, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
            return hist
        except Exception:
            return None

    def calculate_appearance_similarity(self, hist1: Optional[np.ndarray], hist2: Optional[np.ndarray]) -> float:
        if hist1 is None or hist2 is None:
            return 0.5 # Neutral score if missing
        try:
            # Correlation comparison (-1.0 to 1.0)
            score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            return max(0.0, float(score))
        except Exception:
            return 0.5

    def calculate_direction_similarity(self, v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
        mag1 = np.hypot(v1[0], v1[1])
        mag2 = np.hypot(v2[0], v2[1])
        if mag1 < 1e-3 or mag2 < 1e-3:
            return 0.5 # Near stationary
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cos_sim = dot / (mag1 * mag2)
        # Map [-1, 1] to [0, 1]
        return float(max(0.0, (cos_sim + 1.0) / 2.0))

    def calculate_spatial_similarity(
        self,
        v_rec: VehicleRecord,
        new_centroid: Tuple[float, float],
        frame_idx: int,
        frame_diag: float
    ) -> float:
        if not v_rec.trajectory:
            return 0.5
            
        last_centroid = v_rec.trajectory[-1]
        dt_frames = max(1, frame_idx - v_rec.last_frame)
        
        # Extrapolate expected position based on velocity
        vx, vy = v_rec.get_average_velocity()
        exp_x = last_centroid[0] + vx * dt_frames
        exp_y = last_centroid[1] + vy * dt_frames
        
        dist = np.hypot(new_centroid[0] - exp_x, new_centroid[1] - exp_y)
        norm_dist = dist / max(1.0, frame_diag)
        
        score = 1.0 - (norm_dist / self.config.max_spatial_distance_norm)
        return float(max(0.0, min(1.0, score)))

    def calculate_ocr_similarity(self, v_rec: VehicleRecord, new_reading: Optional[str]) -> float:
        if not new_reading or not v_rec.readings:
            return 0.0 # Strict: no similarity bonus if either lacks an OCR reading
            
        # Compare with the most frequent or highest confidence reading in v_rec
        existing_plates = [r.normalized_text for r in v_rec.readings if r.normalized_text and r.normalized_text != "UNREADABLE"]
        if not existing_plates:
            return 0.0
            
        best_sim = 0.0
        for plate in existing_plates[-5:]:
            sim = self.normalizer.calculate_levenshtein(plate, new_reading)
            if sim > best_sim:
                best_sim = sim
        return best_sim

    @staticmethod
    def _is_compatible_class(c1: Optional[str], c2: Optional[str]) -> bool:
        """Determines if two detected vehicle classes are compatible road vehicle types."""
        if not c1 or not c2:
            return True
        c1_low = c1.lower().strip()
        c2_low = c2.lower().strip()
        if c1_low == c2_low:
            return True
        four_wheelers = {"car", "truck", "bus", "van", "suv", "tempo", "vehicle", "automobile"}
        two_wheelers = {"motorcycle", "motorbike", "bike", "bicycle", "two-wheeler"}
        if (c1_low in four_wheelers and c2_low in four_wheelers):
            return True
        if (c1_low in two_wheelers and c2_low in two_wheelers):
            return True
        return False

    def find_matching_vehicle(
        self,
        track_id: int,
        frame_idx: int,
        timestamp: float,
        centroid: Tuple[float, float],
        velocity: Tuple[float, float],
        veh_crop: Optional[np.ndarray],
        candidate_ocr: Optional[str],
        frame_shape: Tuple[int, int],
        cls_name: Optional[str] = None
    ) -> Optional[int]:
        """
        Searches recently lost vehicles to see if this new track_id
        is a continuation of an existing vehicle identity.
        """
        frame_h, frame_w = frame_shape[:2]
        frame_diag = np.hypot(frame_w, frame_h)
        new_hist = self.extract_appearance_hist(veh_crop) if veh_crop is not None else None

        best_vehicle_id = None
        best_score = 0.0

        for vid, v_rec in list(self.lost_vehicles.items()):
            # 0. Class consistency: never merge incompatible vehicle types (e.g. motorcycle with car/truck)
            if cls_name and v_rec.vehicle_class and getattr(self.config, "require_same_class", True):
                if not self._is_compatible_class(cls_name, v_rec.vehicle_class):
                    continue

            time_gap = timestamp - v_rec.last_timestamp
            frame_gap = frame_idx - v_rec.last_frame
            max_gap_sec = getattr(self.config, "max_time_gap_seconds", 2.0)
            max_gap_frames = getattr(self.config, "max_track_gap_frames", 60)
            if time_gap < 0 or time_gap > max_gap_sec or frame_gap > max_gap_frames:
                continue

            # 1. Appearance similarity
            s_app = self.calculate_appearance_similarity(v_rec.appearance_hist, new_hist)

            # 2. Spatial continuity
            s_loc = self.calculate_spatial_similarity(v_rec, centroid, frame_idx, frame_diag)

            # 3. Direction similarity
            s_dir = self.calculate_direction_similarity(v_rec.get_average_velocity(), velocity)

            # 4. OCR similarity
            s_ocr = self.calculate_ocr_similarity(v_rec, candidate_ocr)

            # If no OCR is available on either, require strong appearance & spatial continuity
            if s_ocr == 0.0 and (s_app < 0.75 or s_loc < 0.50):
                continue

            # Weighted composite score
            composite = (
                self.config.weight_appearance * s_app +
                self.config.weight_location * s_loc +
                self.config.weight_direction * s_dir +
                self.config.weight_ocr * s_ocr
            )

            # Bonus if OCR strongly matches (very strong signal of same vehicle)
            if s_ocr >= 0.85:
                composite = min(1.0, composite + 0.20)

            if composite > best_score and composite >= self.config.merge_threshold:
                best_score = composite
                best_vehicle_id = vid

        return best_vehicle_id

    def register_or_update_track(
        self,
        track_id: int,
        frame_idx: int,
        timestamp: float,
        veh_bbox: Tuple[int, int, int, int],
        plate_bbox: Optional[Tuple[int, int, int, int]] = None,
        veh_crop: Optional[np.ndarray] = None,
        candidate_reading: Optional[CandidateReading] = None,
        frame_shape: Tuple[int, int] = (1080, 1920),
        cls_name: Optional[str] = None
    ) -> int:
        """
        Assigns the track_id to a VehicleRecord (either existing, merged, or newly created).
        Returns the vehicle_id.
        """
        cx = (veh_bbox[0] + veh_bbox[2]) / 2.0
        cy = (veh_bbox[1] + veh_bbox[3]) / 2.0
        candidate_ocr = candidate_reading.normalized_text if candidate_reading else None

        # Case 1: Track ID already assigned to a vehicle
        if track_id in self.track_to_vehicle:
            vehicle_id = self.track_to_vehicle[track_id]
            v_rec = self.vehicles[vehicle_id]
            
            frame_gap = frame_idx - v_rec.last_frame
            time_gap = timestamp - v_rec.last_timestamp
            max_gap_frames = getattr(self.config, "max_track_gap_frames", 60)
            max_gap_sec = getattr(self.config, "max_time_gap_seconds", 2.0)

            # Check if ByteTrack recycled this track_id or class changed incompatibly
            class_mismatch = False
            if cls_name and v_rec.vehicle_class and getattr(self.config, "require_same_class", True):
                if not self._is_compatible_class(cls_name, v_rec.vehicle_class):
                    class_mismatch = True
            is_stale = (frame_gap > max_gap_frames) or (time_gap > max_gap_sec)
            # ByteTrack track continuity: As long as the track is actively continuous (gap <= max_gap),
            # keep it bound to the same vehicle identity. Never split active ByteTrack IDs on OCR mismatch;
            # let Temporal Voting Engine accumulate all readings and elect the highest-confidence winner.
            if is_stale or class_mismatch:
                # ByteTrack reused track_id across significant time gap or vehicle class mismatch!
                # Detach from old vehicle record and process as fresh track
                del self.track_to_vehicle[track_id]
            else:
                v_rec.active = True
                if cls_name and not v_rec.vehicle_class:
                    v_rec.vehicle_class = cls_name

                # Compute instantaneous velocity
                if v_rec.trajectory:
                    prev_x, prev_y = v_rec.trajectory[-1]
                    dt = max(1, abs(frame_idx - v_rec.last_frame))
                    v_rec.velocities.append(((cx - prev_x) / dt, (cy - prev_y) / dt))

                v_rec.trajectory.append((cx, cy))
                if frame_idx >= v_rec.last_frame:
                    v_rec.last_frame = frame_idx
                    v_rec.last_timestamp = timestamp
                    v_rec.last_vehicle_bbox = veh_bbox
                    v_rec.last_plate_bbox = plate_bbox

                # Update appearance
                if veh_crop is not None:
                    new_hist = self.extract_appearance_hist(veh_crop)
                    if new_hist is not None:
                        if v_rec.appearance_hist is None:
                            v_rec.appearance_hist = new_hist
                        else:
                            # Exponential moving average
                            v_rec.appearance_hist = 0.8 * v_rec.appearance_hist + 0.2 * new_hist

                if candidate_reading:
                    v_rec.add_reading(candidate_reading)

                return vehicle_id

        # Case 2: New track_id encountered. Check if it matches a recently lost vehicle
        matched_vid = self.find_matching_vehicle(
            track_id=track_id,
            frame_idx=frame_idx,
            timestamp=timestamp,
            centroid=(cx, cy),
            velocity=(0.0, 0.0),
            veh_crop=veh_crop,
            candidate_ocr=candidate_ocr,
            frame_shape=frame_shape,
            cls_name=cls_name
        )

        if matched_vid is not None:
            # Merge track_id into existing vehicle
            vehicle_id = matched_vid
            v_rec = self.vehicles[vehicle_id]
            v_rec.linked_track_ids.add(track_id)
            self.track_to_vehicle[track_id] = vehicle_id
            
            if cls_name and not v_rec.vehicle_class:
                v_rec.vehicle_class = cls_name

            # Remove from lost_vehicles since it is active again
            if vehicle_id in self.lost_vehicles:
                del self.lost_vehicles[vehicle_id]

            v_rec.active = True
            v_rec.last_frame = frame_idx
            v_rec.last_timestamp = timestamp
            v_rec.trajectory.append((cx, cy))
            v_rec.last_vehicle_bbox = veh_bbox
            v_rec.last_plate_bbox = plate_bbox

            if candidate_reading:
                v_rec.add_reading(candidate_reading)

            return vehicle_id

        # Case 3: Create a brand new vehicle record
        vehicle_id = self._next_vehicle_id
        self._next_vehicle_id += 1

        v_rec = VehicleRecord(
            vehicle_id=vehicle_id,
            linked_track_ids={track_id},
            first_frame=frame_idx,
            last_frame=frame_idx,
            first_timestamp=timestamp,
            last_timestamp=timestamp,
            active=True,
            trajectory=[(cx, cy)],
            last_vehicle_bbox=veh_bbox,
            last_plate_bbox=plate_bbox,
            vehicle_class=cls_name or ""
        )

        if veh_crop is not None:
            v_rec.appearance_hist = self.extract_appearance_hist(veh_crop)

        if candidate_reading:
            v_rec.add_reading(candidate_reading)

        self.vehicles[vehicle_id] = v_rec
        self.track_to_vehicle[track_id] = vehicle_id
        return vehicle_id

    def mark_tracks_lost(self, active_track_ids: List[int], current_timestamp: float):
        """
        Marks vehicles whose tracks are no longer active as lost,
        and cleans up stale lost vehicles.
        """
        active_track_set = set(active_track_ids)
        for vid, v_rec in self.vehicles.items():
            # Check if any linked track is active
            has_active_track = any(tid in active_track_set for tid in v_rec.linked_track_ids)
            if not has_active_track and v_rec.active:
                v_rec.active = False
                self.lost_vehicles[vid] = v_rec

        # Prune expired lost vehicles and purge from track_to_vehicle map
        max_retention = getattr(self.config, "max_time_gap_seconds", 2.0) * 2.5
        expired = [
            vid for vid, v in self.lost_vehicles.items()
            if (current_timestamp - v.last_timestamp) > max_retention
        ]
        for vid in expired:
            v_exp = self.lost_vehicles.get(vid)
            if v_exp:
                for tid in list(v_exp.linked_track_ids):
                    if self.track_to_vehicle.get(tid) == vid:
                        del self.track_to_vehicle[tid]
            del self.lost_vehicles[vid]

    def reset(self):
        """Clears all vehicle tracks, active mapping, and resets ID counter."""
        self.vehicles.clear()
        self.track_to_vehicle.clear()
        self.lost_vehicles.clear()
        self._next_vehicle_id = 1
