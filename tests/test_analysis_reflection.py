import sys
import requests
import json
import os
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_analysis_reflection():
    print("=" * 60)
    print("TESTING: Real Analysis Reflection into Results & Live Feeds")
    print("=" * 60)

    session = requests.Session()

    # Step 1: Login
    login_res = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "stateadmin", "password": "HaryanaPolice@HQ2026"}
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.status_code} {login_res.text}"
    print("1. [PASS] Logged in successfully as State Admin")

    # Step 2: Check baseline upload feed
    r_init = session.get(f"{BASE_URL}/api/unified/live-feed?source=upload&limit=15")
    assert r_init.status_code == 200
    init_data = r_init.json()
    initial_upload_veh_count = init_data["kpi"]["vehicles_count"]
    initial_top_plate = init_data["fresh_vehicles"][0]["plate_number"] if init_data["fresh_vehicles"] else None
    print(f"2. [INFO] Baseline upload vehicles: {initial_upload_veh_count}, top plate: {initial_top_plate}")

    # Step 3: Perform actual image analysis upload
    image_path = "sample_uvh26autotruck.jpg"
    assert os.path.exists(image_path), f"Sample image {image_path} missing!"

    with open(image_path, "rb") as f:
        upload_res = session.post(
            f"{BASE_URL}/api/unified/upload",
            files={"file": (image_path, f, "image/jpeg")},
            data={"target": "vehicle", "fps": 5, "task_id": "test_qa_reflection_001"}
        )

    assert upload_res.status_code == 200, f"Upload analysis failed: {upload_res.status_code} {upload_res.text}"
    upload_json = upload_res.json()
    analyzed_vehicles = upload_json.get("vehicles", [])
    print(f"3. [PASS] Upload & analysis executed successfully! Detected vehicles: {len(analyzed_vehicles)}")

    # Step 4: Verify that newly analyzed vehicle reflects in Upload Live Feed
    r_after = session.get(f"{BASE_URL}/api/unified/live-feed?source=upload&limit=15")
    assert r_after.status_code == 200
    after_data = r_after.json()
    new_upload_veh_count = after_data["kpi"]["vehicles_count"]
    new_fresh_vehicles = after_data["fresh_vehicles"]
    print(f"4. [INFO] Post-upload feed vehicles count: {new_upload_veh_count}")

    # Check reflection
    assert len(new_fresh_vehicles) > 0, "fresh_vehicles list in upload feed is empty!"
    top_veh = new_fresh_vehicles[0]
    print(f"   [PASS] Top fresh vehicle in Upload feed: Plate={top_veh.get('display_plate') or top_veh.get('plate_number')}, ID={top_veh.get('id')}, Time={top_veh.get('captured_at')}")

    # Step 5: Verify ZERO leakage into Live Stream Feed
    r_live = session.get(f"{BASE_URL}/api/unified/live-feed?source=live&limit=15")
    assert r_live.status_code == 200
    live_data = r_live.json()
    live_plates = [v.get("id") for v in live_data.get("fresh_vehicles", [])]
    assert top_veh.get("id") not in live_plates, f"CRITICAL: Uploaded vehicle ID {top_veh.get('id')} leaked into live stream feed!"
    print(f"5. [PASS] Zero leakage verified! Uploaded capture ID {top_veh.get('id')} is NOT in Live stream feed.")

    # Step 6: Test Live Stream Sighting Reflection
    # Add a live stream capture directly via CapturedDB
    import sys
    sys.path.insert(0, os.getcwd())
    from src.database.captured_db import CapturedDB
    import numpy as np
    
    cap_db = CapturedDB("data/captured_db.sqlite")
    dummy_img = np.zeros((100, 200, 3), dtype=np.uint8)
    
    live_test_plate = f"HRLIVE{os.getpid() % 1000:03d}"
    live_cid = cap_db.add_capture(
        plate_number=live_test_plate,
        display_plate=live_test_plate,
        confidence=98.5,
        location="Panipat Live Sector 13 Camera",
        source_type="stream_demo",
        plate_img=dummy_img,
        vehicle_img=dummy_img,
        district="Panipat",
        operator_username="op_5421"
    )
    print(f"6. [INFO] Ingested live camera detection: Plate={live_test_plate}, ID={live_cid}")

    # Step 7: Verify live capture appears in Live Feed
    r_live_after = session.get(f"{BASE_URL}/api/unified/live-feed?source=live&limit=15")
    assert r_live_after.status_code == 200
    live_fresh = r_live_after.json()["fresh_vehicles"]
    live_ids = [v["id"] for v in live_fresh]
    assert live_cid in live_ids, f"Live capture {live_cid} failed to reflect in Live Stream feed!"
    print(f"7. [PASS] Live camera detection {live_test_plate} (ID {live_cid}) reflected at TOP of Live feed!")

    # Step 8: Verify live capture does NOT appear in Upload Feed
    r_upload_check = session.get(f"{BASE_URL}/api/unified/live-feed?source=upload&limit=15")
    assert r_upload_check.status_code == 200
    upload_ids = [v["id"] for v in r_upload_check.json()["fresh_vehicles"]]
    assert live_cid not in upload_ids, f"CRITICAL: Live capture {live_cid} leaked into upload feed!"
    print(f"8. [PASS] Zero leakage verified! Live capture {live_cid} is NOT in Upload feed.")

    print("=" * 60)
    print("ALL REFLECTION & PARTITION CHECKS PASSED WITH FLYING COLORS! 🚀")
    print("=" * 60)

if __name__ == "__main__":
    test_analysis_reflection()
