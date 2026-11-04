"""
Unit tests for Temporal Voting, Promotion, and Deduplication Engine
"""
import numpy as np
from src.identity.temporal_voting import TemporalVotingEngine
from src.identity.vehicle_identity import VehicleRecord, CandidateReading
from config import TemporalVotingConfig

def make_reading(plate: str, conf: float, frame_idx: int, track_id: int = 1, is_valid: bool = True) -> CandidateReading:
    dummy_crop = np.zeros((30, 90, 3), dtype=np.uint8)
    return CandidateReading(
        frame_idx=frame_idx,
        timestamp=frame_idx / 30.0,
        track_id=track_id,
        raw_text=plate,
        normalized_text=plate,
        is_valid_format=is_valid,
        format_type="standard" if is_valid else "invalid",
        ocr_confidence=conf,
        detection_confidence=0.90,
        blur_score=100.0,
        crop_image=dummy_crop,
        vehicle_bbox=(100, 100, 300, 300),
        plate_bbox=(150, 250, 250, 280)
    )

def test_consensus_voting_resolves_noise():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=3))
    vehicle = VehicleRecord(vehicle_id=1, linked_track_ids={1})

    # 4 readings of "MH12DE1433" and 1 noisy reading of "MH12DE1438"
    vehicle.add_reading(make_reading("MH12DE1433", 0.90, 1))
    vehicle.add_reading(make_reading("MH12DE1433", 0.92, 2))
    vehicle.add_reading(make_reading("MH12DE1438", 0.70, 3)) # noisy glitch
    vehicle.add_reading(make_reading("MH12DE1433", 0.95, 4))
    vehicle.add_reading(make_reading("MH12DE1433", 0.88, 5))

    voted = engine.vote_on_vehicle(vehicle)
    assert voted.is_verified is True
    assert voted.status == "VERIFIED"
    assert voted.final_plate == "MH12DE1433"
    assert voted.display_plate == "MH 12 DE 1433"
    assert voted.final_confidence >= 0.85

def test_single_frame_routes_to_needs_review():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=3))
    vehicle = VehicleRecord(vehicle_id=2, linked_track_ids={2})

    # Only 1 reading
    vehicle.add_reading(make_reading("KA05M9876", 0.95, 1))

    voted = engine.vote_on_vehicle(vehicle)
    assert voted.is_verified is False
    assert voted.status == "NEEDS_REVIEW"
    assert "insufficient frames" in voted.review_reason.lower()

def test_conflicting_readings_route_to_needs_review():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=2))
    vehicle = VehicleRecord(vehicle_id=3, linked_track_ids={3})

    # Conflicting readings with high confidence
    vehicle.add_reading(make_reading("MH12DE1433", 0.92, 1))
    vehicle.add_reading(make_reading("MH12DE1433", 0.90, 2))
    vehicle.add_reading(make_reading("DL01AB1234", 0.91, 3))
    vehicle.add_reading(make_reading("DL01AB1234", 0.93, 4))

    voted = engine.vote_on_vehicle(vehicle)
    assert voted.is_verified is False
    assert voted.status == "NEEDS_REVIEW"
    assert "conflicting" in voted.review_reason.lower()

def test_deduplication_of_verified_results():
    engine = TemporalVotingEngine()
    
    # Vehicle 1 verified with MH12DE1433 on track 1
    v1 = VehicleRecord(vehicle_id=1, linked_track_ids={1}, first_frame=10, last_frame=50)
    for f in range(10, 15):
        v1.add_reading(make_reading("MH12DE1433", 0.90, f, track_id=1))
    v1 = engine.vote_on_vehicle(v1)

    # Vehicle 2 verified with MH12DE1433 on track 7 (e.g. re-entry or separate track)
    v2 = VehicleRecord(vehicle_id=2, linked_track_ids={7}, first_frame=80, last_frame=120)
    for f in range(80, 85):
        v2.add_reading(make_reading("MH12DE1433", 0.95, f, track_id=7))
    v2 = engine.vote_on_vehicle(v2)

    assert v1.is_verified and v2.is_verified

    # Deduplicate
    deduped = engine.deduplicate_verified_results([v1, v2])
    
    # Must produce strictly 1 verified vehicle
    assert len(deduped) == 1
    unified = deduped[0]
    assert unified.final_plate == "MH12DE1433"
    # Must link both track IDs
    assert 1 in unified.linked_track_ids
    assert 7 in unified.linked_track_ids
    # Must span complete frame range
    assert unified.first_frame == 10
    assert unified.last_frame == 120

