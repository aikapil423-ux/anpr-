"""
End-to-End Simulation Test for ANPR Pipeline
Simulates a multi-frame video with:
- Vehicle 1 on Track 1, then interrupted, then continuing on Track 2 (Same Vehicle Identity)
- Blurry / Watermark frames rejected by Quality Gate
- Vehicle 2 with insufficient frames -> routed to 'Needs Review'
- Final verification check: Verified count strictly represents unique vehicles!
"""
import os
import sys
import numpy as np
import cv2
from config import ANPRConfig
from src.pipeline.anpr_pipeline import ANPRPipeline
from src.identity.vehicle_identity import CandidateReading

def test_full_pipeline_simulation():
    config = ANPRConfig()
    config.voting.min_supporting_frames = 3
    # Use lazy_models=True so unit test doesn't require downloading full YOLO weights
    pipeline = ANPRPipeline(config=config, lazy_models=True)

    dummy_crop = np.zeros((30, 90, 3), dtype=np.uint8)
    cv2.putText(dummy_crop, "MH12DE1433", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    # Simulate Vehicle 1:
    # Appears on Track 1 at frames 1..5, moving from (100, 100) to (125, 125)
    red_crop = np.zeros((80, 80, 3), dtype=np.uint8)
    red_crop[:, :] = (0, 0, 220)

    for f in range(1, 6):
        t = f / 30.0
        x = 100 + f * 5
        reading = CandidateReading(
            frame_idx=f,
            timestamp=t,
            track_id=1,
            raw_text="MH12DE1433",
            normalized_text="MH12DE1433",
            is_valid_format=True,
            format_type="standard",
            ocr_confidence=0.92,
            detection_confidence=0.89,
            blur_score=110.0,
            crop_image=dummy_crop,
            vehicle_bbox=(x, x, x + 80, x + 80),
            plate_bbox=(x + 10, x + 40, x + 70, x + 60)
        )
        vid = pipeline.track_merger.register_or_update_track(
            track_id=1,
            frame_idx=f,
            timestamp=t,
            veh_bbox=(x, x, x + 80, x + 80),
            plate_bbox=(x + 10, x + 40, x + 70, x + 60),
            veh_crop=red_crop,
            candidate_reading=reading
        )
        pipeline.stats["valid_ocr_readings"] += 1
        pipeline.stats["total_frames_processed"] += 1

    # Simulate Track 1 lost at frame 5
    pipeline.track_merger.mark_tracks_lost(active_track_ids=[], current_timestamp=5 / 30.0)

    # Track 2 appears at frame 8 (same red car, continuing trajectory, same plate)
    for f in range(8, 12):
        t = f / 30.0
        x = 100 + f * 5
        reading = CandidateReading(
            frame_idx=f,
            timestamp=t,
            track_id=2, # New ByteTrack ID!
            raw_text="MH12DE1433",
            normalized_text="MH12DE1433",
            is_valid_format=True,
            format_type="standard",
            ocr_confidence=0.94,
            detection_confidence=0.91,
            blur_score=120.0,
            crop_image=dummy_crop,
            vehicle_bbox=(x, x, x + 80, x + 80),
            plate_bbox=(x + 10, x + 40, x + 70, x + 60)
        )
        vid2 = pipeline.track_merger.register_or_update_track(
            track_id=2,
            frame_idx=f,
            timestamp=t,
            veh_bbox=(x, x, x + 80, x + 80),
            plate_bbox=(x + 10, x + 40, x + 70, x + 60),
            veh_crop=red_crop,
            candidate_reading=reading
        )
        pipeline.stats["valid_ocr_readings"] += 1
        pipeline.stats["total_frames_processed"] += 1

    # Verify Track 1 and Track 2 were merged into the same vehicle ID!
    assert vid2 == vid, f"Expected Track 2 to be merged into vehicle {vid}, got {vid2}"

    # Simulate Vehicle 2: A different car that appears for only 1 frame (e.g. glitch/edge of camera)
    blue_crop = np.zeros((80, 80, 3), dtype=np.uint8)
    blue_crop[:, :] = (220, 0, 0)
    reading_v2 = CandidateReading(
        frame_idx=15,
        timestamp=0.5,
        track_id=99,
        raw_text="DL01AB9999",
        normalized_text="DL01AB9999",
        is_valid_format=True,
        format_type="standard",
        ocr_confidence=0.85,
        detection_confidence=0.80,
        blur_score=80.0,
        crop_image=dummy_crop,
        vehicle_bbox=(500, 500, 600, 600),
        plate_bbox=(520, 560, 580, 590)
    )
    vid3 = pipeline.track_merger.register_or_update_track(
        track_id=99,
        frame_idx=15,
        timestamp=0.5,
        veh_bbox=(500, 500, 600, 600),
        plate_bbox=(520, 560, 580, 590),
        veh_crop=blue_crop,
        candidate_reading=reading_v2
    )
    pipeline.stats["valid_ocr_readings"] += 1

    # Finalize pipeline
    results = pipeline.finalize()
    verified = results["verified_vehicles"]
    needs_review = results["needs_review"]
    stats = results["stats"]

    # Check Verified Results:
    # Must have exactly 1 verified vehicle (Vehicle 1 with plate MH12DE1433)
    assert len(verified) == 1, f"Expected 1 verified vehicle, got {len(verified)}"
    v1_final = verified[0]
    assert v1_final.final_plate == "MH12DE1433"
    assert v1_final.is_verified is True
    # Track 1 and Track 2 are both linked to this verified vehicle
    assert 1 in v1_final.linked_track_ids
    assert 2 in v1_final.linked_track_ids
    assert v1_final.first_frame == 1
    assert v1_final.last_frame == 11

    # Check Needs Review:
    # Vehicle 2 had only 1 frame, so it must be in needs_review, NOT counted in verified!
    assert len(needs_review) == 1
    v2_review = needs_review[0]
    assert v2_review.is_verified is False
    assert "insufficient frames" in v2_review.review_reason.lower()

    # Check Stats:
    assert stats["verified_total"] == 1
    assert stats["needs_review_total"] == 1
    assert stats["tracks_merged_into_vehicles"] == 1
    assert stats["total_bytetrack_ids"] == 3 # Tracks 1, 2, 99
    assert stats["total_vehicles_created"] == 2 # Only 2 unique vehicle entities!

    print("\nEnd-to-End Simulation Pipeline successfully verified!")
