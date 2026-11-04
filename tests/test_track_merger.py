"""
Unit tests for Vehicle-Level Identity Layer and Track Merger
"""
import numpy as np
import cv2
from src.identity.track_merger import TrackMerger
from src.identity.vehicle_identity import CandidateReading
from config import IdentityMergerConfig

def make_dummy_reading(frame_idx: int, timestamp: float, track_id: int, plate: str) -> CandidateReading:
    dummy_crop = np.zeros((30, 90, 3), dtype=np.uint8)
    return CandidateReading(
        frame_idx=frame_idx,
        timestamp=timestamp,
        track_id=track_id,
        raw_text=plate,
        normalized_text=plate,
        is_valid_format=True,
        format_type="standard",
        ocr_confidence=0.92,
        detection_confidence=0.88,
        blur_score=120.0,
        crop_image=dummy_crop,
        vehicle_bbox=(100, 200, 300, 400),
        plate_bbox=(150, 320, 250, 360)
    )

def test_track_merging_same_vehicle():
    merger = TrackMerger(IdentityMergerConfig(max_time_gap_seconds=3.0, merge_threshold=0.60))
    
    # Create red car appearance
    red_car = np.zeros((100, 100, 3), dtype=np.uint8)
    red_car[:, :] = (0, 0, 200) # BGR red

    # Track 1 appears from frame 1 to 20 moving down-right
    v1_id = None
    for f in range(1, 21):
        x1 = 100 + f * 5
        y1 = 100 + f * 5
        t = f / 30.0
        reading = make_dummy_reading(f, t, 1, "MH12DE1433") if f % 5 == 0 else None
        v1_id = merger.register_or_update_track(
            track_id=1,
            frame_idx=f,
            timestamp=t,
            veh_bbox=(x1, y1, x1 + 80, y1 + 80),
            veh_crop=red_car,
            candidate_reading=reading
        )

    assert v1_id is not None
    # Now simulate Track 1 disappearing (occlusion) at frame 20
    merger.mark_tracks_lost(active_track_ids=[], current_timestamp=20 / 30.0)
    assert v1_id in merger.lost_vehicles

    # Track 2 appears at frame 26 (t = 26/30.0), close to expected location, same red car, same plate
    f = 26
    x2 = 100 + f * 5 + 2 # slight offset
    y2 = 100 + f * 5 + 2
    t2 = f / 30.0
    reading2 = make_dummy_reading(f, t2, 2, "MH12DE1433")
    
    v2_id = merger.register_or_update_track(
        track_id=2,
        frame_idx=f,
        timestamp=t2,
        veh_bbox=(x2, y2, x2 + 80, y2 + 80),
        veh_crop=red_car,
        candidate_reading=reading2
    )

    # They should be merged into the same vehicle ID!
    assert v2_id == v1_id
    vehicle_rec = merger.vehicles[v1_id]
    assert 1 in vehicle_rec.linked_track_ids
    assert 2 in vehicle_rec.linked_track_ids
    assert len(vehicle_rec.linked_track_ids) == 2

def test_distinct_vehicles_not_merged():
    merger = TrackMerger(IdentityMergerConfig())

    red_car = np.zeros((100, 100, 3), dtype=np.uint8)
    red_car[:, :] = (0, 0, 200) # Red

    blue_car = np.zeros((100, 100, 3), dtype=np.uint8)
    blue_car[:, :] = (200, 0, 0) # Blue

    # Vehicle 1 at top-left
    v1_id = merger.register_or_update_track(
        track_id=10,
        frame_idx=1,
        timestamp=0.1,
        veh_bbox=(50, 50, 150, 150),
        veh_crop=red_car,
        candidate_reading=make_dummy_reading(1, 0.1, 10, "MH12DE1433")
    )

    # Vehicle 2 at bottom-right, different appearance, different plate
    v2_id = merger.register_or_update_track(
        track_id=20,
        frame_idx=2,
        timestamp=0.2,
        veh_bbox=(800, 800, 900, 900),
        veh_crop=blue_car,
        candidate_reading=make_dummy_reading(2, 0.2, 20, "DL01AB9999")
    )

    assert v1_id != v2_id
    assert len(merger.vehicles) == 2
