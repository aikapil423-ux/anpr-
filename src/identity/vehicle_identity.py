"""
Vehicle Identity Data Structures
Represents candidate readings, vehicle tracks, and vehicle-level identity records.
"""
from dataclasses import dataclass, field
from typing import List, Set, Tuple, Optional, Dict, Any
import numpy as np

@dataclass
class CandidateReading:
    frame_idx: int
    timestamp: float
    track_id: int
    raw_text: str
    normalized_text: str
    is_valid_format: bool
    format_type: str
    ocr_confidence: float
    detection_confidence: float
    blur_score: float
    crop_image: np.ndarray
    vehicle_bbox: Tuple[int, int, int, int]
    plate_bbox: Tuple[int, int, int, int]
    vehicle_crop: Optional[np.ndarray] = None
    annotated_frame: Optional[np.ndarray] = None
    enhanced_crop: Optional[np.ndarray] = None
    preprocessing_meta: Optional[Dict[str, Any]] = None

@dataclass
class EvidenceFrame:
    frame_idx: int
    track_id: int
    text: str
    confidence: float
    crop_image: np.ndarray
    raw_text: str = ""
    ocr_confidence: float = 0.0
    det_confidence: float = 0.0
    vehicle_crop: Optional[np.ndarray] = None
    timestamp: float = 0.0

