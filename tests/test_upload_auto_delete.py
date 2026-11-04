import os
import shutil
import tempfile
import cv2
import numpy as np
from app import app, run_video_processing, captured_db, vehicle_db, OUTPUTS_DIR
from fastapi.testclient import TestClient

def test_uploaded_video_auto_deleted_after_analysis():
    # 1. Create a short synthetic test video
    temp_dir = tempfile.mkdtemp()
    test_video_path = os.path.join(OUTPUTS_DIR, "test_autodelete_vehicle.mp4")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(test_video_path, fourcc, 10.0, (320, 240))
    for f in range(15):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        # Vehicle box
        cv2.rectangle(frame, (50, 50), (250, 180), (180, 100, 40), -1)
        # Plate
        cv2.rectangle(frame, (100, 130), (200, 160), (255, 255, 255), -1)
        cv2.putText(frame, "DL01AB1234", (105, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2)
        out.write(frame)
    out.release()

    assert os.path.exists(test_video_path), "Test video should exist before processing"

    # 2. Run video processing
    run_video_processing(test_video_path)

    # 3. Verify that the uploaded video file was automatically deleted
    assert not os.path.exists(test_video_path), "Uploaded video file should be automatically deleted after analysis"

    # Clean up temp dir if any
    shutil.rmtree(temp_dir, ignore_errors=True)
