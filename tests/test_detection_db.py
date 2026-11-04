"""
Unit tests for DetectionDB (FIFO 100 ring buffer and crop cleanup)
"""
import os
import sys
import tempfile
import numpy as np
import cv2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.detection_db import DetectionDB
from fastapi.testclient import TestClient
from app import app

def test_fifo_ring_buffer_and_crop_pruning():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_detections.sqlite")
        # Test ring buffer with limit of 10 for speed
        det_db = DetectionDB(db_path=db_path, max_records=10)

        # Create dummy plate and vehicle crops
        plate_crop = np.zeros((30, 100, 3), dtype=np.uint8)
        plate_crop[:] = (255, 255, 255)
        vehicle_crop = np.zeros((100, 150, 3), dtype=np.uint8)
        vehicle_crop[:] = (120, 120, 120)

        saved_records = []
        # Insert 15 detections (exceeding limit of 10)
        for i in range(1, 16):
            rec_id = det_db.add_detection(
                plate_number=f"DL01AB{i:04d}",
                display_plate=f"DL 01 AB {i:04d}",
                confidence=85.0 + (i % 10),
                plate_img=plate_crop,
                vehicle_img=vehicle_crop,
                location="North Toll Booth",
                source_type="live_feed",
                is_hotlist_hit=(i % 5 == 0),
                hotlist_info="WANTED STOLEN" if (i % 5 == 0) else None
            )
            saved_records.append((rec_id, f"DL01AB{i:04d}"))

        # Verify strict limit of 10 entries maintained
        total = det_db.get_total_count()
        assert total == 10, f"Expected 10 records, got {total}"

        recent = det_db.get_recent(limit=20)
        assert len(recent) == 10

        # Verify newest record (#15) is at index 0 (top)
        assert recent[0]["plate_number"] == "DL01AB0015"
        # Verify oldest retained record is #6
        assert recent[-1]["plate_number"] == "DL01AB0006"

        # Verify oldest 5 records (#1 to #5) were pruned
        purged_plates = [r["plate_number"] for r in recent]
        for old_i in range(1, 6):
            old_plate = f"DL01AB{old_i:04d}"
            assert old_plate not in purged_plates, f"Purged plate {old_plate} still found in DB"

        # Verify crops directory files count matches remaining records
        crops_dir = det_db.crops_dir
        crop_files = os.listdir(crops_dir)
        # Each record creates 2 files: plate and vehicle -> 10 records * 2 = 20 files
        assert len(crop_files) == 20, f"Expected 20 image files on disk, got {len(crop_files)}"

        # Test single delete cleans up disk files
        first_id = recent[0]["id"]
        assert det_db.delete(first_id) is True
        assert det_db.get_total_count() == 9
        crop_files_after = os.listdir(crops_dir)
        assert len(crop_files_after) == 18

        # Test clear all
        det_db.clear_all()
        assert det_db.get_total_count() == 0
        assert len(os.listdir(crops_dir)) == 0

        print("test_fifo_ring_buffer_and_crop_pruning passed successfully!")

def test_detection_api_endpoints():
    import app as app_module
    from src.database.captured_db import CapturedDB

    orig_cap = app_module.captured_db
    orig_det = app_module.detection_db

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_cap_path = os.path.join(tmp_dir, "test_captured.sqlite")
        tmp_det_path = os.path.join(tmp_dir, "test_det.sqlite")
        test_captured_db = CapturedDB(db_path=tmp_cap_path)
        test_detection_db = DetectionDB(db_path=tmp_det_path)

        app_module.captured_db = test_captured_db
        app_module.detection_db = test_detection_db

        try:
            client = TestClient(app)

            # 1. Clear test detections
            client.delete("/api/detections")

            # 2. Add an image upload to trigger detection logging
            img = np.zeros((400, 600, 3), dtype=np.uint8)
            img[:] = (60, 60, 60)
            cv2.rectangle(img, (150, 100), (450, 320), (200, 200, 200), -1)
            cv2.rectangle(img, (220, 240), (380, 290), (255, 255, 255), -1)
            cv2.putText(img, "MH12DE1433", (230, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
            import io
            real_sample = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "vehicle_photos", "HR67F9260_1790071731.jpeg"))
            if os.path.exists(real_sample):
                with open(real_sample, "rb") as vf:
                    upload_bytes = vf.read()
            else:
                _, enc = cv2.imencode(".jpg", img)
                upload_bytes = enc.tobytes()

            res_upload = client.post(
                "/api/upload_image",
                files={"file": ("test_detection.jpg", io.BytesIO(upload_bytes), "image/jpeg")}
            )
            assert res_upload.status_code == 200

            # Ensure detection exists in test_detection_db and test_captured_db for API route testing
            if test_detection_db.get_total_count() == 0:
                plate_crop = np.zeros((30, 100, 3), dtype=np.uint8)
                vehicle_crop = np.zeros((100, 150, 3), dtype=np.uint8)
                test_detection_db.add_detection(
                    plate_number="MH12DE1433",
                    display_plate="MH 12 DE 1433",
                    confidence=95.0,
                    plate_img=plate_crop,
                    vehicle_img=vehicle_crop,
                    location="North Toll Booth",
                    source_type="image_upload"
                )
            if test_captured_db.get_total_count() == 0:
                plate_crop = np.zeros((30, 100, 3), dtype=np.uint8)
                vehicle_crop = np.zeros((100, 150, 3), dtype=np.uint8)
                test_captured_db.add_capture(
                    plate_number="MH12DE1433",
                    display_plate="MH 12 DE 1433",
                    confidence=95.0,
                    plate_img=plate_crop,
                    vehicle_img=vehicle_crop,
                    location="North Toll Booth",
                    source_type="image_upload"
                )

            # 3. GET /api/detections
            res_list = client.get("/api/detections")
            assert res_list.status_code == 200
            data = res_list.json()
            assert data["status"] == "success"
            assert data["total_count"] >= 1
            detections = data["detections"]
            assert len(detections) >= 1

            first = detections[0]
            assert "plate_number" in first
            assert "captured_at" in first
            assert "location" in first
            det_id = first["id"]

            # 4. GET /api/detections/{id}
            res_single = client.get(f"/api/detections/{det_id}")
            assert res_single.status_code == 200
            assert res_single.json()["detection"]["id"] == det_id

            # 5. DELETE /api/detections/{id}
            res_del = client.delete(f"/api/detections/{det_id}")
            assert res_del.status_code == 200
            assert res_del.json()["deleted_id"] == det_id

            print("test_detection_api_endpoints passed successfully!")
        finally:
            app_module.captured_db = orig_cap
            app_module.detection_db = orig_det

if __name__ == "__main__":
    test_fifo_ring_buffer_and_crop_pruning()
    test_detection_api_endpoints()
