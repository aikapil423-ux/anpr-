import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import app

class BackgroundUploadTests(unittest.TestCase):
    def test_accepted_job_preserves_file_and_publishes_result(self):
        async def analyze(file, **kwargs):
            self.assertEqual(await file.read(), b"video bytes")
            return {"success": True, "vehicles": [{"final_plate": "HR54G2404"}]}
        with patch.object(app, "_handle_unified_upload_impl", side_effect=analyze):
            client = TestClient(app.app)
            response = client.post("/api/unified/upload", data={"background":"true", "task_id":"test-bg-success"}, files={"file":("test.avi",b"video bytes","video/avi")})
            self.assertEqual(response.status_code, 202)
            state = client.get("/api/unified/upload-progress?task_id=test-bg-success").json()
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["result"]["vehicles"][0]["final_plate"], "HR54G2404")

    def test_job_failure_is_reported(self):
        with patch.object(app, "_handle_unified_upload_impl", new=AsyncMock(side_effect=ValueError("Bad video"))):
            client = TestClient(app.app)
            response = client.post("/api/unified/upload", data={"background":"true", "task_id":"test-bg-error"}, files={"file":("test.avi",b"bad","video/avi")})
            self.assertEqual(response.status_code, 202)
            state = client.get("/api/unified/upload-progress?task_id=test-bg-error").json()
            self.assertEqual(state["status"], "error")
            self.assertEqual(state["status_text"], "Bad video")
