"""
Test POST /api/upload_image endpoint
"""
import io
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import cv2
import numpy as np
from fastapi.testclient import TestClient
from app import app

def test_image_upload_endpoint():
    client = TestClient(app)

    # Create synthetic test car image with license plate
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    img[:] = (70, 70, 70)
    
    # Car box
    cv2.rectangle(img, (150, 100), (450, 320), (200, 200, 200), -1)
    # License plate box
    cv2.rectangle(img, (220, 240), (380, 290), (255, 255, 255), -1)
    cv2.rectangle(img, (220, 240), (380, 290), (0, 0, 0), 2)
    cv2.putText(img, "MH12DE1433", (230, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    _, encoded = cv2.imencode('.jpg', img)
    file_bytes = io.BytesIO(encoded.tobytes())

    response = client.post(
        "/api/upload_image",
        files={"file": ("test_plate.jpg", file_bytes, "image/jpeg")}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "annotated_image_base64" in data
    assert "detections" in data
    print("test_image_upload_endpoint passed!")

if __name__ == "__main__":
    test_image_upload_endpoint()
