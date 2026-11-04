"""
Incident Evidence Video Clip Recorder
Automatically captures pre-hit and post-hit video buffers on Hotlist / Criminal matches
and produces web-playable H.264 MP4 clips for permanent digital forensic preservation.
"""
import os
import time
import subprocess
import threading
from typing import List, Tuple, Optional, Any
import cv2
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLIPS_DIR = os.path.join(BASE_DIR, "outputs", "evidence_clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

def transcode_to_web_mp4(raw_path: str, web_path: str) -> bool:
    """Transcodes video to web-standard H.264 (yuv420p) for HTML5 video tags."""
    cmd = [
        "ffmpeg", "-y", "-i", raw_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-crf", "24",
        "-movflags", "+faststart",
        web_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return res.returncode == 0 and os.path.exists(web_path) and os.path.getsize(web_path) > 0
    except Exception:
        return False

def compile_evidence_clip(
    frames: List[np.ndarray],
    entity_id: str,
    fps: float = 20.0
) -> Optional[str]:
    """
    Compiles a list of BGR video frames into an incident evidence clip MP4.
    Returns the web-accessible relative URL (e.g. '/outputs/evidence_clips/...').
    """
    if not frames or len(frames) < 5:
        return None

    clean_id = "".join(c for c in entity_id if c.isalnum() or c in ("-", "_")).upper()
    ts = int(time.time())
    raw_fn = f"raw_{clean_id}_{ts}.mp4"
    web_fn = f"clip_{clean_id}_{ts}.mp4"
    raw_path = os.path.join(CLIPS_DIR, raw_fn)
    web_path = os.path.join(CLIPS_DIR, web_fn)

    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(raw_path, fourcc, max(10.0, min(30.0, fps)), (w, h))

    try:
        for f in frames:
            if f is not None and getattr(f, "size", 0) > 0:
                if f.shape[:2] != (h, w):
                    f = cv2.resize(f, (w, h))
                writer.write(f)
        writer.release()
    except Exception as e:
        print(f"[EvidenceClipRecorder] Write error: {e}")
        try:
            writer.release()
        except Exception:
            pass
        return None

    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
        if transcode_to_web_mp4(raw_path, web_path):
            try:
                os.remove(raw_path)
            except Exception:
                pass
            return f"/outputs/evidence_clips/{web_fn}"
        else:
            return f"/outputs/evidence_clips/{raw_fn}"

    return None
