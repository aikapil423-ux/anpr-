"""Verify imported camera identities and their use in chronological vehicle trails."""
import tempfile
from pathlib import Path
from src.camera.registry import camera_registry, resolve_camera
from src.database.trail_db import TrailDB


def test_imported_registry():
    data = camera_registry()
    assert len(data["sites"]) == 62
    assert len(data["cameras"]) == sum(s["installed_cameras"] for s in data["sites"])
    assert len({c["id"] for c in data["cameras"]}) == len(data["cameras"])
    for site in data["sites"]:
        cameras = [c for c in data["cameras"] if c["site_id"] == site["id"]]
        assert [c["name"] for c in cameras] == [f'{site["name"]} {i}' for i in range(1, site["installed_cameras"]+1)]
        assert all((c["lat"],c["lng"]) == (site["lat"],site["lng"]) for c in cameras)
    assert resolve_camera(location="Aggi Park") is None  # ambiguous site is not a device
    assert resolve_camera(location="Aggi Park 2")["id"] == "KNL-ICCC-001-C02"
    assert resolve_camera(location="unknown checkpoint") is None


def test_registered_camera_trail_and_event_time():
    with tempfile.TemporaryDirectory() as directory:
        db = TrailDB(str(Path(directory) / "trail.sqlite"))
        # Process out-of-order footage; trail must sort by capture time, not processing time.
        for camera, at in [("Aggi Park 2","2026-11-03T10:05:00"),
                           ("Aggi Park 1","2026-11-03T10:00:00"),
                           ("Ambedkar Chowk 1","2026-11-03T10:10:00")]:
            assert db.record_sighting(1,"HR26AB1234",camera_id="UPLOAD-01",location=camera,
                                     gps_coords="0, 0",captured_at=at,passage_id=camera)
        rows = db.get_vehicle_history(1)
        assert [r["location"] for r in rows] == ["Aggi Park 1","Aggi Park 2","Ambedkar Chowk 1"]
        assert rows[0]["camera_id"] == "KNL-ICCC-001-C01"
        assert rows[1]["camera_id"] == "KNL-ICCC-001-C02"
        assert all(r["district"] == "Karnal" for r in rows)
        assert rows[0]["gps_coords"] != "0, 0"
        assert rows[0]["captured_at"].endswith("+05:30")
        assert len(db.get_vehicle_history(1,camera_id="KNL-ICCC-001-C02")) == 1
        assert db.record_sighting(1,"HR26AB1234",location="Aggi Park 1",passage_id="Aggi Park 1") is None


def test_captured_vehicle_uses_registered_location():
    from src.database.captured_db import CapturedDB
    with tempfile.TemporaryDirectory() as directory:
        db = CapturedDB(str(Path(directory) / "captures.sqlite"))
        capture = db.add_capture(plate_number="HR26AB1234", display_plate="HR 26 AB 1234",
                                 confidence=95, location="Aggi Park 2", gps_coords="0, 0")
        assert capture > 0
        row = db.get_recent(limit=1)[0]
        assert row["location"] == "Aggi Park 2"
        assert row["gps_coords"] == "29.693996, 76.96406"
        assert row["district"] == "Karnal"


def test_same_passage_token_on_different_cameras_is_preserved():
    with tempfile.TemporaryDirectory() as directory:
        db = TrailDB(str(Path(directory) / "trail.sqlite"))
        for camera in ("Aggi Park 1", "Aggi Park 2"):
            assert db.record_sighting(1,"HR26AB1234",location=camera,passage_id="same-batch-second")
        assert len(db.get_vehicle_history(1)) == 2