def test_ten_digit_priority_over_nine_and_eleven():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=2))
    vehicle = VehicleRecord(vehicle_id=5, linked_track_ids={5})

    # Simulating a 10-char plate HR06BJ5553 where:
    # - 1 frame had OCR dropped 'J' -> HR06B5553 (9 chars) with high confidence 0.90
    # - 2 frames read correct HR06BJ5553 (10 chars) with lower confidence 0.70
    # - 1 frame had screw hallucination -> HR06BJC5553 (11 chars) with confidence 0.85
    vehicle.add_reading(make_reading("HR06B5553", 0.90, 1, is_valid=True))
    vehicle.add_reading(make_reading("HR06BJ5553", 0.70, 2, is_valid=True))
    vehicle.add_reading(make_reading("HR06BJ5553", 0.72, 3, is_valid=True))
    vehicle.add_reading(make_reading("HR06BJC5553", 0.85, 4, is_valid=True))

    voted = engine.vote_on_vehicle(vehicle)
    # The 10-character candidate HR06BJ5553 must win despite the high individual confidences of 9 and 11 candidates!
    assert voted.final_plate == "HR06BJ5553"
    assert voted.display_plate == "HR 06 BJ 5553"

def test_multiple_ten_digit_candidates_highest_confidence_wins():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=1))
    vehicle = VehicleRecord(vehicle_id=6, linked_track_ids={6})

    # Competing with 9-char and 11-char, but two different 10-char candidates:
    vehicle.add_reading(make_reading("HR06B5553", 0.92, 1, is_valid=True))    # 9-char
    vehicle.add_reading(make_reading("HR06DJ5553", 0.65, 2, is_valid=True))   # 10-char lower conf
    vehicle.add_reading(make_reading("HR06BJ5553", 0.95, 3, is_valid=True))   # 10-char higher conf
    vehicle.add_reading(make_reading("HR06BJ55531", 0.88, 4, is_valid=True))  # 11-char

    voted = engine.vote_on_vehicle(vehicle)
    assert voted.final_plate == "HR06BJ5553"
    assert voted.display_plate == "HR 06 BJ 5553"

def test_unreadable_tier_with_evidence_preservation():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=2))
    vehicle = VehicleRecord(vehicle_id=7, linked_track_ids={7})

    dummy_crop = np.full((30, 90, 3), 128, dtype=np.uint8)
    reading1 = CandidateReading(
        frame_idx=10,
        timestamp=0.33,
        track_id=7,
        raw_text="UNREADABLE",
        normalized_text="UNREADABLE",
        is_valid_format=False,
        format_type="UNREADABLE",
        ocr_confidence=0.0,
        detection_confidence=0.82,
        blur_score=25.0,
        crop_image=dummy_crop,
        vehicle_bbox=(100, 100, 300, 300),
        plate_bbox=(150, 250, 250, 280)
    )
    reading2 = CandidateReading(
        frame_idx=15,
        timestamp=0.50,
        track_id=7,
        raw_text="UNREADABLE",
        normalized_text="UNREADABLE",
        is_valid_format=False,
        format_type="UNREADABLE",
        ocr_confidence=0.0,
        detection_confidence=0.85,
        blur_score=35.0,
        crop_image=dummy_crop,
        vehicle_bbox=(105, 102, 305, 302),
        plate_bbox=(152, 252, 252, 282)
    )
    vehicle.add_reading(reading1)
    vehicle.add_reading(reading2)

    assert vehicle.best_crop is not None
    assert len(vehicle.evidence_frames) >= 1

    voted = engine.vote_on_vehicle(vehicle)
    assert voted.status == "UNREADABLE"
    assert voted.final_plate == "UNREADABLE"
    assert voted.display_plate == "UNREADABLE (LOW EVIDENCE)"
    assert voted.is_verified is False
    assert voted.best_crop is not None
    assert len(voted.evidence_frames) >= 1

def test_medium_confidence_routes_to_needs_review_not_rejected():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=2, min_promotion_confidence=0.75))
    vehicle = VehicleRecord(vehicle_id=8, linked_track_ids={8})

    # Confidence between 40% and 60%
    vehicle.add_reading(make_reading("DL01AB1234", 0.52, 1))
    vehicle.add_reading(make_reading("DL01AB1234", 0.54, 2))

    voted = engine.vote_on_vehicle(vehicle)
    assert voted.status == "NEEDS_REVIEW"
    assert voted.is_verified is False
    assert voted.final_plate == "DL01AB1234"
    assert "low confidence" in voted.review_reason.lower()

def test_weak_noise_under_50_percent_strictly_rejected():
    engine = TemporalVotingEngine(TemporalVotingConfig(min_supporting_frames=2))
    vehicle = VehicleRecord(vehicle_id=9, linked_track_ids={9})

    # Weak detection <= 50% confidence (noise)
    vehicle.add_reading(CandidateReading(
        frame_idx=10,
        timestamp=0.33,
        track_id=9,
        raw_text="UNREADABLE",
        normalized_text="UNREADABLE",
        is_valid_format=False,
        format_type="UNREADABLE",
        ocr_confidence=0.0,
        detection_confidence=0.45,
        blur_score=15.0,
        crop_image=np.zeros((30, 90, 3), dtype=np.uint8),
        vehicle_bbox=(100, 100, 300, 300),
        plate_bbox=(150, 250, 250, 280)
    ))
    voted = engine.vote_on_vehicle(vehicle)
    assert voted.status == "REJECTED"


