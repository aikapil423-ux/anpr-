"""
Unit and Integration Tests for Camera & Live Stream Ingestion with AI ANPR Toggle
"""
import os
import shutil
import tempfile
import time
import numpy as np
import cv2

from src.camera.stream_manager import CameraStreamManager, MultiCameraStreamManager
from src.database.vehicle_db import VehicleDB
from src.database.captured_db import CapturedDB
from src.database.trail_db import TrailDB

def _create_dummy_video(path: str, num_frames: int = 30):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 30, (320, 240))
    for f in range(num_frames):
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(img, f"F:{f}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        out.write(img)
    out.release()

def test_camera_stream_manager_lifecycle():
    temp_dir = tempfile.mkdtemp()
    try:
        video_path = os.path.join(temp_dir, "test_feed.mp4")
        _create_dummy_video(video_path, num_frames=20)

        vdb = VehicleDB(db_path=os.path.join(temp_dir, "vdb.sqlite"))
        cdb = CapturedDB(db_path=os.path.join(temp_dir, "cdb.sqlite"))
        tdb = TrailDB(db_path=os.path.join(temp_dir, "tdb.sqlite"))

        manager = CameraStreamManager(vehicle_db=vdb, captured_db=cdb, trail_db=tdb)
        assert not manager.is_running

        # Start stream using the dummy video as source with GPS coordinates
        ok = manager.start_stream(
            source=video_path,
            source_type="test",
            camera_id="CAM-99",
            location="Test Gate",
            gps_coords="28.6139, 77.2090"
        )
        assert ok is True
        assert manager.is_running is True

        status = manager.get_status()
        assert status["is_running"] is True
        assert status["camera_id"] == "CAM-99"
        assert status["location"] == "Test Gate"
        assert status["gps_coords"] == "28.6139, 77.2090"
        assert status["anpr_enabled"] is True

        # Test toggle ANPR off
        manager.set_anpr_enabled(False)
        assert manager.anpr_enabled is False
        assert manager.get_status()["anpr_enabled"] is False

        # Test toggle ANPR back on
        manager.set_anpr_enabled(True)
        assert manager.anpr_enabled is True

        # Wait for background thread to read frames
        for _ in range(20):
            if manager.frame_count > 0:
                break
            time.sleep(0.05)
        assert manager.frame_count > 0

        # Test frame generator yields multipart JPEG frames
        gen = manager.generate_mjpeg_frames()
        first_frame = next(gen)
        assert b"--frame" in first_frame
        assert b"Content-Type: image/jpeg" in first_frame

        # Stop stream
        manager.stop_stream()
        assert manager.is_running is False
        assert manager.get_status()["is_running"] is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_multi_camera_grid_lifecycle():
    temp_dir = tempfile.mkdtemp()
    try:
        video_path1 = os.path.join(temp_dir, "feed1.mp4")
        video_path2 = os.path.join(temp_dir, "feed2.mp4")
        _create_dummy_video(video_path1, num_frames=20)
        _create_dummy_video(video_path2, num_frames=20)

        vdb = VehicleDB(db_path=os.path.join(temp_dir, "vdb.sqlite"))
        cdb = CapturedDB(db_path=os.path.join(temp_dir, "cdb.sqlite"))
        tdb = TrailDB(db_path=os.path.join(temp_dir, "tdb.sqlite"))

        multi_manager = MultiCameraStreamManager(vehicle_db=vdb, captured_db=cdb, trail_db=tdb)
        assert len(multi_manager.cameras) == 4
        assert "CAM-01" in multi_manager.cameras
        assert "CAM-02" in multi_manager.cameras
        assert "CAM-03" in multi_manager.cameras
        assert "CAM-04" in multi_manager.cameras

        # Initial status
        init_status = multi_manager.get_status()
        assert init_status["active_count"] == 0
        assert init_status["total_slots"] == 4

        # Start stream on CAM-01 and CAM-02 concurrently
        ok1 = multi_manager.start_stream(
            source=video_path1,
            source_type="test",
            camera_id="CAM-01",
            location="North Gate",
            gps_coords="28.6139, 77.2090"
        )
        ok2 = multi_manager.start_stream(
            source=video_path2,
            source_type="test",
            camera_id="CAM-02",
            location="South Toll",
            gps_coords="28.5355, 77.3910"
        )
        assert ok1 is True
        assert ok2 is True

        status = multi_manager.get_status()
        assert status["active_count"] == 2
        assert status["cameras"]["CAM-01"]["is_running"] is True
        assert status["cameras"]["CAM-02"]["is_running"] is True
        assert status["cameras"]["CAM-03"]["is_running"] is False
        assert status["cameras"]["CAM-01"]["location"] == "North Gate"
        assert status["cameras"]["CAM-02"]["location"] == "South Toll"

        # Test independent ANPR toggling
        multi_manager.set_anpr_enabled(True, camera_id="CAM-01")
        multi_manager.set_anpr_enabled(False, camera_id="CAM-02")
        assert multi_manager.get_status("CAM-01")["anpr_enabled"] is True
        assert multi_manager.get_status("CAM-02")["anpr_enabled"] is False

        # Wait for background ingestion
        for _ in range(20):
            if multi_manager.get_camera("CAM-01").frame_count > 0 and multi_manager.get_camera("CAM-02").frame_count > 0:
                break
            time.sleep(0.05)

        # Generate frames for both
        gen1 = multi_manager.generate_mjpeg_frames("CAM-01")
        gen2 = multi_manager.generate_mjpeg_frames("CAM-02")
        f1 = next(gen1)
        f2 = next(gen2)
        assert b"--frame" in f1
        assert b"--frame" in f2

        # Stop CAM-01, verify CAM-02 remains active
        multi_manager.stop_stream("CAM-01")
        assert multi_manager.get_status("CAM-01")["is_running"] is False
        assert multi_manager.get_status("CAM-02")["is_running"] is True
        assert multi_manager.get_status()["active_count"] == 1

        # Stop all
        multi_manager.stop_all()
        assert multi_manager.get_status()["active_count"] == 0
        assert multi_manager.get_status("CAM-02")["is_running"] is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

