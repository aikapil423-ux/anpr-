"""Shared authoritative names and coordinates for the imported Karnal camera sites."""
import json
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "resources" / "karnal_cameras.json"
router = APIRouter()


@lru_cache(maxsize=1)
def camera_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def resolve_camera(camera_id=None, location=None):
    """Match explicit site ID or exact name only; never guess a nearby camera."""
    values = {str(v).strip().casefold() for v in (camera_id, location) if v}
    for camera in camera_registry()["cameras"]:
        if camera["id"].casefold() in values or camera["name"].casefold() in values:
            return camera.copy()
    return None


def camera_metadata(camera):
    return camera["id"], camera["name"], f'{camera["lat"]}, {camera["lng"]}'


@router.get("/api/cameras/registry")
def get_camera_registry():
    data = camera_registry()
    return {**data, "count": len(data["cameras"]), "site_count": len(data["sites"])}
