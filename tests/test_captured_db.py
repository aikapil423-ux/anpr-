"""
Unit tests for Captured DB (Strict 100 Recent Entries FIFO Ring Buffer & Crop Cleanup)
"""
import os
import sys
import tempfile
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.captured_db import CapturedDB
from fastapi.testclient import TestClient
from app import app, captured_db

def test_captured_db_fifo_ring_buffer():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_captured_fifo.sqlite")
        # Initialize CapturedDB with limit of 10 for test speed
        cdb = CapturedDB(db_path=db_path, max_records=10)

        # Create dummy plate and vehicle crops
        plate_crop = np.zeros((30, 100, 3), dtype=np.uint8)
        plate_crop[:] = (255, 255, 255)
        vehicle_crop = np.zeros((100, 150, 3), dtype=np.uint8)
        vehicle_crop[:] = (120, 120, 120)

        # Insert 15 captures sequentially
        for i in range(1, 16):
            rec_id = cdb.add_capture(
                plate_number=f"DL01AB{i:04d}",
                display_plate=f"DL 01 AB {i:04d}",
                confidence=85.0 + (i % 10),
                plate_img=plate_crop,
                vehicle_img=vehicle_crop,
                location="Main Surveillance Gate",
                source_type="live_feed",
                is_hotlist_hit=(i == 15),
                hotlist_info="WANTED IN HIT & RUN" if (i == 15) else None
            )

        # 1. Total records must strictly be 10 (FIFO limit)
        assert cdb.get_total_count() == 10

        recent = cdb.get_recent(limit=20)
        assert len(recent) == 10

        # 2. Most recent entry (#15) must be at index 0 (#1 position)
        assert recent[0]["plate_number"] == "DL01AB0015"
        assert recent[0]["is_hotlist_hit"] == 1
        assert recent[0]["hotlist_info"] == "WANTED IN HIT & RUN"

        # 3. Oldest retained record must be #6
        assert recent[-1]["plate_number"] == "DL01AB0006"

        # 4. Oldest 5 records (#1 through #5) must have been automatically purged
        retained_plates = [r["plate_number"] for r in recent]
        for old_num in range(1, 6):
            old_p = f"DL01AB{old_num:04d}"
            assert old_p not in retained_plates

        # 5. Disk images for pruned records must be deleted from disk
        crops_dir = cdb.crops_dir
        crop_files = os.listdir(crops_dir)
        # 10 records * 2 images = 20 images
        assert len(crop_files) == 20

        # 6. Delete a single entry and verify file removal
        first_id = recent[0]["id"]
        assert cdb.delete(first_id) is True
        assert cdb.get_total_count() == 9
        assert len(os.listdir(crops_dir)) == 18

        # 7. Clear all
        cdb.clear_all()
        assert cdb.get_total_count() == 0
        assert len(os.listdir(crops_dir)) == 0

        print("test_captured_db_fifo_ring_buffer passed successfully!")

def test_captured_db_api_endpoints():
    import app as app_module
    # Temporarily switch app_module.captured_db to an isolated test DB
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db_path = os.path.join(tmp_dir, "test_api_captured.sqlite")
        orig_db = app_module.captured_db
        test_cdb = CapturedDB(db_path=test_db_path)
        app_module.captured_db = test_cdb
        app_module.detection_db = test_cdb

        try:
            client = TestClient(app)

            # 1. Add direct entries to test_cdb
            p_crop = np.zeros((30, 100, 3), dtype=np.uint8)
            v_crop = np.zeros((100, 150, 3), dtype=np.uint8)
            rec1_id = test_cdb.add_capture(
                plate_number="MH12DE1433",
                display_plate="MH 12 DE 1433",
                confidence=95.5,
                plate_img=p_crop,
                vehicle_img=v_crop,
                location="Toll Plaza Lane 2",
                source_type="video_upload",
                is_hotlist_hit=True,
                hotlist_info="POLICE CASE: Hit & Run | FIR: FIR-2026/01"
            )

            rec2_id = test_cdb.add_capture(
                plate_number="DL01AB1234",
                display_plate="DL 01 AB 1234",
                confidence=88.0,
                plate_img=p_crop,
                vehicle_img=v_crop,
                location="South Gate Camera",
                source_type="live_feed",
                is_hotlist_hit=False
            )

            # 2. GET /api/captured
            res = client.get("/api/captured")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["total_count"] == 2
            captures = data["captured"]
            # Newest is rec2
            assert captures[0]["id"] == rec2_id
            assert captures[1]["id"] == rec1_id

            # 3. Search and Filter
            res_search = client.get("/api/captured?search=MH12DE")
            assert res_search.status_code == 200
            assert len(res_search.json()["captured"]) == 1

            res_hotlist = client.get("/api/captured?hotlist_only=true")
            assert res_hotlist.status_code == 200
            assert len(res_hotlist.json()["captured"]) == 1
            assert res_hotlist.json()["captured"][0]["id"] == rec1_id

            # 4. GET /api/captured/{id}
            res_single = client.get(f"/api/captured/{rec1_id}")
            assert res_single.status_code == 200
            assert res_single.json()["capture"]["plate_number"] == "MH12DE1433"

            # 5. DELETE /api/captured/{id}
            res_del = client.delete(f"/api/captured/{rec2_id}")
            assert res_del.status_code == 200

            # 6. Clean up in temp test db
            client.delete("/api/captured")
            assert test_cdb.get_total_count() == 0

            print("test_captured_db_api_endpoints passed successfully!")
        finally:
            app_module.captured_db = orig_db
            app_module.detection_db = orig_db

if __name__ == "__main__":
    test_captured_db_fifo_ring_buffer()
    test_captured_db_api_endpoints()
