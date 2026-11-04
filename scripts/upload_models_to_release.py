#!/usr/bin/env python3
"""
Upload local model weights to GitHub Release 'v1.0-weights'
Used to sync heavy weights so TestVMs and other environments can pull via download_models.py.
"""

import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from scripts.download_models import resolve_github_token, fetch_release_info

REPO = "haryana-police/anpr-frs"
TAG = "v1.0-weights"

def upload_asset(file_path: Path, asset_name: str, token: str, release_id: int):
    file_size = file_path.stat().st_size
    print(f"\n>> Uploading {asset_name} ({file_size / 1e6:.1f} MB)...")
    upload_url = f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name={asset_name}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "User-Agent": "HaryanaPolice-ModelUploader"
    }
    
    with open(file_path, "rb") as f:
        data = f.read()

    req = urllib.request.Request(upload_url, data=data, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            dur = time.time() - t0
            print(f"   [SUCCESS] Uploaded {asset_name} in {dur:.1f}s (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        print(f"   [ERROR] Failed to upload {asset_name}: HTTP {e.code} - {e.reason}")
        return False
    except Exception as e:
        print(f"   [ERROR] Failed to upload {asset_path}: {e}")
        return False

def main():
    token = resolve_github_token()
    if not token:
        print("[ERROR] GitHub token with write access required.")
        return 1

    info = fetch_release_info(REPO, TAG, token)
    release_id = info["id"]
    existing = {a["name"]: a for a in info.get("assets", [])}
    print(f"Release '{TAG}' currently has {len(existing)} assets.")

    # Target models to ensure uploaded to release
    targets = [
        REPO_ROOT / "models" / "yolo" / "tanish_yolo11s_plate.pt",
        REPO_ROOT / "models" / "yolo" / "subash_indian_plate.pt",
        REPO_ROOT / "models" / "yolo" / "plate_yolo_ft.pt",
        REPO_ROOT / "models" / "yolo" / "plate_yolo_l.pt",
        REPO_ROOT / "models" / "yolo" / "yolo11l_cctv_ft.pt",
        REPO_ROOT / "models" / "yolo" / "yolo11l_indian_plate.pt",
        REPO_ROOT / "models" / "yolo" / "driveindia_tihan_yolov10m.pt",
    ]

    for p in targets:
        if not p.is_file():
            print(f"[SKIP] Local file not found: {p}")
            continue
        name = p.name
        if name in existing:
            print(f"[EXISTS] {name} ({existing[name]['size'] / 1e6:.1f} MB) already in release. Skipping.")
            continue
        upload_asset(p, name, token, release_id)

    print("\n[DONE] Release sync complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
