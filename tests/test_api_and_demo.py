"""
Test API endpoints and demo video generation
"""
import os
import cv2
from fastapi.testclient import TestClient
from app import app, create_sample_demo_video, serialize_vehicle
from src.identity.vehicle_identity import VehicleRecord

def test_demo_video_creation():
    demo_path = "outputs/test_demo.mp4"
    create_sample_demo_video(demo_path)
    assert os.path.exists(demo_path)
    cap = cv2.VideoCapture(demo_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert frame_count > 50
    if os.path.exists(demo_path):
        os.remove(demo_path)

def test_api_status_endpoint():
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_processing" in data
    assert "progress" in data

def test_api_results_endpoint():
    client = TestClient(app)
    response = client.get("/api/results")
    assert response.status_code == 200

def test_html_dashboard_endpoint():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
def test_api_review_confirm_captured_db():
    from app import captured_db, vehicle_db
    client = TestClient(app)
    test_plate = "HR26CL9999"
    
    # Confirm through the review endpoint
    response = client.post("/api/review/confirm", data={
        "plate_number": test_plate,
        "original_plate": "HR26CL999",
        "confidence": 92.0,
        "location": "Manual Review Test Gate"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["confirmed_plate"] == test_plate
    assert data["captured_logged"] is True

    # Verify it is in Captured DB
    recent_captures = captured_db.get_recent(limit=10, search=test_plate)
    assert any(c["plate_number"] == test_plate for c in recent_captures)

    # Verify it was NOT inserted into Watchlist (vehicle_db)
    assert vehicle_db.match_plate(test_plate) is None

def test_download_endpoints():
    client = TestClient(app)
    # Test 404 for nonexistent files
    resp_v = client.get("/api/download/annotated-video/nonexistent_12345.mp4")
    assert resp_v.status_code == 404
    resp_p = client.get("/api/download/annotated-photo/nonexistent_12345.jpg")
    assert resp_p.status_code == 404

    # Test 200 with dummy photo in outputs
    dummy_photo_path = os.path.join("outputs", "test_download_photo.jpg")
    with open(dummy_photo_path, "wb") as f:
        f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00")
    try:
        resp_p2 = client.get("/api/download/annotated-photo/test_download_photo.jpg")
        assert resp_p2.status_code == 200
        assert "attachment" in resp_p2.headers.get("content-disposition", "")
    finally:
        if os.path.exists(dummy_photo_path):
            os.remove(dummy_photo_path)

if __name__ == "__main__":
    test_demo_video_creation()
    test_api_status_endpoint()
    test_api_results_endpoint()
    test_html_dashboard_endpoint()
    test_api_review_confirm_captured_db()
    test_download_endpoints()
    print("All API and demo tests passed successfully!")