@dataclass
class VehicleRecord:
    vehicle_id: int
    linked_track_ids: Set[int] = field(default_factory=set)
    first_frame: int = 0
    last_frame: int = 0
    first_timestamp: float = 0.0
    last_timestamp: float = 0.0
    active: bool = True
    
    # Trajectory and kinematics:
    trajectory: List[Tuple[float, float]] = field(default_factory=list) # vehicle centroid (cx, cy)
    velocities: List[Tuple[float, float]] = field(default_factory=list) # (vx, vy)
    last_vehicle_bbox: Optional[Tuple[int, int, int, int]] = None
    last_plate_bbox: Optional[Tuple[int, int, int, int]] = None
    
    # Appearance feature:
    appearance_hist: Optional[np.ndarray] = None
    vehicle_class: str = "" # COCO class name (car, motorcycle, bus, truck)
    ocr_attempts: int = 0   # Count of OCR passes triggered for this vehicle

    # All valid OCR readings collected across all frames and tracks:
    readings: List[CandidateReading] = field(default_factory=list)
    
    # Final consolidated state:
    final_plate: str = ""
    display_plate: str = ""
    final_confidence: float = 0.0
    format_type: str = "standard"
    is_valid_format: bool = False
    is_verified: bool = False
    is_saturated: bool = False
    alert_state: str = "NORMAL" # NORMAL (Blue), SUSPECT (Orange), HOTLIST (Red)
    alert_reason: str = ""
    best_plate_det_conf: float = 0.0
    status: str = "ACTIVE" # ACTIVE, VERIFIED, NEEDS_REVIEW, REJECTED
    review_reason: str = ""
    
    best_crop: Optional[np.ndarray] = None
    best_vehicle_crop: Optional[np.ndarray] = None
    best_annotated_frame: Optional[np.ndarray] = None
    best_enhanced_crop: Optional[np.ndarray] = None
    preprocessing_meta: Optional[Dict[str, Any]] = None
    best_crop_score: float = -1.0
    max_plate_area: float = 0.0      # Peak plate bbox area (W * H) for Golden Frame tracking
    golden_frame_idx: int = -1       # Frame index of peak clarity / proximity
    evidence_frames: List[EvidenceFrame] = field(default_factory=list)
    candidate_slots: List[CandidateReading] = field(default_factory=list)

    def add_reading(self, reading: CandidateReading, max_evidence: int = 15):
        self.readings.append(reading)
        
        # Track plate bbox area for Golden Frame proximity selection
        pw = max(0, reading.plate_bbox[2] - reading.plate_bbox[0]) if reading.plate_bbox else 0
        ph = max(0, reading.plate_bbox[3] - reading.plate_bbox[1]) if reading.plate_bbox else 0
        current_area = float(pw * ph)
        if current_area > self.max_plate_area:
            self.max_plate_area = current_area

        # Track composite Golden Frame clarity score: sqrt(Area) * log(1 + Blur) * Effective Confidence
        effective_conf = reading.ocr_confidence if reading.ocr_confidence > 0 else (reading.detection_confidence * 0.5)
        clarity_score = np.sqrt(max(1.0, current_area)) * np.log1p(max(1.0, reading.blur_score)) * effective_conf
        if clarity_score > self.best_crop_score:
            self.best_crop_score = clarity_score
            self.golden_frame_idx = reading.frame_idx
            if reading.crop_image is not None and reading.crop_image.size > 0:
                self.best_crop = reading.crop_image.copy()
            if reading.vehicle_crop is not None and reading.vehicle_crop.size > 0:
                self.best_vehicle_crop = reading.vehicle_crop.copy()
            if reading.annotated_frame is not None and reading.annotated_frame.size > 0:
                self.best_annotated_frame = reading.annotated_frame.copy()

        # Update evidence frames (keep highest confidence unique frames)
        ev_conf = reading.ocr_confidence if reading.ocr_confidence > 0 else (reading.detection_confidence * 0.5)
        if reading.crop_image is not None and reading.crop_image.size > 0:
            existing_indices = [i for i, ef in enumerate(self.evidence_frames) if ef.frame_idx == reading.frame_idx]
            v_crop_copy = reading.vehicle_crop.copy() if reading.vehicle_crop is not None and reading.vehicle_crop.size > 0 else None
            new_ef = EvidenceFrame(
                frame_idx=reading.frame_idx,
                track_id=reading.track_id,
                text=reading.normalized_text,
                confidence=ev_conf,
                crop_image=reading.crop_image.copy(),
                raw_text=reading.raw_text,
                ocr_confidence=reading.ocr_confidence,
                det_confidence=reading.detection_confidence,
                vehicle_crop=v_crop_copy,
                timestamp=getattr(reading, "timestamp", 0.0)
            )
            if existing_indices:
                idx = existing_indices[0]
                if ev_conf > self.evidence_frames[idx].confidence:
                    self.evidence_frames[idx] = new_ef
            elif len(self.evidence_frames) < max_evidence:
                self.evidence_frames.append(new_ef)
            else:
                # Replace lowest confidence frame if current is better
                min_idx = min(range(len(self.evidence_frames)), key=lambda i: self.evidence_frames[i].confidence)
                if ev_conf > self.evidence_frames[min_idx].confidence:
                    self.evidence_frames[min_idx] = new_ef


    def update_candidate_slots(self, reading: CandidateReading, max_slots: int = 3):
        """Maintains Top-3 sliding candidate slots ordered by composite visual quality."""
        pw, ph = 0, 0
        if reading.plate_bbox:
            pw = max(0, reading.plate_bbox[2] - reading.plate_bbox[0])
            ph = max(0, reading.plate_bbox[3] - reading.plate_bbox[1])
        bbox_area = max(1, pw * ph)
        score = reading.detection_confidence * np.sqrt(bbox_area) * np.log1p(max(0.0, reading.blur_score))

        if len(self.candidate_slots) < max_slots:
            self.candidate_slots.append(reading)
        else:
            min_idx = -1
            min_score = float('inf')
            for idx, cand in enumerate(self.candidate_slots):
                cpw, cph = 0, 0
                if cand.plate_bbox:
                    cpw = max(0, cand.plate_bbox[2] - cand.plate_bbox[0])
                    cph = max(0, cand.plate_bbox[3] - cand.plate_bbox[1])
                c_area = max(1, cpw * cph)
                c_score = cand.detection_confidence * np.sqrt(c_area) * np.log1p(max(0.0, cand.blur_score))
                if c_score < min_score:
                    min_score = c_score
                    min_idx = idx
            if score > min_score and min_idx >= 0:
                self.candidate_slots[min_idx] = reading

    def get_average_velocity(self) -> Tuple[float, float]:
        if not self.velocities:
            return (0.0, 0.0)
        # Average over recent velocities
        recent = self.velocities[-5:]
        vx = float(np.mean([v[0] for v in recent]))
        vy = float(np.mean([v[1] for v in recent]))
        return (vx, vy)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vehicle_id": self.vehicle_id,
            "linked_track_ids": sorted(list(self.linked_track_ids)),
            "first_frame": self.first_frame,
            "last_frame": self.last_frame,
            "duration_frames": self.last_frame - self.first_frame + 1,
            "final_plate": self.final_plate,
            "display_plate": self.display_plate,
            "final_confidence": round(float(self.final_confidence), 4),
            "is_verified": self.is_verified,
            "is_saturated": self.is_saturated,
            "alert_state": self.alert_state,
            "alert_reason": self.alert_reason,
            "status": self.status,
            "review_reason": self.review_reason,
            "supporting_frames_count": len(self.readings),
            "evidence_count": len(self.evidence_frames)
        }
