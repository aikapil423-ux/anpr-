"""Custom UVH-26 class IDs must not be interpreted as COCO classes."""
from types import SimpleNamespace
from src.detection.vehicle_detector import VehicleDetector


def test_uvh26_uses_all_vehicle_classes():
    detector = VehicleDetector.__new__(VehicleDetector)
    detector.model = SimpleNamespace(names=dict(enumerate([
        "Hatchback", "Sedan", "SUV", "MUV", "Bus", "Truck", "Three-wheeler",
        "Two-wheeler", "LCV", "Mini-bus", "tempo-traveller", "bicycle", "Van", "Others"])))
    detector.enable_people = True
    detector._setup_classes([1, 2, 3, 5, 7])
    assert detector.vehicle_classes == list(range(14))
    assert detector.person_classes == []


def test_coco_keeps_explicit_classes():
    detector = VehicleDetector.__new__(VehicleDetector)
    detector.model = SimpleNamespace(names={0: "person", **{i: str(i) for i in range(1, 80)}})
    detector.enable_people = True
    detector._setup_classes([1, 2, 3, 5, 7])
    assert detector.vehicle_classes == [1, 2, 3, 5, 7]
    assert detector.person_classes == [0]
