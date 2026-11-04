"""Exercise the live AI worker without loading model weights."""
import ast
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_unreadable_live_vehicle_is_saved_once():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "src/camera/stream_manager.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CameraStreamManager")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_ai_worker_loop")
    namespace = {"time": SimpleNamespace(time=lambda: 1.0, sleep=lambda _: None)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "stream_worker", "exec"), namespace)
    class Frame:
        shape = (40, 60, 3)
        size = 7200
        def __getitem__(self, key):
            return self
    frame = Frame()
    vehicle = SimpleNamespace(vehicle_id=1, readings=[], final_plate="", best_vehicle_crop=None)
    db = Mock()
    db.add_capture.return_value = 7
    stop = threading.Event()
    manager = SimpleNamespace(_stop_event=stop, _lock=threading.Lock(), _latest_ai_frame=frame,
        _latest_ai_frame_idx=1, anpr_enabled=True, _track_velocities={}, captured_db=db,
        passage_session_id="test", passage_captures={}, passage_confidences={},
        source_type="demo", location="Test camera", camera_id="CAM-01")
    pipeline = SimpleNamespace(track_merger=SimpleNamespace(vehicles={1: vehicle}))
    pipeline.process_frame = lambda *args, **_: [{"vehicle_id": 1, "track_id": 1, "bbox": (1, 1, 30, 30)}]
    manager._get_pipeline = lambda: pipeline
    class Trigger:
        calls = 0
        def wait(self, timeout):
            self.calls += 1
            manager._latest_ai_frame = frame
            if self.calls > 5:
                stop.set()
            return True
        def clear(self):
            pass
    manager._ai_trigger_event = Trigger()
    namespace["_ai_worker_loop"](manager)
    db.add_capture.assert_called_once()
    assert db.add_capture.call_args.kwargs["plate_number"] == "UNREADABLE"
    assert db.add_capture.call_args.kwargs["source_type"] == "stream_demo"
    assert db.add_capture.call_args.kwargs["vehicle_img"].size > 0
    assert manager.passage_captures["test_1"] == 7
    assert len(manager._cached_displays) == 1
