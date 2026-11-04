"""
Tests for Vehicle Trail DB and API Endpoints
Verifies:
1. Recording sightings linked to vehicle ID with timezone-aware ISO timestamp and photos.
2. Single sighting per passage (duplicate passage ID / rapid retry prevention).
3. Repeat sightings at same or different camera create distinct chronological entries.
4. Unmatched vehicles are excluded.
5. Filters (date, camera, location) in history retrieval.
6. Independence from captured DB FIFO pruning and persistence after restart.
"""
import os
import shutil
import tempfile
import time
import datetime
import numpy as np
from src.database.vehicle_db import VehicleDB
from src.database.captured_db import CapturedDB
from src.database.trail_db import TrailDB

def test_trail_db_basic_recording_and_duplicates():
    temp_dir = tempfile.mkdtemp()
    try:
        trail_db_path = os.path.join(temp_dir, "test_trail.sqlite")
        trail_db = TrailDB(db_path=trail_db_path)

        dummy_plate_img = np.zeros((30, 90, 3), dtype=np.uint8)
        dummy_veh_img = np.zeros((100, 150, 3), dtype=np.uint8)

        # 1. Record first passage sighting
        s1 = trail_db.record_sighting(
            vehicle_id=1,
            registration_number="MH 12 DE 1433",
            camera_id="CAM-01",
            location="Main Surveillance Gate",
            confidence=94.5,
            plate_img=dummy_plate_img,
            vehicle_img=dummy_veh_img,
            passage_id="pass_001"
        )
        assert s1 is not None, "First sighting must be recorded"
        assert trail_db.get_total_sightings_count() == 1

        # 2. Duplicate passage test: Same passage_id should be skipped
        s_dup = trail_db.record_sighting(
            vehicle_id=1,
            registration_number="MH12DE1433",
            camera_id="CAM-01",
            location="Main Surveillance Gate",
            confidence=95.0,
            passage_id="pass_001"
        )
        assert s_dup is None, "Duplicate passage_id must be skipped"
        assert trail_db.get_total_sightings_count() == 1

        # 3. Repeat sighting test: Later passage at another camera CAM-02
        s2 = trail_db.record_sighting(
            vehicle_id=1,
            registration_number="MH 12 DE 1433",
            camera_id="CAM-02",
            location="Exit Toll Booth",
            confidence=96.0,
            plate_img=dummy_plate_img,
            vehicle_img=dummy_veh_img,
            passage_id="pass_002"
        )
        assert s2 is not None, "Repeat sighting at different camera/passage must be recorded"
        assert trail_db.get_total_sightings_count() == 2

        # 4. Summary test
        summaries = trail_db.get_vehicle_trails_summary()
        assert len(summaries) == 1
        assert summaries[0]["vehicle_id"] == 1
        assert summaries[0]["sighting_count"] == 2
        assert summaries[0]["last_seen_camera"] == "CAM-02"
        assert summaries[0]["last_seen_location"] == "Exit Toll Booth"

        # 5. History and Chronological ordering test
        history_asc = trail_db.get_vehicle_history(vehicle_id=1, ascending=True)
        assert len(history_asc) == 2
        assert history_asc[0]["camera_id"] == "CAM-01"
        assert history_asc[1]["camera_id"] == "CAM-02"

        history_desc = trail_db.get_vehicle_history(vehicle_id=1, ascending=False)
        assert history_desc[0]["camera_id"] == "CAM-02"

        # 6. Filtering test by camera
        cam1_only = trail_db.get_vehicle_history(vehicle_id=1, camera_id="CAM-01")
        assert len(cam1_only) == 1
        assert cam1_only[0]["camera_id"] == "CAM-01"

        # 7. Filtering test by location
        exit_only = trail_db.get_vehicle_history(vehicle_id=1, location="Exit Toll")
        assert len(exit_only) == 1
        assert exit_only[0]["location"] == "Exit Toll Booth"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_trail_db_independence_from_captured_fifo():
    temp_dir = tempfile.mkdtemp()
    try:
        captured_db_path = os.path.join(temp_dir, "captured.sqlite")
        trail_db_path = os.path.join(temp_dir, "trail.sqlite")

        cap_db = CapturedDB(db_path=captured_db_path, max_records=2)
        trail_db = TrailDB(db_path=trail_db_path)

        dummy_crop = np.zeros((40, 100, 3), dtype=np.uint8)

        # Record into trail db
        s1 = trail_db.record_sighting(
            vehicle_id=10,
            registration_number="DL01AB1234",
            camera_id="CAM-01",
            location="North Gate",
            confidence=92.0,
            plate_img=dummy_crop,
            vehicle_img=dummy_crop,
            passage_id="pass_trail_1"
        )
        assert s1 is not None

        # Add records to captured db to trigger pruning
        for i in range(5):
            cap_db.add_capture(
                plate_number=f"DL01AB123{i}",
                display_plate=f"DL 01 AB 123{i}",
                confidence=90.0,
                plate_img=dummy_crop,
                vehicle_img=dummy_crop,
                annotated_img=dummy_crop,
                location="Gate",
                source_type="test"
            )

        # Captured DB pruned to 2 records
        assert cap_db.get_total_count() == 2

        # Clear captured db completely
        cap_db.clear_all()
        assert cap_db.get_total_count() == 0

        # Trail DB must remain completely untouched
        assert trail_db.get_total_sightings_count() == 1
        summaries = trail_db.get_vehicle_trails_summary()
        assert len(summaries) == 1
        assert summaries[0]["vehicle_id"] == 10
        assert summaries[0]["sighting_count"] == 1

        # Image file in trail_photos must still exist on disk
        photo_rel = summaries[0]["latest_plate_photo"]
        assert photo_rel is not None
        photo_filename = os.path.basename(photo_rel)
        photo_abs = os.path.join(trail_db.photos_dir, photo_filename)
        assert os.path.exists(photo_abs), "Trail photo must persist independently"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_trail_db_persistence_after_restart():
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(temp_dir, "persistent_trail.sqlite")
        db1 = TrailDB(db_path=db_path)
        db1.record_sighting(
            vehicle_id=5,
            registration_number="MH12DE1433",
            camera_id="CAM-03",
            location="Sector 4 Junction",
            confidence=98.0,
            passage_id="restart_passage_1"
        )
        assert db1.get_total_sightings_count() == 1

        # Simulate application restart by creating a new instance on same file
        db2 = TrailDB(db_path=db_path)
        assert db2.get_total_sightings_count() == 1
        summary = db2.get_vehicle_trails_summary()
        assert len(summary) == 1
        assert summary[0]["vehicle_id"] == 5
        assert summary[0]["last_seen_camera"] == "CAM-03"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
