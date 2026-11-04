"""
End-to-end verification test for Unified Multi-Modal ANPR + FRS Surveillance System
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2
import numpy as np
from fastapi.testclient import TestClient
import app

client = TestClient(app.app)

def test_live_feed():
    print("\n--- 1. Testing GET /api/unified/live-feed ---")
    resp = client.get("/api/unified/live-feed?limit=15")
    assert resp.status_code == 200, f"Failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert "fresh_vehicles" in data
    assert "fresh_faces" in data
    assert "kpi" in data
    assert len(data["fresh_vehicles"]) <= 15
    assert len(data["fresh_faces"]) <= 15
    print("KPIs:", data["kpi"])
    print(f"Fresh Vehicles: {len(data['fresh_vehicles'])}, Fresh Faces: {len(data['fresh_faces'])}")
    print("Live Feed Test PASSED!")

def test_audit_endpoints():
    print("\n--- 2. Testing GET /api/unified/audit-vehicles & audit-faces ---")
    resp_v = client.get("/api/unified/audit-vehicles?limit=100")
    assert resp_v.status_code == 200
    data_v = resp_v.json()
    assert data_v["success"] is True
    assert "vehicles" in data_v
    print(f"Audit Vehicles Count: {data_v['total_count']}, Retrieved: {len(data_v['vehicles'])}")

    resp_f = client.get("/api/unified/audit-faces?limit=100")
    assert resp_f.status_code == 200
    data_f = resp_f.json()
    assert data_f["success"] is True
    assert "faces" in data_f
    print(f"Audit Faces Count: {data_f['total_count']}, Retrieved: {len(data_f['faces'])}")
    print("Audit Endpoints Test PASSED!")

def test_unified_upload():
    print("\n--- 3. Testing POST /api/unified/upload with real media ---")
    # Create composite test image containing both a vehicle crop and a face crop
    face_path = "data/frs/enrolled/deepak_1790049991.jpg"
    veh_path = "data/vehicle_photos/HR67F9260_1790071731.jpeg"

    # Synthetic canvas
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    canvas[:] = (30, 30, 30)

    if os.path.exists(veh_path):
        veh_img = cv2.imread(veh_path)
        if veh_img is not None:
            vh, vw = veh_img.shape[:2]
            scale = min(500 / vw, 400 / vh)
            resized_veh = cv2.resize(veh_img, (int(vw * scale), int(vh * scale)))
            h_v, w_v = resized_veh.shape[:2]
            canvas[100:100+h_v, 100:100+w_v] = resized_veh
            print(f"Embedded vehicle crop into canvas ({w_v}x{h_v})")

    if os.path.exists(face_path):
        face_img = cv2.imread(face_path)
        if face_img is not None:
            fh, fw = face_img.shape[:2]
            scale = min(300 / fw, 300 / fh)
            resized_face = cv2.resize(face_img, (int(fw * scale), int(fh * scale)))
            h_f, w_f = resized_face.shape[:2]
            canvas[150:150+h_f, 750:750+w_f] = resized_face
            print(f"Embedded face crop into canvas ({w_f}x{h_f})")

    _, encoded = cv2.imencode(".jpg", canvas)
    test_bytes = encoded.tobytes()

    resp = client.post(
        "/api/unified/upload",
        files={"file": ("test_composite.jpg", test_bytes, "image/jpeg")}
    )
    assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert "vehicles" in data
    assert "faces" in data
    assert "correlation" in data
    assert "annotated_image_base64" in data
    assert len(data["annotated_image_base64"]) > 0

    print("Stats from upload:", data["stats"])
    print(f"Correlation summary: {data['correlation'].get('summary')}")
    print("Unified Upload Test PASSED!")

def test_hud_layers():
    print("\n--- 4. Testing POST & GET /api/camera/layers ---")
    payload = {
        "vehicle_box": True,
        "bytetrack": True,
        "plate_box": True,
        "ocr_text": True,
        "person_box": True,
        "face_box": True,
        "landmarks": True,
        "people_counter": True
    }
    resp = client.post("/api/camera/layers", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    layers = data["overlay_layers"]
    assert layers["person_box"] is True
    assert layers["face_box"] is True
    assert layers["landmarks"] is True
    assert layers["people_counter"] is True
    print("HUD layers returned:", layers)
    print("HUD Layers Test PASSED!")

if __name__ == "__main__":
    test_live_feed()
    test_audit_endpoints()
    test_hud_layers()
    test_unified_upload()
    print("\n==========================================")
    print("ALL UNIFIED SURVEILLANCE TESTS PASSED 100%!")
    print("==========================================")
