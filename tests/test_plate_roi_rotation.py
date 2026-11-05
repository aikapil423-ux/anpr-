import unittest
import numpy as np
from src.detection.plate_candidates import detect_plate_candidates

class PlateRetryTests(unittest.TestCase):
    def test_retry_rotation_covers_vehicles_outside_first_four(self):
        class Detector:
            def __init__(self): self.crops = 0
            def detect_in_frame(self, frame, **kwargs):
                if kwargs.get("vehicle_boxes") is not None: return []
                self.crops += 1
                return [{"bbox": (5, 5, 25, 15), "conf": .8}]
        vehicles = [{"bbox": (i*60, 0, i*60+50, 50), "cls_name": "car"} for i in range(6)]
        frame = np.zeros((60, 400, 3), dtype=np.uint8)
        first = detect_plate_candidates(Detector(), frame, vehicles, .35, retry_offset=0)
        second = detect_plate_candidates(Detector(), frame, vehicles, .35, retry_offset=4)
        seen = {p["vehicle_bbox"] for p in first + second}
        self.assertEqual(seen, {v["bbox"] for v in vehicles})
        self.assertEqual(len(first), 4)
        for p in first + second:
            self.assertGreaterEqual(p["bbox"][0], p["vehicle_bbox"][0])
