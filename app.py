"""



FastAPI Application for ANPR System



Provides REST API, video processing pipeline endpoints, and static web dashboard.



"""
import os
import sys
try:
    import torch
except Exception:
    pass
os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')
import io
import base64
import time
import datetime
import subprocess
import json
import threading
import asyncio
import contextvars
import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Union
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request, Query, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import torch
if hasattr(torch, 'set_num_threads'):
    try:
        torch.set_num_threads(os.cpu_count() or 4)
    except Exception:
        pass
from config import ANPRConfig
from src.pipeline.anpr_pipeline import ANPRPipeline
from src.pipeline.video_sampling import VideoFrameSampler
from src.identity.vehicle_identity import VehicleRecord
from src.ocr.enhancer import PlateEnhancer
from src.database.vehicle_db import VehicleDB
from src.database.captured_db import CapturedDB
import src.database.violation_db as violation_db
from src.database.trail_db import TrailDB
from src.database.audit_db import AlertAuditDB
from src.database.auth_db import AuthDB
from src.database.investigation_history_db import InvestigationHistoryDB
from src.camera.stream_manager import CameraStreamManager, MultiCameraStreamManager
from src.pipeline.unified_pipeline import UnifiedPipeline
app = FastAPI(title='Smart ANPR Vehicle Verification System', version='1.0.0')
from src.camera.registry import router as camera_registry_router, resolve_camera, camera_metadata
app.include_router(camera_registry_router)
logger = logging.getLogger('anpr_app')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'outputs')
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
DATA_DIR_PHOTOS = os.path.join(DATA_DIR, 'vehicle_photos')
os.makedirs(DATA_DIR_PHOTOS, exist_ok=True)
DEMO_VIDEOS_DIR = os.path.join(DATA_DIR, 'demo_videos')
os.makedirs(DEMO_VIDEOS_DIR, exist_ok=True)
DEMO_VIDEOS = {'demo_1': {'id': 'demo_1', 'title': 'Demo 1 — Highway Traffic Feed (Highway & Two-Wheelers)', 'path': os.path.join(DEMO_VIDEOS_DIR, 'demo_1.mp4'), 'default_location': 'North Gate Toll (Highway)'}, 'demo_2': {'id': 'demo_2', 'title': 'Demo 2 — Urban Junction Feed (City Traffic & Vehicles)', 'path': os.path.join(DEMO_VIDEOS_DIR, 'demo_2.mp4'), 'default_location': 'Sector 18 Chowk (Junction)'}, 'demo_3': {'id': 'demo_3', 'title': 'Demo 3 — Security Checkpoint Feed (Surveillance Lane)', 'path': os.path.join(DEMO_VIDEOS_DIR, 'demo_3.mp4'), 'default_location': 'East Gate Checkpost'}}
current_user_cv: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar('current_user', default=None)
DEMO_DATA_DIR = os.path.join(DATA_DIR, 'demo')
os.makedirs(DEMO_DATA_DIR, exist_ok=True)
prod_vehicle_db = VehicleDB(os.path.join(DATA_DIR, 'vehicle_db.sqlite'))
violation_db.init_db()
prod_captured_db = CapturedDB(os.path.join(DATA_DIR, 'captured_db.sqlite'))
prod_trail_db = TrailDB(os.path.join(DATA_DIR, 'vehicle_trail.sqlite'))
prod_audit_db = AlertAuditDB(os.path.join(DATA_DIR, 'alert_audit.sqlite'))
prod_investigation_db = InvestigationHistoryDB(os.path.join(DATA_DIR, 'investigation_history.sqlite'))
demo_vehicle_db = VehicleDB(os.path.join(DEMO_DATA_DIR, 'vehicle_db.sqlite'))
demo_captured_db = CapturedDB(os.path.join(DEMO_DATA_DIR, 'captured_db.sqlite'))
demo_trail_db = TrailDB(os.path.join(DEMO_DATA_DIR, 'vehicle_trail.sqlite'))
demo_audit_db = AlertAuditDB(os.path.join(DEMO_DATA_DIR, 'alert_audit.sqlite'))
demo_investigation_db = InvestigationHistoryDB(os.path.join(DEMO_DATA_DIR, 'investigation_history.sqlite'))
auth_db = AuthDB()

class UserAwareDBProxy:
    """Dynamically routes queries and mutations to Demo DB for developer_admin, and Production DB for official accounts."""

    def __init__(self, prod_instance, demo_instance):
        self._prod = prod_instance
        self._demo = demo_instance

    def _get_target(self):
        u = current_user_cv.get()
        if u and (u.get('role') == 'DEVELOPER_ADMIN' or str(u.get('username', '')).lower() == 'developer_admin'):
            return self._demo
        return self._prod

    def __getattr__(self, name):
        return getattr(self._get_target(), name)
vehicle_db = UserAwareDBProxy(prod_vehicle_db, demo_vehicle_db)
captured_db = UserAwareDBProxy(prod_captured_db, demo_captured_db)
trail_db = UserAwareDBProxy(prod_trail_db, demo_trail_db)
audit_db = UserAwareDBProxy(prod_audit_db, demo_audit_db)
investigation_db = UserAwareDBProxy(prod_investigation_db, demo_investigation_db)
detection_db = captured_db
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get('hp_surveillance_session')
    if not token:
        token = request.query_params.get('session') or request.query_params.get('token')
    if not token:
        auth_hdr = request.headers.get('Authorization') or request.headers.get('X-Session-Token')
        if auth_hdr and auth_hdr.startswith('Bearer '):
            token = auth_hdr[7:].strip()
        elif auth_hdr:
            token = auth_hdr.strip()
    if token:
        if token in ACTIVE_SESSIONS:
            return ACTIVE_SESSIONS[token]
        db_user = auth_db.get_session(token)
        if db_user:
            ACTIVE_SESSIONS[token] = db_user
            return db_user
    return None

@app.middleware('http')
async def user_context_middleware(request: Request, call_next):
    user = get_current_user_optional(request)
    token = current_user_cv.set(user)
    try:
        response = await call_next(request)
        if request.url.path == '/' or request.url.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    finally:
        current_user_cv.reset(token)
user_stream_managers: Dict[str, MultiCameraStreamManager] = {}
_user_stream_lock = threading.Lock()

def get_user_stream_manager(request_or_user: Union[Request, Dict[str, Any], str, None]) -> MultiCameraStreamManager:
    global user_stream_managers
    user_info = None
    user_key = 'guest'
    if isinstance(request_or_user, Request):
        user_info = get_current_user_optional(request_or_user)
    elif isinstance(request_or_user, dict):
        user_info = request_or_user
    elif isinstance(request_or_user, str) and request_or_user.strip():
        user_key = request_or_user.strip().lower()
    if user_info and isinstance(user_info, dict):
        uname = user_info.get('username') or user_info.get('name') or user_info.get('id')
        if uname:
            user_key = str(uname).strip().lower()
    with _user_stream_lock:
        if user_key not in user_stream_managers:
            district = 'Panipat'
            op_username = user_key
            op_id = None
            station = 'PHQ'
            if user_info:
                district = user_info.get('district') or district
                op_username = user_info.get('username') or op_username
                op_id = user_info.get('id') or user_info.get('operator_id')
                station = user_info.get('station') or user_info.get('police_station') or station
            is_dev = user_key == 'developer_admin' or (user_info and user_info.get('role') == 'DEVELOPER_ADMIN')
            user_vdb = demo_vehicle_db if is_dev else prod_vehicle_db
            user_cdb = demo_captured_db if is_dev else prod_captured_db
            user_tdb = demo_trail_db if is_dev else prod_trail_db
            user_adb = demo_audit_db if is_dev else prod_audit_db
            from src.detection.model_registry import registry
            live_config=ANPRConfig()
            live_config.vehicle_model_name=registry.resolve_model_path(registry.get_active_model_id('vehicle',target='live'))
            live_config.plate_model_path=registry.resolve_model_path(registry.get_active_model_id('plate',target='live'))
            live_config.ocr_model=registry.get_active_model_id('ocr',target='live')
            mgr = MultiCameraStreamManager(config=live_config, vehicle_db=user_vdb, captured_db=user_cdb, trail_db=user_tdb, audit_db=user_adb, district=district, operator_username=op_username, operator_id=op_id, station=station)
            user_stream_managers[user_key] = mgr
        return user_stream_managers[user_key]
stream_manager = get_user_stream_manager('guest')
_anpr_pipeline: Optional[ANPRPipeline] = None
_anpr_lock = threading.Lock()

def get_anpr_pipeline() -> ANPRPipeline:
    global _anpr_pipeline
    if _anpr_pipeline is None:
        with _anpr_lock:
            if _anpr_pipeline is None:
                config = ANPRConfig()
                config.voting.min_supporting_frames = 2
                from src.detection.model_registry import registry
                config.vehicle_model_name = registry.resolve_model_path(registry.active_vehicle_id)
                config.plate_model_path = registry.resolve_model_path(registry.active_plate_id)
                config.ocr_model = registry.active_ocr_id
                pipeline = ANPRPipeline(config=config, async_ocr=False, max_ocr_queue_size=64)
                pipeline.init_models()
                _anpr_pipeline = pipeline
    return _anpr_pipeline
_unified_pipeline: Optional[UnifiedPipeline] = None

def get_unified_pipeline() -> UnifiedPipeline:
    global _unified_pipeline
    if _unified_pipeline is None:
        anpr = get_anpr_pipeline()
        with _user_stream_lock:
            for s_mgr in user_stream_managers.values():
                pass
        _unified_pipeline = UnifiedPipeline(anpr_pipeline=anpr)
    return _unified_pipeline
_upload_anpr_pipeline: Optional[ANPRPipeline] = None
_upload_anpr_lock = threading.Lock()

def get_upload_anpr_pipeline() -> ANPRPipeline:
    global _upload_anpr_pipeline
    if _upload_anpr_pipeline is None:
        with _upload_anpr_lock:
            if _upload_anpr_pipeline is None:
                config = ANPRConfig()
                config.voting.min_supporting_frames = 1
                from src.detection.model_registry import registry
                up_veh = registry.get_active_model_id('vehicle', target='upload')
                up_plt = registry.get_active_model_id('plate', target='upload')
                config.vehicle_model_name = registry.resolve_model_path(up_veh)
                config.plate_model_path = registry.resolve_model_path(up_plt)
                config.ocr_model = registry.get_active_model_id('ocr', target='upload')
                pipeline = ANPRPipeline(config=config, async_ocr=False, max_ocr_queue_size=64)
                pipeline.init_models()
                _upload_anpr_pipeline = pipeline
    return _upload_anpr_pipeline
_upload_unified_pipeline: Optional[UnifiedPipeline] = None
_upload_unified_lock = threading.Lock()

def get_upload_unified_pipeline() -> UnifiedPipeline:
    global _upload_unified_pipeline
    if _upload_unified_pipeline is None:
        with _upload_unified_lock:
            if _upload_unified_pipeline is None:
                anpr = get_upload_anpr_pipeline()
                _upload_unified_pipeline = UnifiedPipeline(anpr_pipeline=anpr)
    return _upload_unified_pipeline

@app.on_event('startup')
def app_startup():
    try:
        from scripts.download_models import ensure_essential_models
        ensure_essential_models(verbose=False)
    except Exception as e:
        logger.warning(f'Auto model check warning: {e}')
    try:
        import subprocess
        subprocess.run(['git', 'config', 'core.hooksPath', '.githooks'], capture_output=True, timeout=5)
    except Exception:
        pass

    def _ensure_and_warmup():
        try:
            import paddle
            import safetensors
        except ImportError:
            try:
                import subprocess
                logger.info('[Auto-Heal] Missing paddle/safetensors. Installing in background...')
                subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', 'paddlepaddle>=2.6.0', 'safetensors>=0.4.0'], capture_output=True, timeout=300)
                logger.info('[Auto-Heal] PaddlePaddle & Safetensors installed successfully!')
            except Exception as ex:
                logger.warning(f'[Auto-Heal] Background install error: {ex}')
        anpr = get_anpr_pipeline()
        get_unified_pipeline()
        try:
            if anpr and anpr.ocr_engine:
                dummy = np.zeros((48, 128, 3), dtype=np.uint8)
                anpr.ocr_engine.read_text(dummy)
        except Exception:
            pass
    threading.Thread(target=_ensure_and_warmup, daemon=True).start()

@app.on_event('shutdown')
def app_shutdown():
    global _anpr_pipeline
    if _anpr_pipeline is not None:
        _anpr_pipeline.close()
    with _user_stream_lock:
        for mgr in user_stream_managers.values():
            mgr.stop_all()
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
app.mount('/data', StaticFiles(directory=DATA_DIR), name='data')
app.mount('/outputs', StaticFiles(directory=OUTPUTS_DIR), name='outputs')
user_pipeline_states: Dict[str, Dict[str, Any]] = {}

def get_user_pipeline_state(username: Optional[str]=None) -> Dict[str, Any]:
    key = (username or 'op_5421').lower().strip()
    if key not in user_pipeline_states:
        user_pipeline_states[key] = {'is_processing': False, 'progress': 0.0, 'current_frame': 0, 'total_frames': 0, 'results': None}
    return user_pipeline_states[key]
pipeline_state = get_user_pipeline_state('op_5421')

def resolve_rbac_filters(user: Optional[Dict[str, Any]], requested_district: Optional[str]=None, requested_operator: Optional[str]=None) -> tuple[Optional[str], Optional[str]]:
    """



    Enforces Multi-Tenant RBAC scope resolution:



    - STATE_ADMIN: Statewide access; can filter by any district or any operator, or None for statewide.



    - DISTRICT_ADMIN: Strictly scoped to user's assigned district; can filter by operators in their district.



    - OPERATOR: Strictly scoped to own district & own operator username.



    """
    if not user:
        return ('__UNAUTHENTICATED__', '__UNAUTHENTICATED__')
    role = str(user.get('role', 'OPERATOR')).upper().strip()
    user_dist = str(user.get('district', 'Panipat')).strip()
    user_uname = str(user.get('username', '')).strip().lower()
    if role in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
        target_dist = None if not requested_district or requested_district.upper() in ('ALL', 'ALL HARYANA', 'ALL HARYANA (STATE HQ)') else requested_district.strip()
        target_op = None if not requested_operator or requested_operator.upper() in ('ALL', 'ALL OPERATORS') else requested_operator.strip().lower()
        return (target_dist, target_op)
    elif role == 'DISTRICT_ADMIN':
        target_dist = user_dist
        target_op = None if not requested_operator or requested_operator.upper() in ('ALL', 'ALL OPERATORS') else requested_operator.strip().lower()
        return (target_dist, target_op)
    else:
        return (user_dist, user_uname)

def encode_image_base64(img: Optional[np.ndarray]) -> str:
    if img is None or img.size == 0:
        return ''
    success, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        return ''
    return base64.b64encode(buffer).decode('utf-8')

def cleanup_file_safely(file_path: Optional[str]):
    """



    Safely deletes an uploaded media file (video or photo) from disk after



    analysis completes and results are permanently stored in Captured DB.



    """
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f'[Auto-Cleanup] Uploaded media file automatically deleted: {file_path}')
    except Exception as e:
        print(f'[Auto-Cleanup Warning] Failed to delete uploaded media file {file_path}: {e}')

def format_seconds_to_timestamp_str(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return '00:00.0s'
    m = int(seconds // 60)
    s = seconds % 60
    return f'{m:02d}:{s:04.1f}s'

def format_hotlist_info(db_match: Optional[Dict[str, Any]]) -> Optional[str]:
    if not db_match:
        return None
    owner_parts = []
    if db_match.get('owner_name'):
        owner_parts.append(f"Owner: {db_match.get('owner_name')}")
    if db_match.get('owner_father_name'):
        owner_parts.append(f"S/o: {db_match.get('owner_father_name')}")
    if db_match.get('owner_mobile'):
        owner_parts.append(f"Mob: {db_match.get('owner_mobile')}")
    if db_match.get('owner_address'):
        owner_parts.append(f"Addr: {db_match.get('owner_address')}")
    owner_str = f" | {' '.join(owner_parts)}" if owner_parts else ''
    if db_match.get('involved_in_case'):
        return f"POLICE CASE: {db_match.get('offence_type', 'Crime')} | FIR: {db_match.get('fir_number', 'N/A')} | PS: {db_match.get('police_station', 'N/A')}{owner_str}"
    else:
        return f"LOST VEHICLE: {db_match.get('lost_location', 'Unknown location')}{owner_str}"

def serialize_vehicle(v: VehicleRecord) -> Dict[str, Any]:
    db_match = vehicle_db.match_plate(v.final_plate) if v.final_plate else None
    peak_conf = round(max([float(ef.confidence) for ef in v.evidence_frames] + [float(v.final_confidence)]) * 100, 1) if v.evidence_frames else round(float(v.final_confidence) * 100, 1)
    sorted_ev = sorted(v.evidence_frames, key=lambda ef: float(ef.confidence), reverse=True)
    first_ts = getattr(v, 'first_timestamp', 0.0)
    last_ts = getattr(v, 'last_timestamp', 0.0)
    first_time_str = format_seconds_to_timestamp_str(first_ts)
    last_time_str = format_seconds_to_timestamp_str(last_ts)
    if first_time_str == last_time_str or last_ts <= first_ts:
        video_window_str = first_time_str
    else:
        video_window_str = f'{first_time_str} - {last_time_str}'
    return {'vehicle_id': v.vehicle_id, 'linked_track_ids': sorted(list(v.linked_track_ids)), 'first_frame': v.first_frame, 'last_frame': v.last_frame, 'duration_frames': max(1, v.last_frame - v.first_frame + 1), 'first_timestamp': round(float(first_ts), 2), 'last_timestamp': round(float(last_ts), 2), 'first_time_str': first_time_str, 'last_time_str': last_time_str, 'video_window_str': video_window_str, 'video_time_str': first_time_str, 'final_plate': v.final_plate, 'display_plate': v.display_plate or v.final_plate, 'final_confidence': peak_conf, 'consensus_confidence': round(float(v.final_confidence) * 100, 1), 'is_verified': v.is_verified, 'status': v.status, 'review_reason': v.review_reason, 'supporting_frames_count': len(v.readings), 'best_crop_base64': encode_image_base64(v.best_crop), 'best_enhanced_crop_base64': encode_image_base64(getattr(v, 'best_enhanced_crop', None)), 'preprocessing_meta': getattr(v, 'preprocessing_meta', None), 'best_vehicle_crop_base64': encode_image_base64(v.best_vehicle_crop), 'best_annotated_frame_base64': encode_image_base64(getattr(v, 'best_annotated_frame', None)), 'hotlist_match': db_match, 'evidence_frames': [{'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'raw_text': getattr(ef, 'raw_text', ef.text), 'confidence': round(float(ef.confidence) * 100, 1), 'ocr_confidence': round(float(getattr(ef, 'ocr_confidence', 0.0)) * 100, 1) if getattr(ef, 'ocr_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'ocr_confidence', 0.0)), 1), 'det_confidence': round(float(getattr(ef, 'det_confidence', 0.0)) * 100, 1) if getattr(ef, 'det_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'det_confidence', 0.0)), 1), 'crop_base64': encode_image_base64(ef.crop_image), 'vehicle_crop_base64': encode_image_base64(getattr(ef, 'vehicle_crop', None)) if getattr(ef, 'vehicle_crop', None) is not None else None, 'timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'video_timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0)), 'video_time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0))} for ef in sorted_ev]}

def annotate_anpr_frame(frame: np.ndarray, active_displays: list) -> np.ndarray:
    annotated = frame.copy()
    for ad in active_displays:
        vx1, vy1, vx2, vy2 = ad['bbox']
        tid = ad.get('track_id', 1)
        cls_name = ad.get('cls_name', 'Vehicle').capitalize()
        veh_color = (255, 140, 0)
        cv2.rectangle(annotated, (vx1, vy1), (vx2, vy2), veh_color, 2)
        veh_lbl = f'{cls_name} #{tid}'
        (vtw, vth), _ = cv2.getTextSize(veh_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(annotated, (vx1, max(0, vy1 - vth - 6)), (vx1 + vtw + 6, vy1), veh_color, -1)
        cv2.putText(annotated, veh_lbl, (vx1 + 3, max(vth + 2, vy1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        pbox = ad.get('plate_bbox')
        if pbox is not None:
            px1, py1, px2, py2 = pbox
            plate_disp = ad.get('display_plate') or ad.get('candidate_plate') or ''
            is_verified = ad.get('is_verified', False)
            is_analyzing = ad.get('is_analyzing', False)
            conf = int((ad.get('confidence') or 0.0) * 100)
            if plate_disp:
                plate_color = (16, 185, 129) if is_verified else (245, 158, 11)
                plate_lbl = f'{plate_disp} ({conf}%)'
            elif is_analyzing:
                plate_color = (245, 158, 11)
                plate_lbl = 'Plate: Analyzing...'
            else:
                plate_color = (16, 185, 129)
                plate_lbl = 'Plate'
            cv2.rectangle(annotated, (px1, py1), (px2, py2), plate_color, 2)
            (ptw, pth), _ = cv2.getTextSize(plate_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(annotated, (px1, max(0, py1 - pth - 6)), (px1 + ptw + 6, py1), plate_color, -1)
            cv2.putText(annotated, plate_lbl, (px1 + 3, max(pth + 2, py1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    return annotated

def transcode_to_h264_web(raw_path: str, final_path: str) -> bool:
    """



    Transcodes an OpenCV-produced video into web-standard H.264 (yuv420p + faststart).



    Ensures native, seamless playback inside HTML5 <video> tags in all web browsers.



    """
    cmd = ['ffmpeg', '-y', '-i', raw_path, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'veryfast', '-crf', '23', '-movflags', '+faststart', final_path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        return res.returncode == 0 and os.path.exists(final_path) and (os.path.getsize(final_path) > 0)
    except Exception as e:
        print(f'[FFmpeg Transcode Warning]: {e}')
        return False

def run_video_processing(video_path: str, target_fps: int=5, operator_username: str='op_5421', district: str='Panipat', operator_id: Optional[int]=None, station: str='PHQ', save_annotated: bool=True):
    p_state = get_user_pipeline_state(operator_username)
    p_state['is_processing'] = True
    p_state['progress'] = 0.0
    video_writer = None
    annotated_video_filename = None
    raw_video_path = None
    annotated_video_path = None
    writer_w, writer_h = (640, 480)
    try:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        raw_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        fps = raw_fps if raw_fps > 0 else 25.0
        p_state['total_frames'] = total_frames
        sampler = VideoFrameSampler(fps, target_fps)
        out_fps = sampler.output_fps
        if save_annotated:
            orig_filename = os.path.basename(video_path)
            base_name, _ = os.path.splitext(orig_filename)
            annotated_video_filename = f'annotated_{base_name}_{int(time.time())}.mp4'
            annotated_video_path = os.path.join(OUTPUTS_DIR, annotated_video_filename)
            raw_video_path = os.path.join(OUTPUTS_DIR, f'raw_{annotated_video_filename}')
            writer_w = orig_w if orig_w % 2 == 0 else orig_w - 1
            writer_h = orig_h if orig_h % 2 == 0 else orig_h - 1
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(raw_video_path, fourcc, out_fps, (writer_w, writer_h))
        pipeline = get_upload_anpr_pipeline()
        pipeline.reset_state()
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if not sampler.includes(frame_idx):
                continue
            timestamp = frame_idx / fps
            active_displays = pipeline.process_frame(frame, frame_idx=frame_idx, timestamp=timestamp, sync=True)
            if save_annotated and video_writer is not None and video_writer.isOpened():
                annotated_frame = annotate_anpr_frame(frame, active_displays)
                if (writer_w, writer_h) != (annotated_frame.shape[1], annotated_frame.shape[0]):
                    frame_to_write = cv2.resize(annotated_frame, (writer_w, writer_h))
                else:
                    frame_to_write = annotated_frame
                video_writer.write(frame_to_write)
            p_state['current_frame'] = frame_idx
            if total_frames > 0:
                p_state['progress'] = round(frame_idx / total_frames * 85.0, 1)
        cap.release()
        if video_writer is not None:
            video_writer.release()
            video_writer = None
        p_state['progress'] = 88.0
        if save_annotated and raw_video_path and os.path.exists(raw_video_path):
            h264_success = transcode_to_h264_web(raw_video_path, annotated_video_path)
            if h264_success:
                try:
                    os.remove(raw_video_path)
                except Exception:
                    pass
            else:
                try:
                    os.replace(raw_video_path, annotated_video_path)
                except Exception:
                    annotated_video_filename = f'raw_{annotated_video_filename}'
        p_state['progress'] = 93.0
        pipeline.drain_ocr_queue(timeout=15.0)
        final_data = pipeline.finalize()
        verified_serialized = [serialize_vehicle(v) for v in final_data['verified_vehicles']]
        needs_review_serialized = [serialize_vehicle(v) for v in final_data['needs_review']]
        unreadable_serialized = [serialize_vehicle(v) for v in final_data.get('unreadable_vehicles', [])]
        all_targets = final_data['verified_vehicles'] + [v for v in final_data['needs_review'] if v.final_plate]
        deduped_targets = []
        for v in all_targets:
            is_dup = False
            for dv in deduped_targets:
                sim = pipeline.normalizer.calculate_levenshtein(v.final_plate, dv.final_plate)
                time_diff = abs(v.first_timestamp - dv.first_timestamp)
                if sim >= 0.8 and time_diff <= 3.5:
                    if v.final_confidence > dv.final_confidence:
                        dv.final_plate = v.final_plate
                        dv.display_plate = v.display_plate
                        dv.final_confidence = v.final_confidence
                        dv.best_crop = v.best_crop
                        dv.best_vehicle_crop = v.best_vehicle_crop
                        dv.best_annotated_frame = getattr(v, 'best_annotated_frame', None)
                        dv.readings.extend(v.readings)
                    is_dup = True
                    break
            if not is_dup:
                deduped_targets.append(v)
        logged_plates = set()
        for v in deduped_targets:
            final_conf_pct = round(float(v.final_confidence) * 100, 1)
            if final_conf_pct < 20.0:
                continue
            if v.final_plate and v.final_plate not in logged_plates:
                logged_plates.add(v.final_plate)
                db_match = vehicle_db.match_plate(v.final_plate) if v.final_plate != 'UNREADABLE' else None
                hotlist_info_str = None
                if db_match:
                    if db_match.get('involved_in_case'):
                        hotlist_info_str = f"POLICE CASE: {db_match.get('offence_type', 'Crime')} | FIR: {db_match.get('fir_number', 'N/A')} | PS: {db_match.get('police_station', 'N/A')}"
                    else:
                        hotlist_info_str = f"LOST VEHICLE: {db_match.get('lost_location', 'Unknown location')}"
                best_r = max(v.readings, key=lambda r: (r.ocr_confidence, getattr(r, 'blur_score', 0.0))) if v.readings and len(v.readings) > 0 else None
                peak_ocr_pct = round(max([r.ocr_confidence for r in v.readings] + [v.final_confidence]) * 100, 1) if v.readings else final_conf_pct
                peak_det_pct = round(max([r.detection_confidence for r in v.readings] + [0.0]) * 100, 1) if v.readings else 0.0
                scene_evidence = getattr(v, 'best_annotated_frame', None)
                if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                    scene_evidence = v.best_vehicle_crop if v.best_vehicle_crop is not None else v.best_crop
                sorted_evidence_frames = sorted(getattr(v, 'evidence_frames', []), key=lambda ef: float(ef.confidence), reverse=True)
                evidence_list = [{'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'raw_text': getattr(ef, 'raw_text', ef.text), 'confidence': round(float(ef.confidence) * 100, 1), 'ocr_confidence': round(float(getattr(ef, 'ocr_confidence', 0.0)) * 100, 1) if getattr(ef, 'ocr_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'ocr_confidence', 0.0)), 1), 'det_confidence': round(float(getattr(ef, 'det_confidence', 0.0)) * 100, 1) if getattr(ef, 'det_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'det_confidence', 0.0)), 1), 'crop_base64': encode_image_base64(ef.crop_image), 'vehicle_crop_base64': encode_image_base64(getattr(ef, 'vehicle_crop', None)) if getattr(ef, 'vehicle_crop', None) is not None else None, 'timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'video_timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0)), 'video_time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0))} for ef in sorted_evidence_frames]
                primary_track_id = next(iter(v.linked_track_ids)) if v.linked_track_ids else v.readings[0].track_id if v.readings else None
                linked_tracks_str = ','.join((str(tid) for tid in sorted(v.linked_track_ids))) if v.linked_track_ids else str(primary_track_id) if primary_track_id is not None else ''
                captured_db.add_capture(plate_number=v.final_plate, display_plate=v.display_plate or v.final_plate, confidence=peak_ocr_pct, plate_img=v.best_crop, vehicle_img=v.best_vehicle_crop, annotated_img=scene_evidence, location='Main Surveillance Feed / Video', source_type='video_upload', is_hotlist_hit=db_match is not None, hotlist_info=hotlist_info_str, blur_score=round(float(best_r.blur_score), 1) if best_r and best_r.blur_score is not None else 0.0, aspect_ratio=round(float(getattr(best_r, 'aspect_ratio', 0.0)), 2) if best_r else 0.0, det_confidence=peak_det_pct if peak_det_pct > 0 else round(float(best_r.detection_confidence) * 100, 1) if best_r else 0.0, ocr_confidence=peak_ocr_pct, format_type=getattr(v, 'format_type', None) or (best_r.format_type if best_r else 'standard'), quality_gate_passed=v.is_verified, quality_reason='Temporal Voting Multi-Frame Verified' if v.is_verified else v.review_reason or 'Needs Review', evidence_data=evidence_list, enhanced_img=getattr(v, 'best_enhanced_crop', None), preprocessing_data=getattr(v, 'preprocessing_meta', None), track_id=primary_track_id, linked_tracks=linked_tracks_str, vehicle_id=v.vehicle_id, district=district, operator_id=operator_id, operator_username=operator_username, station=station, is_traffic_violation=bool(v.get('is_traffic_violation', False)), violation_type=v.get('violation_type'), violation_fine=v.get('violation_fine', 0), violation_id=v.get('violation_id'), violation_details=v.get('violation_details'))
                if v.is_verified and db_match and (v.final_plate != 'UNREADABLE'):
                    passage_id = f'video_{os.path.basename(video_path)}_{v.vehicle_id}'
                    trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=v.final_plate, camera_id='CAM-01', location='Main Surveillance Gate', captured_at=datetime.datetime.now().astimezone().isoformat(), confidence=round(float(v.final_confidence) * 100, 1), plate_img=v.best_crop, vehicle_img=v.best_vehicle_crop, passage_id=passage_id, min_cooldown_seconds=3.0, district=district, operator_id=operator_id, operator_username=operator_username, station=station)
        unreadable_targets = final_data.get('unreadable_vehicles', [])
        for uv in unreadable_targets:
            first_r = uv.readings[0] if uv.readings and len(uv.readings) > 0 else None
            det_conf = round(float(first_r.detection_confidence) * 100, 1) if first_r and first_r.detection_confidence is not None else 0.0
            if len(uv.readings) < 5 or det_conf < 50.0:
                continue
            scene_evidence = getattr(uv, 'best_annotated_frame', None)
            if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                scene_evidence = uv.best_vehicle_crop if uv.best_vehicle_crop is not None else uv.best_crop
            evidence_list = [{'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'raw_text': getattr(ef, 'raw_text', ef.text), 'confidence': round(float(ef.confidence) * 100, 1), 'ocr_confidence': round(float(getattr(ef, 'ocr_confidence', 0.0)) * 100, 1) if getattr(ef, 'ocr_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'ocr_confidence', 0.0)), 1), 'det_confidence': round(float(getattr(ef, 'det_confidence', 0.0)) * 100, 1) if getattr(ef, 'det_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'det_confidence', 0.0)), 1), 'crop_base64': encode_image_base64(ef.crop_image), 'vehicle_crop_base64': encode_image_base64(getattr(ef, 'vehicle_crop', None)) if getattr(ef, 'vehicle_crop', None) is not None else None, 'timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'video_timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0)), 'video_time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0))} for ef in getattr(uv, 'evidence_frames', [])]
            primary_track_id = next(iter(uv.linked_track_ids)) if uv.linked_track_ids else uv.readings[0].track_id if uv.readings else None
            linked_tracks_str = ','.join((str(tid) for tid in sorted(uv.linked_track_ids))) if uv.linked_track_ids else str(primary_track_id) if primary_track_id is not None else ''
            captured_db.add_capture(plate_number='UNREADABLE', display_plate='UNREADABLE (LOW EVIDENCE)', confidence=det_conf, plate_img=uv.best_crop, vehicle_img=uv.best_vehicle_crop, annotated_img=scene_evidence, location='Main Surveillance Feed / Video', source_type='video_upload', is_hotlist_hit=False, hotlist_info=None, blur_score=round(float(first_r.blur_score), 1) if first_r and first_r.blur_score is not None else 0.0, aspect_ratio=round(float(getattr(first_r, 'aspect_ratio', 0.0)), 2) if first_r else 0.0, det_confidence=det_conf, ocr_confidence=0.0, format_type='UNREADABLE', quality_gate_passed=False, quality_reason=uv.review_reason or f'Distant/Low Resolution Plate (<=50% OCR, {len(uv.readings)} frames detected)', evidence_data=evidence_list, track_id=primary_track_id, linked_tracks=linked_tracks_str, vehicle_id=uv.vehicle_id, district=district, operator_id=operator_id, operator_username=operator_username, station=station)
        total_verified = len(verified_serialized)
        total_review = len(needs_review_serialized)
        total_unreadable = len(unreadable_serialized)
        diagnostic_notice = None
        if total_verified == 0 and total_review == 0:
            crops_eval = final_data['stats'].get('crops_evaluated', 0)
            diagnostic_notice = f'0 fully readable plates confirmed in this video. {crops_eval} crops evaluated. {total_unreadable} vehicle(s) logged as UNREADABLE (LOW EVIDENCE) in Captured DB with complete visual evidence preserved.'
        p_state['progress'] = 98.0
        p_state['results'] = {'verified_vehicles': verified_serialized, 'needs_review': needs_review_serialized, 'unreadable_vehicles': unreadable_serialized, 'stats': final_data['stats'], 'annotated_video_url': f'/outputs/{annotated_video_filename}' if annotated_video_filename else None, 'annotated_video_filename': annotated_video_filename, 'download_url': f'/api/download/annotated-video/{annotated_video_filename}' if annotated_video_filename else None, 'diagnostic_notice': diagnostic_notice}
        cleanup_file_safely(video_path)
    except Exception as e:
        print(f'[Processing Error]: {e}')
        p_state['results'] = {'error': str(e)}
    finally:
        if video_writer is not None:
            video_writer.release()
        cleanup_file_safely(video_path)
        p_state['progress'] = 100.0
        p_state['is_processing'] = False

@app.get('/login', response_class=HTMLResponse)
def get_login_page(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse(url='/', status_code=302)
    login_file = os.path.join(STATIC_DIR, 'login.html')
    if os.path.exists(login_file):
        with open(login_file, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse('<h1>Login Page Not Found</h1>')

@app.post('/api/auth/login')
async def auth_login(request: Request, response: Response):
    content_type = request.headers.get('content-type', '')
    username = None
    password = None
    if 'application/json' in content_type:
        try:
            body = await request.json()
            username = body.get('username')
            password = body.get('password')
        except Exception:
            pass
    if not username or not password:
        form = await request.form()
        username = form.get('username')
        password = form.get('password')
    if not username or not password:
        raise HTTPException(status_code=400, detail='Username and password are required.')
    user = auth_db.authenticate(str(username).strip(), str(password))
    if not user:
        raise HTTPException(status_code=401, detail='Invalid username or password.')
    token = uuid.uuid4().hex
    ACTIVE_SESSIONS[token] = user
    auth_db.save_session(token, user)
    response.set_cookie(key='hp_surveillance_session', value=token, httponly=True, samesite='lax', path='/', max_age=86400 * 7)
    return {'success': True, 'user': user, 'token': token}

@app.post('/api/auth/logout')
async def auth_logout(request: Request, response: Response):
    user = get_current_user_optional(request)
    if user:
        uname = (user.get('username') or '').lower().strip()
        with _user_stream_lock:
            if uname in user_stream_managers:
                user_stream_managers[uname].stop_all()
    token = request.cookies.get('hp_surveillance_session')
    if token:
        if token in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[token]
        auth_db.delete_session(token)
    response.delete_cookie('hp_surveillance_session', path='/')
    return {'success': True, 'message': 'Logged out successfully.'}

@app.get('/api/auth/me')
def auth_me(request: Request):
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required. Please log in.')
    return user

@app.get('/api/users/list')
def list_officers(request: Request):
    user = get_current_user_optional(request)
    if not user:
        user = auth_db.get_user_by_username('stateadmin')
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required.')
    role = user.get('role', 'OPERATOR')
    district = user.get('district', 'Panipat')
    users = auth_db.list_users(requesting_role=role, requesting_district=district)
    return {'success': True, 'users': users, 'viewer_role': role, 'viewer_district': district}

@app.post('/api/users/create')
async def create_officer_account(request: Request):
    current_user = get_current_user_optional(request)
    if not current_user:
        raise HTTPException(status_code=401, detail='Authentication required.')
    content_type = request.headers.get('content-type', '')
    data = {}
    if 'application/json' in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = dict(form)
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    full_name = str(data.get('full_name', '')).strip()
    belt_number = str(data.get('belt_number', '')).strip()
    role = str(data.get('role', '')).strip()
    district = str(data.get('district', '')).strip()
    station = str(data.get('station', 'General Duty')).strip()
    if not all([username, password, full_name, belt_number, role, district]):
        raise HTTPException(status_code=400, detail='All officer profile fields are required.')
    req_role = current_user.get('role')
    req_district = current_user.get('district')
    if req_role in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
        pass
    elif req_role == 'DISTRICT_ADMIN':
        if role != 'OPERATOR':
            raise HTTPException(status_code=403, detail='District Admin can only create Operator accounts.')
        if district != req_district:
            raise HTTPException(status_code=403, detail=f'District Admin can only create accounts for {req_district}.')
    else:
        raise HTTPException(status_code=403, detail='Operators are not authorized to create accounts.')
    try:
        new_user = auth_db.create_user(username=username, password=password, full_name=full_name, belt_number=belt_number, role=role, district=district, station=station or 'General Duty', created_by_user=current_user.get('username', 'admin'))
        try:
            client_ip = request.client.host if request.client else '127.0.0.1'
            audit_db.log_db_change(action_type='ADD', target_type='USER_ACCOUNT', entity_identifier=username, officer_name=current_user.get('full_name', 'Admin'), officer_belt_number=current_user.get('belt_number', ''), officer_district=current_user.get('district', 'State HQ'), officer_role=req_role, new_data={'username': username, 'role': role, 'district': district, 'full_name': full_name}, reason=f"Account created by {current_user.get('username')}", workstation_ip=client_ip)
        except Exception as audit_err:
            logger.warning(f'Failed to log audit for user creation {username}: {audit_err}')
        return {'success': True, 'user': new_user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f'Error creating officer user {username}: {e}')
        raise HTTPException(status_code=400, detail=f'Failed to create account: {str(e)}')

@app.post('/api/users/reset-password')
async def reset_officer_password(request: Request):
    current_user = get_current_user_optional(request)
    if not current_user:
        raise HTTPException(status_code=401, detail='Authentication required.')
    content_type = request.headers.get('content-type', '')
    data = {}
    if 'application/json' in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = dict(form)
    user_id = data.get('user_id')
    target_username = data.get('target_username')
    new_password = data.get('new_password')
    if not new_password:
        raise HTTPException(status_code=400, detail='New password is required.')
    if not user_id and target_username:
        target_obj = auth_db.get_user_by_username(str(target_username).strip())
        if not target_obj:
            raise HTTPException(status_code=404, detail=f"Officer '{target_username}' not found.")
        user_id = target_obj.get('user_id') or target_obj.get('id')
    elif user_id:
        user_id = int(user_id)
    else:
        raise HTTPException(status_code=400, detail='Target user identifier is required.')
    try:
        auth_db.reset_password(target_user_id=user_id, new_password=new_password, requesting_user=current_user)
        target = auth_db.get_user_by_id(user_id)
        client_ip = request.client.host if request.client else '127.0.0.1'
        audit_db.log_db_change(action_type='EDIT', target_type='USER_PASSWORD', entity_identifier=target.get('username', str(user_id)) if target else str(user_id), officer_name=current_user.get('full_name', 'Admin'), officer_belt_number=current_user.get('belt_number', ''), officer_district=current_user.get('district', 'State HQ'), officer_role=current_user.get('role', 'ADMIN'), reason='Administrative password reset', workstation_ip=client_ip)
        return {'success': True, 'message': 'Password reset successfully.'}
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 400, detail=str(e))

@app.get('/api/auth/scope-filters')
def get_scope_filters(request: Request):
    """



    Returns valid district and operator filter options for the current logged-in user



    to populate multi-tenant filter dropdowns in database drawers and master trail views.



    """
    user = get_current_user_optional(request)
    if not user:
        user = auth_db.get_user_by_username('op_5421') or {'role': 'OPERATOR', 'district': 'Panipat', 'username': 'op_5421'}
    role = user.get('role', 'OPERATOR')
    user_dist = user.get('district', 'Panipat')
    user_uname = user.get('username', 'op_5421')
    conn = auth_db._get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT district FROM users WHERE district IS NOT NULL AND district != ''")
        districts_in_db = [r['district'] for r in cursor.fetchall() if r['district'] != 'All Haryana (State HQ)']
        cursor.execute('SELECT username, full_name, district, role FROM users WHERE is_active = 1')
        all_users = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    if 'Panipat' not in districts_in_db:
        districts_in_db.append('Panipat')
    if role in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
        allowed_districts = ['ALL'] + sorted(list(set(districts_in_db)))
        allowed_operators = [{'username': 'ALL', 'label': 'All Operators', 'district': 'ALL'}]
        for u in all_users:
            if u['role'] in ['OPERATOR', 'DISTRICT_ADMIN']:
                allowed_operators.append({'username': u['username'], 'label': f"{u['username']} ({u['full_name']} - {u['district']})", 'district': u['district']})
        return {'role': role, 'districts': allowed_districts, 'operators': allowed_operators, 'selected_district': 'ALL', 'selected_operator': 'ALL'}
    elif role == 'DISTRICT_ADMIN':
        allowed_districts = [user_dist]
        allowed_operators = [{'username': 'ALL', 'label': f'All {user_dist} Operators', 'district': user_dist}]
        for u in all_users:
            if u['district'].lower() == user_dist.lower() and u['role'] == 'OPERATOR':
                allowed_operators.append({'username': u['username'], 'label': f"{u['username']} ({u['full_name']})", 'district': user_dist})
        return {'role': role, 'districts': allowed_districts, 'operators': allowed_operators, 'selected_district': user_dist, 'selected_operator': 'ALL'}
    else:
        return {'role': role, 'districts': [user_dist], 'operators': [{'username': user_uname, 'label': f'My Entries ({user_uname})', 'district': user_dist}], 'selected_district': user_dist, 'selected_operator': user_uname}

@app.get('/api/system/ocr-diagnostics')
def api_get_ocr_diagnostics():
    """Live diagnostic endpoint to verify Awiros and fallback OCR health on server."""
    import subprocess
    from datetime import datetime
    from config import AWIROS_WEIGHTS_PATH, AWIROS_DICT_PATH, AWIROS_PADDLEOCR_DIR, DEFAULT_AWIROS_PYTHON
    w_path = str(AWIROS_WEIGHTS_PATH)
    d_path = str(AWIROS_DICT_PATH)
    p_path = str(AWIROS_PADDLEOCR_DIR)
    w_exists = os.path.isfile(w_path)
    w_size = os.path.getsize(w_path) if w_exists else 0
    d_exists = os.path.isfile(d_path)
    d_size = os.path.getsize(d_path) if d_exists else 0
    p_exists = os.path.isdir(p_path)
    paddle_status = 'missing'
    try:
        import paddle
        paddle_status = f"installed (v{getattr(paddle, '__version__', 'unknown')})"
    except Exception as e:
        paddle_status = f'not available: {e}'
    safetensors_status = 'missing'
    try:
        import safetensors
        safetensors_status = 'installed'
    except Exception as e:
        safetensors_status = f'not available: {e}'
    easyocr_status = 'missing'
    try:
        import easyocr
        easyocr_status = 'installed'
    except Exception as e:
        easyocr_status = f'not available: {e}'
    test_result = {}
    try:
        p = get_upload_pipeline(request=None)
        if p and p.anpr and p.anpr.ocr_engine:
            eng = p.anpr.ocr_engine
            test_crop = np.full((60, 240, 3), 255, dtype=np.uint8)
            cv2.putText(test_crop, 'HR26DK8337', (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
            txt, conf = eng.read_text(test_crop)
            test_result = {'detected_text': txt, 'confidence': round(conf * 100, 1), 'active_strategy': eng.last_ocr_diagnostics.get('selected_strategy', 'unknown'), 'awiros_client_ready': getattr(eng.awiros_client, 'ready', False) if eng.awiros_client else False, 'awiros_last_error': getattr(eng.awiros_client, 'last_error', None) if eng.awiros_client else None}
    except Exception as e:
        test_result = {'error': str(e)}
    return {'status': 'healthy' if test_result.get('detected_text') else 'degraded', 'timestamp': datetime.now().isoformat(), 'active_python': sys.executable, 'awiros_configured_python': DEFAULT_AWIROS_PYTHON, 'files': {'weights_file': {'path': w_path, 'exists': w_exists, 'size_mb': round(w_size / (1024 * 1024), 2)}, 'dict_file': {'path': d_path, 'exists': d_exists, 'size_bytes': d_size}, 'paddleocr_dir': {'path': p_path, 'exists': p_exists}}, 'dependencies': {'paddlepaddle': paddle_status, 'safetensors': safetensors_status, 'easyocr': easyocr_status}, 'test_reading': test_result}

@app.get('/api/benchmark')
def api_get_benchmark(refresh: bool=False):
    from src.benchmarks.benchmark_service import run_unified_benchmark, get_benchmark_recommendations, get_hardware_info
    results = run_unified_benchmark(force_refresh=refresh)
    recs = get_benchmark_recommendations(results)
    hw = get_hardware_info()
    return JSONResponse(content={'success': True, 'results': results, 'recommendations': recs, 'hardware': hw})

@app.get('/api/investigation/history')
def get_investigation_history(request: Request, limit: int=50):
    user = get_current_user_optional(request)
    role = user.get('role', 'STATE_ADMIN') if user else 'STATE_ADMIN'
    district = user.get('district', 'Panipat') if user else 'Panipat'
    searches = investigation_db.list_searches(requesting_role=role, requesting_district=district, limit=limit)
    return {'success': True, 'searches': searches, 'count': len(searches)}

@app.get('/api/investigation/history/{search_id}')
def get_investigation_search_details(search_id: str):
    search = investigation_db.get_search_by_id(search_id)
    if not search:
        raise HTTPException(status_code=404, detail='Investigation record not found.')
    return {'success': True, 'search': search}

@app.delete('/api/investigation/history/clear')
def clear_investigation_history(request: Request):
    user = get_current_user_optional(request)
    role = user.get('role', 'STATE_ADMIN') if user else 'STATE_ADMIN'
    district = user.get('district', 'Panipat') if user else 'Panipat'
    investigation_db.clear_searches(requesting_role=role, requesting_district=district)
    return {'success': True, 'message': 'Investigation search history cleared.'}

@app.get('/api/unified/sessions')
def get_unified_sessions(request: Request, district: Optional[str]=None, operator: Optional[str]=None, limit: int=50):
    """Lists grouped upload and analysis sessions respecting Haryana Police RBAC hierarchy."""
    user = get_current_user_optional(request)
    eff_user = user or {'role': 'STATE_ADMIN', 'district': 'Panipat', 'username': 'admin'}
    target_dist, target_op = resolve_rbac_filters(eff_user, district, operator)
    role = eff_user.get('role', 'STATE_ADMIN')
    sessions = investigation_db.list_sessions(requesting_role=role, requesting_district=target_dist, requesting_operator=target_op, limit=limit)
    return {'success': True, 'sessions': sessions, 'count': len(sessions), 'user_role': role, 'scoped_district': target_dist or 'All Haryana (Statewide)', 'scoped_operator': target_op or 'All Operators'}

@app.post('/api/unified/sessions')
async def create_unified_session(request: Request):
    """Creates a new grouped upload and analysis session from completed batch/single uploads."""
    user = get_current_user_optional(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if user:
        body.setdefault('username', user.get('username', 'Unknown'))
        body.setdefault('officer_name', user.get('full_name') or user.get('username', 'Duty Officer'))
        body.setdefault('belt_number', user.get('belt_number', '--'))
        body.setdefault('district', user.get('district', 'Panipat'))
        body.setdefault('station', user.get('station') or user.get('police_station') or 'General Post')
        body.setdefault('role', user.get('role', 'OPERATOR'))
    res = investigation_db.add_session(body)
    return {'success': True, 'session_id': res.get('session_id')}

@app.get('/api/unified/sessions/{session_id}')
def get_unified_session_by_id(session_id: str, request: Request):
    """Fetches details of a specific upload and analysis session with RBAC verification."""
    user = get_current_user_optional(request)
    sess = investigation_db.get_session_by_id(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail='Upload session not found.')
    if user:
        role = str(user.get('role', 'OPERATOR')).upper().strip()
        u_dist = str(user.get('district', 'Panipat')).strip()
        u_name = str(user.get('username', '')).strip().lower()
        if role not in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
            sess_dist = str(sess.get('district') or '').strip().lower()
            if role == 'DISTRICT_ADMIN' and sess_dist != u_dist.lower():
                raise HTTPException(status_code=403, detail='Access denied: Session belongs to another district.')
            elif role == 'OPERATOR':
                sess_user = str(sess.get('username') or '').strip().lower()
                if sess_dist != u_dist.lower() or (sess_user and sess_user != u_name):
                    raise HTTPException(status_code=403, detail='Access denied: Session belongs to another operator.')
    return {'success': True, 'session': sess}

@app.delete('/api/unified/sessions/{session_id}')
def delete_unified_session(session_id: str, request: Request):
    """Deletes an upload session record with RBAC protection."""
    user = get_current_user_optional(request)
    sess = investigation_db.get_session_by_id(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail='Upload session not found.')
    if user:
        role = str(user.get('role', 'OPERATOR')).upper().strip()
        u_dist = str(user.get('district', 'Panipat')).strip()
        u_name = str(user.get('username', '')).strip().lower()
        if role not in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
            sess_dist = str(sess.get('district') or '').strip().lower()
            if role == 'DISTRICT_ADMIN' and sess_dist != u_dist.lower():
                raise HTTPException(status_code=403, detail='Access denied: Cannot delete sessions from other districts.')
            elif role == 'OPERATOR':
                sess_user = str(sess.get('username') or '').strip().lower()
                if sess_dist != u_dist.lower() or (sess_user and sess_user != u_name):
                    raise HTTPException(status_code=403, detail='Access denied: You can only delete your own sessions.')
    ok = investigation_db.delete_session(session_id)
    return {'success': ok}

@app.get('/', response_class=HTMLResponse)
def get_dashboard(request: Request):
    user = get_current_user_optional(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    index_file = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(index_file):
        with open(index_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return HTMLResponse(content=content, headers={'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache', 'Expires': '0'})
    return '<h1>ANPR System API Running</h1><p>Static index.html not found.</p>'

@app.post('/api/upload')
async def upload_video(request: Request, background_tasks: BackgroundTasks, file: UploadFile=File(...), fps: int=Form(5), save_annotated_video: str=Form('true')):
    save_annotated = str(save_annotated_video).strip().lower() in ('true', '1', 'yes', 'on')
    user = get_current_user_optional(request)
    username = user.get('username', 'op_5421') if user else 'op_5421'
    district = user.get('district', 'Panipat') if user else 'Panipat'
    op_id = user.get('id') if user else None
    station = user.get('station', 'PHQ') if user else 'PHQ'
    temp_path = os.path.join(OUTPUTS_DIR, file.filename)
    with open(temp_path, 'wb') as f:
        f.write(await file.read())
    background_tasks.add_task(run_video_processing, temp_path, fps, operator_username=username, district=district, operator_id=op_id, station=station, save_annotated=save_annotated)
    return {'status': 'started', 'filename': file.filename, 'operator': username}

@app.post('/api/upload_image')
def upload_image(request: Request, file: UploadFile=File(...)):
    user = get_current_user_optional(request)
    username = user.get('username', 'op_5421') if user else 'op_5421'
    district = user.get('district', 'Panipat') if user else 'Panipat'
    op_id = user.get('id') if user else None
    station = user.get('station', 'PHQ') if user else 'PHQ'
    p_state = get_user_pipeline_state(username)
    p_state['is_processing'] = True
    p_state['progress'] = 0.0
    contents = file.file.read()
    try:
        file.file.close()
    except Exception:
        pass
    if not contents or len(contents) == 0:
        p_state['is_processing'] = False
        raise HTTPException(status_code=400, detail='Uploaded file is empty (0 bytes). Please upload a valid image.')
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        p_state['is_processing'] = False
        raise HTTPException(status_code=400, detail='Invalid image file or unsupported image format.')
    frame_h, frame_w = image.shape[:2]
    pipeline = get_upload_anpr_pipeline()
    pipeline.reset_state()
    annotated = image.copy()
    active_displays = pipeline.process_frame(image, frame_idx=1, timestamp=0.0, is_photo=True)
    pipeline.drain_ocr_queue(timeout=30.0)
    results_list = []
    for ad in active_displays:
        vx1, vy1, vx2, vy2 = ad['bbox']
        tid = ad.get('track_id', 1)
        cls_name = ad.get('cls_name', 'Vehicle').capitalize()
        veh_color = (255, 140, 0)
        cv2.rectangle(annotated, (vx1, vy1), (vx2, vy2), veh_color, 3)
        veh_lbl = f'Vehicle: {cls_name}'
        (vtw, vth), _ = cv2.getTextSize(veh_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        cv2.rectangle(annotated, (vx1, max(0, vy1 - vth - 8)), (vx1 + vtw + 8, vy1), veh_color, -1)
        cv2.putText(annotated, veh_lbl, (vx1 + 4, max(vth + 2, vy1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        pbox = ad.get('plate_bbox')
        if pbox is not None:
            px1, py1, px2, py2 = pbox
            p_crop = image[py1:py2, px1:px2]
            pw, ph = (px2 - px1, py2 - py1)
            aspect_ratio = round(pw / float(max(1, ph)), 2)
            v_rec = pipeline.track_merger.vehicles.get(ad['vehicle_id'])
            reading = v_rec.readings[-1] if v_rec and v_rec.readings else None
            if reading and reading.ocr_confidence >= 0.2 and (reading.normalized_text != 'UNREADABLE'):
                is_valid_fmt, fmt_type, norm_plate = pipeline.normalizer.validate(reading.normalized_text)
                display_plate = pipeline.normalizer.format_display(norm_plate)
                conf_pct = round(float(reading.ocr_confidence) * 100, 1)
                is_verified = conf_pct > 50.0 and is_valid_fmt
                plate_color = (16, 185, 129) if is_verified else (245, 158, 11)
                cv2.rectangle(annotated, (px1, py1), (px2, py2), plate_color, 3)
                plate_lbl = f'Plate: {display_plate} ({conf_pct}%)'
                (ptw, pth), _ = cv2.getTextSize(plate_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                cv2.rectangle(annotated, (px1, max(0, py1 - pth - 8)), (px1 + ptw + 8, py1), plate_color, -1)
                cv2.putText(annotated, plate_lbl, (px1 + 4, max(pth + 2, py1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
                db_match = vehicle_db.match_plate(norm_plate) if norm_plate else None
                hotlist_info_str = format_hotlist_info(db_match)
                v_crop = image[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)]
                scene_evidence = getattr(reading, 'annotated_frame', None)
                if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                    scene_evidence = annotated
                diag = PlateEnhancer.get_preprocessing_diagnostics(p_crop)
                enhanced_crop = diag.get('enhanced_image')
                prep_meta = {'raw_angle': diag.get('raw_angle', 0.0), 'is_deskewed': diag.get('is_deskewed', False), 'corrected_angle': diag.get('corrected_angle', 0.0), 'raw_blur': diag.get('raw_blur', 0.0), 'enhanced_blur': diag.get('enhanced_blur', 0.0)}
                v['captured_id'] = captured_db.add_capture(plate_number=norm_plate, display_plate=display_plate, confidence=conf_pct, plate_img=p_crop, vehicle_img=v_crop, annotated_img=scene_evidence, location='Single Image Inspection', source_type='image_upload', is_hotlist_hit=db_match is not None, hotlist_info=hotlist_info_str, blur_score=round(float(reading.blur_score), 1) if reading.blur_score is not None else 0.0, aspect_ratio=aspect_ratio, det_confidence=round(float(reading.detection_confidence) * 100, 1) if reading.detection_confidence is not None else 0.0, ocr_confidence=conf_pct, format_type=fmt_type, quality_gate_passed=is_verified, quality_reason='Valid plate crop' if is_verified else 'Needs Review (Illegible Numbers)' if fmt_type == 'illegible_numbers' else 'Needs Review (Incomplete Digits)' if fmt_type == 'incomplete_digits' else f'Needs Review ({fmt_type})', evidence_data=[{'frame_idx': 1, 'track_id': 1, 'text': display_plate, 'confidence': conf_pct, 'crop_base64': encode_image_base64(p_crop)}], enhanced_img=enhanced_crop, preprocessing_data=prep_meta, district=district, operator_id=op_id, operator_username=username, station=station, is_traffic_violation=bool(ad.get('is_traffic_violation') or getattr(v_rec, 'is_traffic_violation', False)), violation_type=ad.get('violation_type') or getattr(v_rec, 'violation_type', None), violation_fine=ad.get('violation_fine') or getattr(v_rec, 'violation_fine', 0), violation_id=ad.get('violation_id') or getattr(v_rec, 'violation_id', None), violation_details=ad.get('violation_details') or getattr(v_rec, 'violation_details', None))
                if db_match and is_verified:
                    passage_id = f'img_{int(time.time())}_{norm_plate}'
                    trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=norm_plate, camera_id='CAM-01', location='Image Inspection Station', captured_at=datetime.datetime.now().astimezone().isoformat(), confidence=conf_pct, plate_img=p_crop, vehicle_img=v_crop, passage_id=passage_id, min_cooldown_seconds=3.0, district=district, operator_id=op_id, operator_username=username, station=station)
                if db_match:
                    try:
                        audit_db.create_alert(alert_type='ANPR_HOTLIST', entity_identifier=norm_plate, display_name=display_plate or norm_plate, case_info=hotlist_info_str or 'Watchlist Match', camera_id='UPLOAD-01', camera_location='Single Image Inspection', origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=district, confidence=conf_pct, snapshot_path=encode_image_base64(p_crop) if p_crop is not None else None)
                    except Exception as ae:
                        logger.warning(f'Failed to create audit alert in upload_image: {ae}')
                results_list.append({'bbox': [px1, py1, px2, py2], 'raw_text': reading.raw_text, 'normalized_plate': norm_plate, 'display_plate': display_plate, 'detection_confidence': round(float(reading.detection_confidence) * 100, 1), 'ocr_confidence': round(float(reading.ocr_confidence) * 100, 1), 'blur_score': round(float(reading.blur_score), 1), 'aspect_ratio': aspect_ratio, 'quality_gate_passed': is_verified, 'quality_reason': 'Valid plate crop' if is_verified else 'Needs Review', 'is_valid_format': is_valid_fmt, 'format_type': reading.format_type, 'crop_base64': encode_image_base64(p_crop), 'enhanced_crop_base64': encode_image_base64(enhanced_crop), 'preprocessing_meta': prep_meta, 'hotlist_match': db_match, 'is_traffic_violation': bool(ad.get('is_traffic_violation') or getattr(v_rec, 'is_traffic_violation', False)), 'violation_type': ad.get('violation_type') or getattr(v_rec, 'violation_type', None), 'violation_fine': ad.get('violation_fine') or getattr(v_rec, 'violation_fine', 0), 'violation_id': ad.get('violation_id') or getattr(v_rec, 'violation_id', None), 'violation_details': ad.get('violation_details') or getattr(v_rec, 'violation_details', None)})
            else:
                det_conf_pct = round(float(reading.detection_confidence) * 100, 1) if reading and reading.detection_confidence is not None else 0.0
                if det_conf_pct > 50.0:
                    plate_color = (148, 163, 184)
                    cv2.rectangle(annotated, (px1, py1), (px2, py2), plate_color, 3)
                    plate_lbl = f'Plate: UNREADABLE ({det_conf_pct}% det)'
                    (ptw, pth), _ = cv2.getTextSize(plate_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                    cv2.rectangle(annotated, (px1, max(0, py1 - pth - 8)), (px1 + ptw + 8, py1), plate_color, -1)
                    cv2.putText(annotated, plate_lbl, (px1 + 4, max(pth + 2, py1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
                    v_crop = image[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)]
                    scene_evidence = getattr(reading, 'annotated_frame', None) if reading else None
                    if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                        scene_evidence = annotated
                    captured_db.add_capture(plate_number='UNREADABLE', display_plate='UNREADABLE (LOW EVIDENCE)', confidence=det_conf_pct, plate_img=p_crop, vehicle_img=v_crop, annotated_img=scene_evidence, location='Single Image Inspection', source_type='image_upload', is_hotlist_hit=False, hotlist_info=None, blur_score=round(float(reading.blur_score), 1) if reading and reading.blur_score is not None else 0.0, aspect_ratio=aspect_ratio, det_confidence=det_conf_pct, ocr_confidence=0.0, format_type='UNREADABLE', quality_gate_passed=False, quality_reason='Low Resolution / Unreadable (<40% OCR)', evidence_data=[{'frame_idx': 1, 'track_id': 1, 'text': 'UNREADABLE', 'confidence': det_conf_pct, 'crop_base64': encode_image_base64(p_crop)}], district=district, operator_id=op_id, operator_username=username, station=station)
                    results_list.append({'bbox': [px1, py1, px2, py2], 'raw_text': 'UNREADABLE', 'normalized_plate': 'UNREADABLE', 'display_plate': 'UNREADABLE (LOW EVIDENCE)', 'detection_confidence': det_conf_pct, 'ocr_confidence': 0.0, 'blur_score': round(float(reading.blur_score), 1) if reading and reading.blur_score is not None else 0.0, 'aspect_ratio': aspect_ratio, 'quality_gate_passed': False, 'quality_reason': 'Low Resolution / Unreadable (<40% OCR)', 'is_valid_format': False, 'format_type': 'UNREADABLE', 'crop_base64': encode_image_base64(p_crop), 'hotlist_match': None})
    annotated_photo_filename = f'annotated_photo_{int(time.time() * 1000)}.jpg'
    annotated_photo_path = os.path.join(OUTPUTS_DIR, annotated_photo_filename)
    cv2.imwrite(annotated_photo_path, annotated)
    final_data = pipeline.finalize(is_single_image=True)
    verified_serialized = [serialize_vehicle(v) for v in final_data['verified_vehicles']]
    needs_review_serialized = [serialize_vehicle(v) for v in final_data['needs_review']]
    unreadable_serialized = [serialize_vehicle(v) for v in final_data.get('unreadable_vehicles', [])]
    p_state['results'] = {'verified_vehicles': verified_serialized, 'needs_review': needs_review_serialized, 'unreadable_vehicles': unreadable_serialized, 'stats': final_data['stats'], 'annotated_photo_url': f'/outputs/{annotated_photo_filename}', 'annotated_photo_filename': annotated_photo_filename, 'download_url': f'/api/download/annotated-photo/{annotated_photo_filename}'}
    p_state['is_processing'] = False
    p_state['progress'] = 100.0
    return {'status': 'success', 'detections_count': len(results_list), 'detections': results_list, 'annotated_image_base64': encode_image_base64(annotated), 'annotated_photo_url': f'/outputs/{annotated_photo_filename}', 'annotated_photo_filename': annotated_photo_filename, 'download_url': f'/api/download/annotated-photo/{annotated_photo_filename}', 'pipeline_results': p_state['results']}

@app.get('/api/download/annotated-video/{filename}')
def download_annotated_video(filename: str):
    clean_filename = os.path.basename(filename)
    file_path = os.path.join(OUTPUTS_DIR, clean_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail='Annotated video file not found')
    return FileResponse(file_path, media_type='video/mp4', filename=clean_filename, headers={'Content-Disposition': f'attachment; filename="{clean_filename}"'})

@app.get('/api/download/annotated-photo/{filename}')
def download_annotated_photo(filename: str):
    clean_filename = os.path.basename(filename)
    file_path = os.path.join(OUTPUTS_DIR, clean_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail='Annotated photo file not found')
    return FileResponse(file_path, media_type='image/jpeg', filename=clean_filename, headers={'Content-Disposition': f'attachment; filename="{clean_filename}"'})

@app.post('/api/run_demo')
async def run_demo(request: Request, background_tasks: BackgroundTasks):
    user = get_current_user_optional(request)
    username = user.get('username', 'op_5421') if user else 'op_5421'
    district = user.get('district', 'Panipat') if user else 'Panipat'
    op_id = user.get('id') if user else None
    station = user.get('station', 'PHQ') if user else 'PHQ'
    demo_path = os.path.join(OUTPUTS_DIR, 'demo_anpr.mp4')
    if not os.path.exists(demo_path):
        create_sample_demo_video(demo_path)
    background_tasks.add_task(run_video_processing, demo_path, 5, operator_username=username, district=district, operator_id=op_id, station=station)
    return {'status': 'started', 'source': 'demo_anpr.mp4', 'operator': username}

@app.get('/api/status')
def get_status(request: Request):
    user = get_current_user_optional(request)
    username = user.get('username', 'op_5421') if user else 'op_5421'
    p_state = get_user_pipeline_state(username)
    return {'is_processing': p_state['is_processing'], 'progress': p_state['progress'], 'current_frame': p_state['current_frame'], 'total_frames': p_state['total_frames'], 'has_results': p_state['results'] is not None}

@app.get('/api/results')
def get_results(request: Request):
    user = get_current_user_optional(request)
    if not user:
        return JSONResponse({'status': 'no_results_yet'}, status_code=200)
    username = str(user.get('username', '')).strip().lower()
    p_state = get_user_pipeline_state(username)
    if p_state['results'] is None:
        return JSONResponse({'status': 'no_results_yet'}, status_code=200)
    return p_state['results']

@app.post('/api/vehicles')
async def add_vehicle_to_db(request: Request, vehicle_number: Optional[str]=Form('UNKNOWN'), vehicle_type: Optional[str]=Form('Other'), vehicle_color: Optional[str]=Form('Unknown'), involved_in_case: Optional[str]=Form('no'), manual_location: Optional[str]=Form(None), offence_type: Optional[str]=Form(None), fir_number: Optional[str]=Form(None), police_station: Optional[str]=Form(None), io_number: Optional[str]=Form(None), case_summary: Optional[str]=Form(None), lost_location: Optional[str]=Form(None), lost_details: Optional[str]=Form(None), district_name: Optional[str]=Form('All Haryana'), created_by_officer: Optional[str]=Form('Duty Officer'), owner_name: Optional[str]=Form(None), owner_father_name: Optional[str]=Form(None), owner_mobile: Optional[str]=Form(None), owner_address: Optional[str]=Form(None), photo: Optional[UploadFile]=File(None)):
    eff_vnum = (vehicle_number or '').strip().upper() or 'UNKNOWN'
    eff_vtype = (vehicle_type or '').strip() or 'Other'
    eff_vcol = (vehicle_color or '').strip() or 'Unknown'
    is_case = (involved_in_case or '').strip().lower() in ('yes', 'true', '1')
    photo_bytes = None
    photo_filename = None
    if photo and photo.filename:
        photo_bytes = await photo.read()
        photo_filename = photo.filename
    curr_u = get_current_user_optional(request) or {}
    eff_district = district_name or 'All Haryana'
    if curr_u.get('role') in ['DISTRICT_ADMIN', 'OPERATOR'] and curr_u.get('district'):
        eff_district = curr_u.get('district')
    eff_officer = curr_u.get('full_name') or created_by_officer or 'Duty Officer'
    new_id = vehicle_db.add_vehicle(vehicle_number=eff_vnum, vehicle_type=eff_vtype, vehicle_color=eff_vcol, involved_in_case=is_case, manual_location=manual_location, offence_type=offence_type, fir_number=fir_number, police_station=police_station, io_number=io_number, case_summary=case_summary, lost_location=lost_location, lost_details=lost_details, district_name=eff_district, created_by_officer=eff_officer, owner_name=owner_name, owner_father_name=owner_father_name, owner_mobile=owner_mobile, owner_address=owner_address, photo_bytes=photo_bytes, photo_filename=photo_filename)
    created = vehicle_db.get_by_id(new_id)
    try:
        curr_u = get_current_user_optional(request) or {}
        client_ip = request.client.host if request.client else '127.0.0.1'
        audit_db.log_db_change(action_type='ADD', target_type='VEHICLE_DB', entity_identifier=eff_vnum, officer_name=curr_u.get('full_name') or created_by_officer or 'Duty Officer', officer_belt_number=curr_u.get('belt_number', ''), officer_district=district_name or curr_u.get('district', 'All Haryana'), officer_role=curr_u.get('role', 'OPERATOR'), new_data={'vehicle_number': eff_vnum, 'district': district_name, 'fir': fir_number, 'owner': owner_name, 'mobile': owner_mobile}, reason=f"Hotlist entry: {case_summary or offence_type or 'Police Watchlist'}", workstation_ip=client_ip)
    except Exception as e:
        logger.warning(f'Audit log error on vehicle add: {e}')
    return {'status': 'success', 'vehicle': created}

@app.get('/api/vehicles')
def get_vehicles(search: Optional[str]=None, filter: Optional[str]=None, district: Optional[str]=None):
    vehicles = vehicle_db.get_all(search_query=search, filter_type=filter, district=district)
    return {'status': 'success', 'total': len(vehicles), 'vehicles': vehicles}

@app.get('/api/vehicles/search-full')
def search_vehicles_full(q: str=Query(..., description='Plate number or Tracking ID')):
    """



    Unified forensic search endpoint for captured vehicles across video uploads and live streams.



    Queries captured_db by plate number, track_id, vehicle_id, or linked_tracks.



    Also queries vehicle_db (watchlist/hotlist) and vehicle_trail (transit history).



    """
    if not q or not q.strip():
        return {'success': True, 'query': q, 'total_matches': 0, 'results': []}
    search_query = q.strip()
    captures = captured_db.search_full(search_query)
    enriched_results = []
    for cap in captures:
        plate = cap.get('plate_number')
        hotlist_entry = None
        sighting_trail = []
        if plate and plate != 'UNREADABLE':
            hotlist_entry = vehicle_db.match_plate(plate)
            try:
                conn = trail_db._get_connection()
                cursor = conn.cursor()
                clean_plate = vehicle_db.normalizer.clean_raw_text(plate) if hasattr(vehicle_db, 'normalizer') else plate
                cursor.execute('SELECT * FROM vehicle_sightings WHERE registration_number LIKE ? ORDER BY id DESC LIMIT 50', (f'%{clean_plate}%',))
                sighting_trail = [dict(r) for r in cursor.fetchall()]
                conn.close()
            except Exception as e:
                print(f'[Search Forensics Trail Error]: {e}')
                sighting_trail = []
        ev_frames = cap.get('evidence_frames', []) or []
        enriched_ev_frames = []
        frame_timestamps = []
        for ef in ev_frames:
            ts = ef.get('timestamp') or ef.get('video_timestamp')
            f_idx = ef.get('frame_idx')
            if (ts is None or ts == 0.0) and f_idx is not None and (f_idx > 0):
                ts = round(float(f_idx) / 25.0, 2)
            elif ts is not None:
                ts = round(float(ts), 2)
            else:
                ts = 0.0
            time_str = ef.get('time_str') or ef.get('video_time_str') or format_seconds_to_timestamp_str(ts)
            ef_copy = dict(ef)
            ef_copy['timestamp'] = ts
            ef_copy['video_timestamp'] = ts
            ef_copy['time_str'] = time_str
            ef_copy['video_time_str'] = time_str
            enriched_ev_frames.append(ef_copy)
            if ts > 0:
                frame_timestamps.append(ts)
        first_time_sec = min(frame_timestamps) if frame_timestamps else None
        last_time_sec = max(frame_timestamps) if frame_timestamps else None
        if first_time_sec is not None and last_time_sec is not None:
            first_str = format_seconds_to_timestamp_str(first_time_sec)
            last_str = format_seconds_to_timestamp_str(last_time_sec)
            video_window_str = first_str if first_str == last_str else f'{first_str} - {last_str}'
            video_time_str = first_str
        else:
            video_window_str = None
            video_time_str = None
        enriched_results.append({'id': cap.get('id'), 'plate_number': cap.get('plate_number'), 'display_plate': cap.get('display_plate'), 'confidence': cap.get('confidence', 0.0), 'det_confidence': cap.get('det_confidence', 0.0), 'ocr_confidence': cap.get('ocr_confidence', 0.0), 'track_id': cap.get('track_id'), 'linked_tracks': cap.get('linked_tracks'), 'vehicle_id': cap.get('vehicle_id') if cap.get('vehicle_id') is not None else cap.get('track_id'), 'plate_pic_path': cap.get('plate_pic_path'), 'vehicle_pic_path': cap.get('vehicle_pic_path'), 'annotated_pic_path': cap.get('annotated_pic_path'), 'captured_at': cap.get('captured_at'), 'location': cap.get('location'), 'gps_coords': cap.get('gps_coords'), 'clip_name': cap.get('clip_name'), 'source_type': cap.get('source_type'), 'is_hotlist_hit': bool(cap.get('is_hotlist_hit')), 'hotlist_info': cap.get('hotlist_info'), 'quality_gate_passed': bool(cap.get('quality_gate_passed', 1)), 'quality_reason': cap.get('quality_reason'), 'evidence_frames': enriched_ev_frames, 'video_window_str': video_window_str, 'video_time_str': video_time_str, 'first_video_time': first_time_sec, 'last_video_time': last_time_sec, 'hotlist_match': hotlist_entry, 'sighting_trail': sighting_trail})
    if not enriched_results and search_query:
        try:
            conn = trail_db._get_connection()
            cursor = conn.cursor()
            clean_q = vehicle_db.normalizer.clean_raw_text(search_query) if hasattr(vehicle_db, 'normalizer') else search_query
            cursor.execute('SELECT * FROM vehicle_sightings WHERE registration_number LIKE ? ORDER BY captured_epoch ASC LIMIT 50', (f'%{clean_q}%',))
            trail_rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            if trail_rows:
                first_r = trail_rows[0]
                hotlist_entry = vehicle_db.match_plate(first_r.get('registration_number', clean_q))
                for idx, tr in enumerate(trail_rows):
                    enriched_results.append({'id': tr['id'], 'plate_number': tr.get('registration_number', clean_q), 'display_plate': tr.get('display_number', clean_q), 'confidence': tr.get('confidence', 95.0), 'plate_pic_path': tr.get('plate_photo_path'), 'vehicle_pic_path': tr.get('vehicle_photo_path'), 'annotated_pic_path': None, 'captured_at': tr.get('captured_at'), 'location': tr.get('location'), 'gps_coords': tr.get('gps_coords'), 'clip_name': tr.get('camera_id'), 'source_type': 'trail_sighting', 'track_id': idx + 1, 'evidence_frames': [{'frame_idx': (idx + 1) * 35, 'video_time_str': f'0{idx}:15.0s', 'crop_base64': None, 'vehicle_crop_base64': None}], 'hotlist_match': hotlist_entry, 'sighting_trail': trail_rows})
        except Exception as e:
            print(f'[Search Full Fallback Trail Error]: {e}')
    return {'success': True, 'query': search_query, 'total_matches': len(enriched_results), 'results': enriched_results}

@app.get('/api/vehicles/{vehicle_id}')
def get_vehicle_record(vehicle_id: int):
    rec = vehicle_db.get_by_id(vehicle_id)
    if not rec:
        raise HTTPException(status_code=404, detail='Vehicle not found')
    return {'status': 'success', 'vehicle': rec}

@app.delete('/api/vehicles/{vehicle_id}')
def delete_vehicle_record(request: Request, vehicle_id: int, reason: Optional[str]=None):
    current_user = get_current_user_optional(request)
    if not current_user:
        current_user = auth_db.get_user_by_username('stateadmin')
    if current_user and current_user.get('role') == 'OPERATOR':
        raise HTTPException(status_code=403, detail='Duty Operators are not authorized to delete records. Action restricted to District Admin and State Admin.')
    old_rec = vehicle_db.get_by_id(vehicle_id)
    if not old_rec:
        raise HTTPException(status_code=404, detail='Vehicle not found')
    ok = vehicle_db.delete(vehicle_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Vehicle not found or could not be deleted')
    client_ip = request.client.host if request.client else '127.0.0.1'
    audit_db.log_db_change(action_type='DELETE', target_type='VEHICLE_DB', entity_identifier=old_rec.get('vehicle_number', f'ID-{vehicle_id}'), officer_name=current_user.get('full_name', 'Duty Officer'), officer_belt_number=current_user.get('belt_number', ''), officer_district=current_user.get('district', 'State HQ'), officer_role=current_user.get('role', 'ADMIN'), old_data=old_rec, reason=reason or 'Administrative record deletion', workstation_ip=client_ip)
    return {'status': 'success', 'deleted_id': vehicle_id}

@app.get('/api/vehicles/match/{plate}')
def match_vehicle_plate(plate: str):
    match = vehicle_db.match_plate(plate)
    return {'status': 'success', 'matched': match is not None, 'vehicle': match}

@app.get('/api/captured')
@app.get('/api/detections')
def get_recent_captured(request: Request, limit: int=100, offset: int=0, search: Optional[str]=None, hotlist_only: bool=False, district: Optional[str]=None, operator: Optional[str]=None):
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    items = captured_db.get_recent(limit=limit, offset=offset, search=search, hotlist_only=hotlist_only, district=eff_district, operator=eff_operator)
    return {'status': 'success', 'total_count': captured_db.get_total_count(district=eff_district, operator=eff_operator), 'limit': limit, 'offset': offset, 'captured': items, 'detections': items, 'effective_district': eff_district, 'effective_operator': eff_operator}

@app.get('/api/violations')
def api_get_violations(plate: Optional[str]=None, violation_type: Optional[str]=Query(None, alias='type'), limit: int=100, offset: int=0):
    """Returns persistent list of traffic violations (Triple Riding & Helmet) from violations.db."""
    try:
        data = violation_db.get_violations(plate_filter=plate, type_filter=violation_type, limit=limit, offset=offset)
        return {'status': 'success', 'violations': data, 'count': len(data)}
    except Exception as e:
        return {'status': 'error', 'message': str(e), 'violations': []}

@app.get('/api/violations/stats')
def api_get_violation_stats():
    """Returns metric counts for interactive filter cards."""
    try:
        stats = violation_db.get_violation_stats()
        return {'status': 'success', 'stats': stats}
    except Exception as e:
        return {'status': 'error', 'message': str(e), 'stats': {'total': 0, 'triple': 0, 'no_helmet': 0, 'both': 0, 'total_fine': 0}}

@app.post('/api/violations/{viol_id}/update')
async def api_update_violation(viol_id: str, payload: Dict[str, Any]=Body(...)):
    """Updates unhelmeted multiplier, custom sections, and recalculated total penalty."""
    try:
        unhelmeted_count = payload.get('unhelmeted_count', 1)
        applied_sections = payload.get('applied_sections', [])
        total_fine = payload.get('total_fine')
        updated = violation_db.update_violation_penalty(viol_id=viol_id, unhelmeted_count=unhelmeted_count, applied_sections=applied_sections, total_fine=total_fine)
        if not updated:
            raise HTTPException(status_code=404, detail='Violation record not found')
        return {'status': 'success', 'violation': updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/captured/export-pdf')
@app.get('/api/captured-export-pdf')
def export_captured_vehicles_pdf(request: Request, district: Optional[str]=None, operator: Optional[str]=None):
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    pdf_bytes = captured_db.export_pdf(district=eff_district, operator=eff_operator)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename=captured_vehicles_report.pdf'})

@app.get('/api/captured/export-csv')
@app.get('/api/captured-export-csv')
def export_captured_vehicles_csv(request: Request, district: Optional[str]=None, operator: Optional[str]=None):
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    csv_data = captured_db.export_csv(district=eff_district, operator=eff_operator)
    return StreamingResponse(io.StringIO(csv_data), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=captured_vehicles.csv'})

@app.get('/api/captured/{capture_id}')
@app.get('/api/detections/{capture_id}')
def get_captured_detail(capture_id: int):
    item = captured_db.get_by_id(capture_id)
    if not item:
        item = demo_captured_db.get_by_id(capture_id) or prod_captured_db.get_by_id(capture_id)
    if not item:
        raise HTTPException(status_code=404, detail='Capture record not found')
    evidence_frames = []
    if item.get('evidence_json'):
        try:
            evidence_frames = json.loads(item['evidence_json'])
        except Exception:
            pass
    item['evidence_frames'] = evidence_frames
    prep_meta = {}
    if item.get('preprocessing_json'):
        try:
            prep_meta = json.loads(item['preprocessing_json'])
        except Exception:
            pass
    item['preprocessing_meta'] = prep_meta
    return {'status': 'success', 'capture': item, 'detection': item}

@app.delete('/api/captured/{capture_id}')
@app.post('/api/captured/{capture_id}/delete')
@app.delete('/api/detections/{capture_id}')
def delete_captured_record(capture_id: int):
    ok = captured_db.delete(capture_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Capture record not found')
    return {'status': 'success', 'deleted_id': capture_id}

@app.delete('/api/captured')
@app.post('/api/captured/clear')
@app.delete('/api/detections')
def clear_all_captured():
    captured_db.clear_all()
    return {'status': 'success', 'cleared': True}

@app.get('/api/trails')
def get_vehicle_trails(request: Request, search: Optional[str]=None, district: Optional[str]=None, operator: Optional[str]=None):
    """



    Returns summary list of all tracked vehicles having recorded sightings:



    sighting_count, last_seen_location, last_seen_camera, last_seen_time,



    and associated vehicle details from Vehicle DB. Filtered by RBAC district & operator.



    """
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    summaries = trail_db.get_vehicle_trails_summary(search=search, district=eff_district, operator=eff_operator)
    enriched = []
    for s in summaries:
        v_info = vehicle_db.get_by_id(s['vehicle_id'])
        item = {**s}
        if v_info:
            item['vehicle_type'] = v_info.get('vehicle_type', 'Unknown')
            item['vehicle_color'] = v_info.get('vehicle_color', 'Unknown')
            item['involved_in_case'] = bool(v_info.get('involved_in_case'))
            item['offence_type'] = v_info.get('offence_type')
            item['fir_number'] = v_info.get('fir_number')
            item['police_station'] = v_info.get('police_station')
            item['lost_location'] = v_info.get('lost_location')
            item['vehicle_status'] = v_info.get('status', 'ACTIVE')
            item['db_photo_path'] = v_info.get('photo_path')
        else:
            item['vehicle_type'] = 'Unknown'
            item['vehicle_color'] = 'Unknown'
            item['involved_in_case'] = False
            item['offence_type'] = None
            item['fir_number'] = None
            item['police_station'] = None
            item['lost_location'] = None
            item['vehicle_status'] = 'ACTIVE'
            item['db_photo_path'] = None
        enriched.append(item)
    return {'status': 'success', 'total_vehicles_tracked': len(enriched), 'total_sightings': trail_db.get_total_sightings_count(district=eff_district, operator=eff_operator), 'trails': enriched, 'effective_district': eff_district, 'effective_operator': eff_operator}

@app.get('/api/trails/{vehicle_id}')
def get_vehicle_trail_history(request: Request, vehicle_id: int, start_date: Optional[str]=None, end_date: Optional[str]=None, camera_id: Optional[str]=None, location: Optional[str]=None, order: str='desc', district: Optional[str]=None, operator: Optional[str]=None):
    """



    Returns chronological history of sightings for vehicle_id, with optional



    date range, camera, and location filters.



    """
    v_info = vehicle_db.get_by_id(vehicle_id)
    if not v_info:
        raise HTTPException(status_code=404, detail='Vehicle not found in registry')
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    history = trail_db.get_vehicle_history(vehicle_id=vehicle_id, start_date=start_date, end_date=end_date, camera_id=camera_id, location=location, ascending=order.lower() == 'asc', district=eff_district, operator=eff_operator)
    return {'status': 'success', 'vehicle': v_info, 'sightings_count': len(history), 'history': history}

@app.delete('/api/trails/sightings/{sighting_id}')
def delete_trail_sighting(sighting_id: int):
    ok = trail_db.delete_sighting(sighting_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Sighting not found')
    return {'status': 'success', 'deleted_id': sighting_id}

@app.delete('/api/trails/vehicle/{vehicle_id}')
def delete_entire_vehicle_trail(vehicle_id: int):
    count = trail_db.delete_vehicle_trail(vehicle_id)
    return {'status': 'success', 'vehicle_id': vehicle_id, 'deleted_sightings': count}

@app.delete('/api/trails/plate/{plate_number}')
def delete_vehicle_trail_by_plate(plate_number: str):
    count = trail_db.delete_vehicle_trail_by_plate(plate_number)
    return {'status': 'success', 'plate_number': plate_number, 'deleted_sightings': count}

@app.post('/api/review/confirm')
async def confirm_review_detection(plate_number: str=Form(...), original_plate: Optional[str]=Form(None), camera_id: str=Form('CAM-01'), location: str=Form('Manual Human Verification'), confidence: float=Form(85.0), plate_crop_base64: Optional[str]=Form(None), vehicle_crop_base64: Optional[str]=Form(None), annotated_crop_base64: Optional[str]=Form(None)):
    """



    Human verification endpoint for uncertain 'Needs Review' detections.



    When confirmed/corrected, saves or updates the entry directly in Captured DB.



    Does NOT add the vehicle to Watchlist (vehicle_db).



    If it happens to match an existing vehicle already in Watchlist, records a sighting to Vehicle Trail DB.



    """
    cleaned_plate = trail_db.normalizer.clean_raw_text(plate_number)
    disp_plate = trail_db.normalizer.format_display(cleaned_plate)
    plate_img = None
    if plate_crop_base64:
        try:
            p_data = base64.b64decode(plate_crop_base64)
            nparr = np.frombuffer(p_data, np.uint8)
            plate_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            pass
    vehicle_img = None
    if vehicle_crop_base64:
        try:
            v_data = base64.b64decode(vehicle_crop_base64)
            nparr = np.frombuffer(v_data, np.uint8)
            vehicle_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            pass
    annotated_img = None
    if annotated_crop_base64:
        try:
            a_data = base64.b64decode(annotated_crop_base64)
            nparr = np.frombuffer(a_data, np.uint8)
            annotated_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            pass
    db_match = vehicle_db.match_plate(cleaned_plate)
    hotlist_info_str = None
    if db_match:
        if db_match.get('involved_in_case'):
            hotlist_info_str = f"POLICE CASE: {db_match.get('offence_type', 'Crime')} | FIR: {db_match.get('fir_number', 'N/A')} | PS: {db_match.get('police_station', 'N/A')}"
        else:
            hotlist_info_str = f"LOST VEHICLE: {db_match.get('lost_location', 'Unknown location')}"
    updated = False
    if original_plate:
        cleaned_orig = trail_db.normalizer.clean_raw_text(original_plate)
        if cleaned_orig:
            updated = captured_db.update_plate(cleaned_orig, cleaned_plate, confidence=confidence)
    if not updated:
        best_scene = annotated_img if annotated_img is not None else vehicle_img if vehicle_img is not None else plate_img
        captured_db.add_capture(plate_number=cleaned_plate, display_plate=disp_plate, confidence=round(float(confidence), 1) if confidence > 0 else 90.0, plate_img=plate_img, vehicle_img=vehicle_img, annotated_img=best_scene, location=location or 'Manual Human Gate Review', source_type='human_review', is_hotlist_hit=db_match is not None, hotlist_info=hotlist_info_str, blur_score=100.0, aspect_ratio=3.0, det_confidence=100.0, ocr_confidence=round(float(confidence), 1) if confidence > 0 else 90.0, format_type='human_confirmed', quality_gate_passed=True, quality_reason='Human Review Confirmed')
    sighting_id = None
    trail_appended = False
    if db_match:
        passage_id = f'human_confirm_{int(time.time())}_{cleaned_plate}'
        sighting_id = trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=cleaned_plate, camera_id=camera_id, location=location, captured_at=datetime.datetime.now().astimezone().isoformat(), confidence=confidence, plate_img=plate_img, vehicle_img=vehicle_img, passage_id=passage_id, min_cooldown_seconds=1.0)
        trail_appended = sighting_id is not None
    return {'status': 'success', 'confirmed_plate': cleaned_plate, 'display_plate': disp_plate, 'captured_logged': True, 'is_hotlist_match': db_match is not None, 'matched_vehicle': db_match, 'trail_appended': trail_appended, 'sighting_id': sighting_id}
DISTRICT_GPS_REGISTRY = {'Panipat': {'coords': '29.3909, 76.9635', 'name': 'Panipat NH-44 Toll Plaza Checkpoint'}, 'Hisar': {'coords': '29.1492, 75.7217', 'name': 'Hisar City Surveillance Post'}, 'Ambala': {'coords': '30.3782, 76.7767', 'name': 'Ambala Cantt Grand Trunk Road'}, 'Faridabad': {'coords': '28.4089, 77.3178', 'name': 'Faridabad Border Checkpoint'}, 'Gurugram': {'coords': '28.4595, 77.0266', 'name': 'Gurugram Expressway Cyber Hub'}, 'Panchkula': {'coords': '30.6942, 76.8606', 'name': 'Panchkula Police HQ, Sector 6'}, 'Karnal': {'coords': '29.6857, 76.9905', 'name': 'Karnal Toll Plaza NH-44'}, 'Rohtak': {'coords': '28.8955, 76.6066', 'name': 'Rohtak Bypass Checkpoint'}, 'Sonipat': {'coords': '28.9931, 77.0151', 'name': 'Sonipat GT Road Post'}, 'Yamunanagar': {'coords': '30.1290, 77.2674', 'name': 'Yamunanagar Inter-state Barrier'}, 'Sirsa': {'coords': '29.5349, 75.0290', 'name': 'Sirsa Highway Checkpoint'}, 'Rewari': {'coords': '28.1828, 76.6186', 'name': 'Rewari Bypass Junction'}, 'Kurukshetra': {'coords': '29.9695, 76.8783', 'name': 'Kurukshetra University Post'}, 'Kaithal': {'coords': '29.7999, 76.4002', 'name': 'Kaithal Bypass Gate'}, 'Jind': {'coords': '29.3140, 76.3134', 'name': 'Jind Junction Post'}, 'Jhajjar': {'coords': '28.6083, 76.6566', 'name': 'Jhajjar Border Post'}, 'Fatehabad': {'coords': '29.5146, 75.4542', 'name': 'Fatehabad Highway Gate'}, 'Charkhi Dadri': {'coords': '28.5921, 76.2653', 'name': 'Charkhi Dadri Checkpoint'}, 'Bhiwani': {'coords': '28.7831, 76.1397', 'name': 'Bhiwani Junction Gate'}, 'Palwal': {'coords': '28.1438, 77.3275', 'name': 'Palwal KMP Expressway Toll'}, 'Nuh': {'coords': '28.1090, 77.0163', 'name': 'Nuh Mewat Border Post'}, 'Mahendragarh': {'coords': '28.2797, 76.1517', 'name': 'Narnaul-Mahendragarh Highway'}}
SLOT_GEO_OFFSETS = {'CAM-01': (0.0, 0.0, 'North Gate'), 'CAM-02': (-0.0028, 0.0031, 'South Toll'), 'CAM-03': (0.0019, -0.0025, 'West Lane'), 'CAM-04': (-0.0015, -0.003, 'East Terminal')}

@app.get('/api/geo/auto-detect')
async def auto_detect_gps(request: Request, camera_id: str=''):
    camera = resolve_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=400, detail='Select a registered Karnal camera; browser/IP location is not a camera location.')
    return {'gps_coords': camera_metadata(camera)[2], 'location_name': camera['name'], 'camera_id': camera['id'], 'source': 'karnal_camera_registry'}

@app.post('/api/camera/connect')
async def connect_camera(request: Request, source_type: str=Form('webcam'), source_path: str=Form('0'), camera_id: str=Form('CAM-01'), location: str=Form('Main Surveillance Gate'), gps_coords: Optional[str]=Form(None), custom_video: Optional[UploadFile]=File(None), target_frame: int=Form(1), registered_camera_id: Optional[str]=Form(None)):
    if registered_camera_id:
        selected_camera = resolve_camera(registered_camera_id)
        if not selected_camera:
            raise HTTPException(status_code=400, detail='Unknown Karnal camera ID')
        _, location, gps_coords = camera_metadata(selected_camera)
    "\n\n\n\n    Connects to a live video source (Webcam, RTSP IP camera, HTTP/HTTPS stream, or Demo / Local Video Loop)\n\n\n\n    for a specific camera slot (CAM-01, CAM-02, CAM-03, CAM-04) strictly isolated to the calling user's workspace.\n\n\n\n    "
    cid = camera_id.strip().upper() if camera_id else 'CAM-01'
    user = get_current_user_optional(request)
    mgr = get_user_stream_manager(user)
    user_tag = (user.get('username') if user else 'guest') or 'guest'
    user_tag_clean = re.sub('[^a-zA-Z0-9_.-]', '_', str(user_tag))
    src: Union[int, str] = source_path
    if source_type == 'webcam':
        try:
            src = int(source_path)
        except ValueError:
            src = 0
    elif source_type in ('demo', 'file'):
        if custom_video is not None and getattr(custom_video, 'filename', None):
            loop_dir = os.path.join(OUTPUTS_DIR, 'custom_loops')
            os.makedirs(loop_dir, exist_ok=True)
            try:
                for old_f in os.listdir(loop_dir):
                    if old_f.startswith(f'loop_{user_tag_clean}_{cid}_'):
                        try:
                            os.remove(os.path.join(loop_dir, old_f))
                        except Exception:
                            pass
            except Exception:
                pass
            clean_name = re.sub('[^a-zA-Z0-9_.-]', '_', custom_video.filename)
            dest_path = os.path.join(loop_dir, f'loop_{user_tag_clean}_{cid}_{int(time.time())}_{clean_name}')
            with open(dest_path, 'wb') as f_out:
                while (chunk := (await custom_video.read(1024 * 1024))):
                    f_out.write(chunk)
            src = dest_path
        elif source_path in DEMO_VIDEOS and os.path.isfile(DEMO_VIDEOS[source_path]['path']):
            src = DEMO_VIDEOS[source_path]['path']
        elif source_path and source_path not in ('demo', 'default', 'custom') and os.path.isfile(source_path):
            src = source_path
        else:
            demo_1_path = os.path.join(DEMO_VIDEOS_DIR, 'demo_1.mp4')
            if os.path.exists(demo_1_path):
                src = demo_1_path
            else:
                demo_path = os.path.join(OUTPUTS_DIR, 'demo_anpr.mp4')
                if not os.path.exists(demo_path):
                    create_sample_demo_video(demo_path)
                src = demo_path
    ok = mgr.start_stream(source=src, source_type=source_type, camera_id=cid, location=location, gps_coords=gps_coords, target_frame=target_frame)
    if not ok:
        raise HTTPException(status_code=400, detail=f'Failed to connect {cid} to {source_type} stream: {source_path}')
    return {'status': 'success', 'message': f'Connected {cid} ({source_type}) successfully', 'camera_id': cid, 'stream_info': mgr.get_status(cid)}

@app.get('/api/camera/demo-videos')
def get_camera_demo_videos():
    """Returns the pre-bundled demo video options for the camera connect modal."""
    return {'success': True, 'videos': [{'id': vid_id, 'title': meta['title'], 'default_location': meta['default_location'], 'exists': os.path.isfile(meta['path'])} for vid_id, meta in DEMO_VIDEOS.items()]}

@app.post('/api/camera/disconnect')
def disconnect_camera(request: Request, camera_id: Optional[str]=Form(None)):
    """Disconnects and stops a specific camera stream or CAM-01 for the authenticated user."""
    cid = camera_id.strip().upper() if camera_id else 'CAM-01'
    mgr = get_user_stream_manager(request)
    mgr.stop_stream(cid)
    return {'status': 'success', 'camera_id': cid, 'message': f'{cid} stream disconnected'}

@app.post('/api/camera/disconnect_all')
def disconnect_all_cameras(request: Request):
    """Disconnects all camera streams in the user's grid."""
    mgr = get_user_stream_manager(request)
    mgr.stop_all()
    return {'status': 'success', 'message': 'All camera streams disconnected'}

@app.post('/api/camera/target-frame')
async def set_camera_target_frame(request: Request):
    """Dynamically updates the AI analysis cadence (1 to 20 frames) during live streaming."""
    cid = 'CAM-01'
    target_frame = 1
    content_type = request.headers.get('content-type', '')
    if 'application/json' in content_type:
        try:
            body = await request.json()
            cid = str(body.get('camera_id', 'CAM-01')).strip().upper()
            target_frame = int(body.get('target_frame', 1))
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            cid = str(form.get('camera_id', 'CAM-01')).strip().upper()
            target_frame = int(form.get('target_frame', 1))
        except Exception:
            pass
    mgr = get_user_stream_manager(request)
    new_target = mgr.set_target_frame_interval(target_frame, camera_id=cid)
    return {'status': 'success', 'camera_id': cid, 'target_frame': new_target, 'message': f'Target frame cadence set to every {new_target} consecutive frame(s) on {cid}'}

@app.post('/api/camera/toggle_anpr')
def toggle_anpr_pipeline(request: Request, enabled: bool=Form(...), camera_id: str=Form('CAM-01')):
    """



    Toggles AI ANPR Pipeline ON or OFF on a specific camera stream for the authenticated user.



    When OFF, raw crystal-clear surveillance feed is streamed with zero AI inference latency.



    When ON, real-time detection, tracking, OCR, and DB logging are engaged.



    """
    cid = camera_id.strip().upper() if camera_id else 'CAM-01'
    mgr = get_user_stream_manager(request)
    new_state = mgr.set_anpr_enabled(enabled, camera_id=cid)
    return {'status': 'success', 'camera_id': cid, 'anpr_enabled': new_state, 'mode': 'ANPR ENGAGED' if new_state else 'RAW SURVEILLANCE'}

@app.get('/api/models/catalog')
def get_models_catalog(target: str='live'):
    """Returns available YOLO vehicle and Indian plate models with download & active status for target scope."""
    from src.detection.model_registry import registry
    return registry.get_catalog(target=target)

@app.post('/api/models/rename')
def rename_pipeline_models(payload: Dict[str, str]=Body(...)):
    """Dynamically renames model display names across registry and returns updated catalog."""
    from src.detection.model_registry import registry
    updated = registry.update_model_names(payload)
    return {'status': 'success', 'updated': updated, 'catalog': registry.get_catalog()}

@app.post("/api/models/select")
def select_pipeline_models(
    vehicle_model: Optional[str] = Form(None),
    plate_model: Optional[str] = Form(None),
    person_model: Optional[str] = Form(None),
    ocr_model: Optional[str] = Form(None),
    target: str = Form("live")
):
    """Dynamically selects models for ANPR pipeline."""
    from src.detection.model_registry import registry
    target_clean = "upload" if str(target).strip().lower() == "upload" else "live"

    updated = registry.set_active_models(
        vehicle_id=vehicle_model,
        plate_id=plate_model,
        person_id=person_model,
        ocr_id=ocr_model,
        target=target_clean
    )

    # Apply the registry's approved selection, including the temporary model lock.
    vehicle_model = updated['active_vehicle']
    plate_model = updated['active_plate']
    person_model = updated['active_person']
    ocr_model = updated['active_ocr']

    if target_clean == "live":
        try:
            pipeline = get_anpr_pipeline()
            if vehicle_model:
                pipeline.switch_vehicle_model(vehicle_model)
            if plate_model:
                pipeline.switch_plate_model(plate_model)
            if ocr_model:
                pipeline.switch_ocr_model(ocr_model)
        except Exception as e:
            print(f"[WARN] Error updating live singleton pipeline models: {e}")

        try:
            eff_veh = vehicle_model or person_model
            with _user_stream_lock:
                for mgr in user_stream_managers.values():
                    mgr.switch_pipeline_models(vehicle_model=eff_veh, plate_model=plate_model, ocr_model=ocr_model)
        except Exception as e:
            print(f"[WARN] Error updating live stream manager pipeline models: {e}")
    else:
        try:
            global _upload_anpr_pipeline
            if _upload_anpr_pipeline is not None:
                if vehicle_model:
                    _upload_anpr_pipeline.switch_vehicle_model(vehicle_model)
                if plate_model:
                    _upload_anpr_pipeline.switch_plate_model(plate_model)
                if ocr_model:
                    _upload_anpr_pipeline.switch_ocr_model(ocr_model)
        except Exception as e:
            print(f"[WARN] Error updating upload pipeline models: {e}")

    return {
        "status": "success",
        "message": f"AI Pipeline models for '{target_clean.upper()}' updated successfully",
        **updated
    }

@app.post('/api/models/revert')
def revert_pipeline_models(target: Optional[str]=Form(None)):
    """1-Click Revert: Instantly resets Live, Upload, or both AI pipelines back to rock-solid factory defaults."""
    from src.detection.model_registry import registry
    res = registry.revert_to_defaults(target=target)
    try:
        live_veh = registry.get_active_model_id('vehicle', target='live')
        live_plt = registry.get_active_model_id('plate', target='live')
        live_ocr = registry.get_active_model_id('ocr', target='live')
        pipeline = get_anpr_pipeline()
        pipeline.switch_vehicle_model(live_veh)
        pipeline.switch_plate_model(live_plt)
        pipeline.switch_ocr_model(live_ocr)
        with _user_stream_lock:
            for mgr in user_stream_managers.values():
                mgr.switch_pipeline_models(vehicle_model=live_veh, plate_model=live_plt, ocr_model=live_ocr)
    except Exception as e:
        print(f'[WARN] Error resetting live stream pipeline models: {e}')
    try:
        global _upload_anpr_pipeline
        if _upload_anpr_pipeline is not None:
            up_veh = registry.get_active_model_id('vehicle', target='upload')
            up_plt = registry.get_active_model_id('plate', target='upload')
            up_ocr = registry.get_active_model_id('ocr', target='upload')
            _upload_anpr_pipeline.switch_vehicle_model(up_veh)
            _upload_anpr_pipeline.switch_plate_model(up_plt)
            _upload_anpr_pipeline.switch_ocr_model(up_ocr)
    except Exception as e:
        print(f'[WARN] Error resetting upload pipeline models: {e}')
    return res

@app.post('/api/camera/toggle_pause')
async def toggle_camera_pause(request: Request, camera_id: Optional[str]=Form(None), paused: Optional[bool]=Form(None)):
    """



    Toggles or sets the pause state for a specific camera or all active cameras in the user's workspace.



    When paused, frame capture and video playback are frozen in place,



    allowing detailed forensic inspection without advancing video time.



    """
    content_type = request.headers.get('content-type', '')
    if 'application/json' in content_type:
        try:
            body = await request.json()
            if 'camera_id' in body and camera_id is None:
                camera_id = body.get('camera_id')
            if 'paused' in body and paused is None:
                paused = body.get('paused')
        except Exception:
            pass
    cid = camera_id.strip().upper() if camera_id else None
    mgr = get_user_stream_manager(request)
    res = mgr.toggle_pause(camera_id=cid, paused=paused)
    return {'status': 'success', 'result': res}

@app.get('/api/camera/layers')
def get_camera_overlay_layers(request: Request, camera_id: Optional[str]=None):
    """Returns the currently active selective HUD overlay layers for user's live streams."""
    cid = camera_id.strip().upper() if camera_id else None
    mgr = get_user_stream_manager(request)
    layers = mgr.get_overlay_layers(cid)
    return {'status': 'success', 'camera_id': cid or 'ALL', 'overlay_layers': layers}

@app.post('/api/camera/layers')
def set_camera_overlay_layers(request: Request, payload: Dict[str, Any]):
    cid = payload.get('camera_id')
    if cid:
        cid = str(cid).strip().upper()
    valid_keys = ('vehicle_box', 'bytetrack', 'plate_box', 'ocr_text', 'person_box', 'people_counter')
    layers = {k: bool(v) for k, v in payload.items() if k in valid_keys}
    mgr = get_user_stream_manager(request)
    updated = mgr.set_overlay_layers(layers, camera_id=cid)
    return {'status': 'success', 'camera_id': cid or 'ALL', 'overlay_layers': updated}

@app.get('/api/camera/status')
def get_camera_status(request: Request, camera_id: Optional[str]=None):
    """Returns real-time stream status, FPS, resolution, and ANPR toggle state strictly for the caller's private session."""
    mgr = get_user_stream_manager(request)
    if camera_id:
        cid = camera_id.strip().upper()
        cam_info = mgr.get_status(cid)
        return {'status': 'success', 'camera_id': cid, 'camera': cam_info}
    full_status = mgr.get_status()
    return {'status': 'success', 'cameras': full_status.get('cameras', {}), 'total_slots': full_status.get('total_slots', 4), 'active_count': full_status.get('active_count', 0), 'camera': full_status}

@app.get('/api/camera/stream/{camera_id}')
def get_camera_mjpeg_stream_by_id(request: Request, camera_id: str):
    """



    Streams multipart MJPEG video directly for a specific camera slot (CAM-01 .. CAM-04) from caller's private manager.



    """
    cid = camera_id.strip().upper()
    mgr = get_user_stream_manager(request)
    cam = mgr.get_camera(cid)
    if not cam or not cam.is_running:
        raise HTTPException(status_code=503, detail=f'Camera stream {cid} is not active in your workspace. Connect a feed first.')
    return StreamingResponse(cam.generate_mjpeg_frames(), media_type='multipart/x-mixed-replace; boundary=frame')

@app.get('/api/camera/stream')
def get_camera_mjpeg_stream(request: Request):
    """



    Streams multipart MJPEG video directly into the browser (defaults to CAM-01 for backward compatibility) from caller's private manager.



    """
    mgr = get_user_stream_manager(request)
    cam = mgr.get_camera('CAM-01')
    if not cam or not cam.is_running:
        raise HTTPException(status_code=503, detail='Camera stream CAM-01 is not active in your workspace. Connect a feed first.')
    return StreamingResponse(cam.generate_mjpeg_frames(), media_type='multipart/x-mixed-replace; boundary=frame')

@app.get('/api/camera/snapshot')
def get_camera_snapshot(request: Request, camera_id: Optional[str]=None):
    cid = camera_id.strip().upper() if camera_id else 'CAM-04'
    mgr = get_user_stream_manager(request)
    frame = mgr.get_snapshot(cid)
    if frame is None:
        raise HTTPException(status_code=503, detail='No active camera feed available for snapshot in your workspace.')
    ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ret:
        raise HTTPException(status_code=500, detail='Failed to encode frame as JPEG.')
    return Response(content=buf.tobytes(), media_type='image/jpeg')

@app.post('/api/camera/inspect-click')
async def inspect_camera_click(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    camera_id = data.get('camera_id') or 'CAM-01'
    try:
        norm_x = float(data.get('norm_x', 0.0))
        norm_y = float(data.get('norm_y', 0.0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Invalid normalized coordinates (norm_x, norm_y).')
    mgr = get_user_stream_manager(request)
    target = mgr.inspect_target_at_coords(camera_id=camera_id, norm_x=norm_x, norm_y=norm_y)
    if not target:
        return {'success': True, 'found': False, 'message': 'No active target detected at clicked position.'}
    return {'success': True, 'found': True, 'target': target}

@app.get('/api/camera/active-boxes')
def get_camera_active_boxes(request: Request, camera_id: str='CAM-01'):
    cid = camera_id.strip().upper()
    mgr = get_user_stream_manager(request)
    cam = mgr.get_camera(cid)
    if not cam:
        return {'boxes': []}
    with cam._lock:
        displays = [{'type': 'VEHICLE', 'track_id': d.get('track_id'), 'bbox': list(d.get('bbox', [])), 'plate_bbox': list(d.get('plate_bbox', [])) if d.get('plate_bbox') else None, 'plate': d.get('disp_plate')} for d in cam._cached_displays]
        persons = [{'type': 'PERSON', 'track_id': p.get('track_id'), 'bbox': list(p.get('bbox', []))} for p in cam._cached_persons]
        fh, fw = cam.last_frame.shape[:2] if cam.last_frame is not None else (720, 1280)
    return {'camera_id': cid, 'frame_size': [fw, fh], 'vehicles': displays, 'persons': persons}

def create_sample_demo_video(output_path: str):
    """



    Creates a synthetic traffic video with multiple vehicles, plate textures,



    simulated occlusion (causing ByteTrack track break to demonstrate vehicle merging),



    and edge blur.



    """
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 30
    width, height = (1280, 720)
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    num_frames = 120
    for f in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (50, 50, 50)
        cv2.line(frame, (0, 360), (1280, 360), (255, 255, 255), 2)
        for x_dash in range(0, 1280, 60):
            cv2.line(frame, (x_dash, 540), (x_dash + 30, 540), (255, 255, 255), 3)
        cv2.putText(frame, 'CAM-01 2026-09-20 12:55:00 LIVE', (30, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        v1_x = 100 + f * 9
        v1_y = 380
        is_occluded = 50 <= f <= 56
        if not is_occluded and v1_x < 1150:
            cv2.rectangle(frame, (v1_x, v1_y), (v1_x + 180, v1_y + 110), (220, 220, 220), -1)
            cv2.rectangle(frame, (v1_x, v1_y), (v1_x + 180, v1_y + 110), (100, 100, 100), 2)
            p1_x = v1_x + 40
            p1_y = v1_y + 70
            cv2.rectangle(frame, (p1_x, p1_y), (p1_x + 100, p1_y + 30), (255, 255, 255), -1)
            cv2.rectangle(frame, (p1_x, p1_y), (p1_x + 100, p1_y + 30), (0, 0, 0), 2)
            cv2.putText(frame, 'MH12DE1433', (p1_x + 6, p1_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2)
        cv2.rectangle(frame, (600, 320), (630, 520), (30, 30, 30), -1)
        v2_x = 1100 - f * 8
        v2_y = 200
        if 50 < v2_x < 1200:
            cv2.rectangle(frame, (v2_x, v2_y), (v2_x + 160, v2_y + 90), (180, 100, 40), -1)
            p2_x = v2_x + 35
            p2_y = v2_y + 55
            cv2.rectangle(frame, (p2_x, p2_y), (p2_x + 90, p2_y + 26), (255, 255, 255), -1)
            cv2.rectangle(frame, (p2_x, p2_y), (p2_x + 90, p2_y + 26), (0, 0, 0), 2)
            cv2.putText(frame, 'DL01AB1234', (p2_x + 5, p2_y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 2)
        out.write(frame)
    out.release()
    print(f'[Demo] Created demo video at {output_path}')

@app.get('/api/unified/live-feed')
def get_unified_live_feed(request: Request, limit: int=15, source: Optional[str]='live', district: Optional[str]=None, operator: Optional[str]=None):
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    cam_status = get_user_stream_manager(request).get_status()
    recent_vehicles = captured_db.get_recent(limit=limit, district=eff_district, operator=eff_operator, source=source)
    total_vehicles = captured_db.get_total_count(district=eff_district, operator=eff_operator)
    stolen_hits = len(captured_db.get_recent(limit=100, hotlist_only=True, district=eff_district, operator=eff_operator))
    return {'success': True, 'source': source, 'fresh_vehicles': recent_vehicles, 'kpi': {'vehicles_count': total_vehicles, 'stolen_alerts': stolen_hits}, 'camera_status': cam_status, 'effective_district': eff_district, 'effective_operator': eff_operator}

@app.get('/api/unified/audit-vehicles')
def get_unified_audit_vehicles(request: Request, limit: int=100, offset: int=0, search: Optional[str]=None, hotlist_only: bool=False, district: Optional[str]=None, operator: Optional[str]=None):
    """Returns historical FIFO vehicle records (up to 100) for the sidebar drawer."""
    user = get_current_user_optional(request)
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    items = captured_db.get_recent(limit=limit, offset=offset, search=search, hotlist_only=hotlist_only, district=eff_district, operator=eff_operator)
    return {'success': True, 'total_count': captured_db.get_total_count(district=eff_district, operator=eff_operator), 'vehicles': items, 'effective_district': eff_district, 'effective_operator': eff_operator}
HARYANA_DISTRICTS = ['All Haryana (State HQ)', 'Ambala', 'Bhiwani', 'Charkhi Dadri', 'Faridabad', 'Fatehabad', 'Gurugram', 'Hisar', 'Jhajjar', 'Jind', 'Kaithal', 'Karnal', 'Kurukshetra', 'Mahendragarh', 'Nuh', 'Palwal', 'Panchkula', 'Panipat', 'Rewari', 'Rohtak', 'Sirsa', 'Sonipat', 'Yamunanagar']

@app.get('/api/districts')
def get_districts():
    """Returns official list of Haryana Police districts for multi-tenant filtering."""
    return {'districts': HARYANA_DISTRICTS}

@app.get('/api/alerts/active')
def get_active_alerts(request: Request, district: Optional[str]=None):
    """Returns active unacknowledged emergency alerts for the floating card and bell badge."""
    current_user = get_current_user_optional(request)
    eff_district = district
    if not eff_district or eff_district.lower() in ['all', 'all haryana', 'all haryana (state hq)', 'state hq']:
        if current_user and current_user.get('role') not in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
            eff_district = current_user.get('district')
        else:
            eff_district = None
    if current_user and current_user.get('role') in ('STATE_ADMIN', 'DEVELOPER_ADMIN') and (not district):
        stats = audit_db.get_audit_stats()
        return {'success': True, 'count': 0, 'alerts': [], 'stats': stats}
    pending = audit_db.get_pending_alerts(district=eff_district, limit=15)
    stats = audit_db.get_audit_stats(district=eff_district)
    return {'success': True, 'count': len(pending), 'alerts': pending, 'stats': stats}

@app.post('/api/alerts/acknowledge')
async def acknowledge_alert(request: Request, alert_id: str=Form(...), officer_name: str=Form(...), officer_belt_number: str=Form(...), officer_district: str=Form(...), action_taken: str=Form(...), remarks: Optional[str]=Form(None)):
    """



    Mandatory operator acknowledgment endpoint with Chain-of-Custody logging.



    Records operator details, action taken, and latency in seconds.



    """
    client_ip = request.client.host if request.client else '127.0.0.1'
    updated = audit_db.acknowledge_alert(alert_id=alert_id, officer_name=officer_name, officer_belt_number=officer_belt_number, officer_district=officer_district, action_taken=action_taken, remarks=remarks, workstation_ip=client_ip)
    if not updated:
        raise HTTPException(status_code=404, detail='Alert record not found')
    return {'success': True, 'alert': updated}

@app.get('/api/alerts/audit-log')
def get_alert_audit_logs(request: Request, limit: int=150, offset: int=0, category: Optional[str]='ALL', status: Optional[str]=None, action_type: Optional[str]=None, target_type: Optional[str]=None, district: Optional[str]=None, operator: Optional[str]=None, alert_type: Optional[str]=None, search: Optional[str]=None):
    """Returns unified tamper-evident audit logs with multi-tenant RBAC scope resolution."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    role = str(user.get('role', 'OPERATOR')).upper().strip()
    if role == 'OPERATOR':
        raise HTTPException(status_code=403, detail='Access Denied: Operators do not have permission to view Alert Audit Trails.')
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    eff_action = action_type or status or 'ALL'
    eff_target = target_type or alert_type or 'ALL'
    return audit_db.get_unified_audit_logs(limit=limit, offset=offset, category=category, action_type=eff_action, target_type=eff_target, district=eff_district, operator=eff_operator, search=search)

@app.get('/api/alerts/stats')
def get_alert_stats(request: Request, district: Optional[str]=None, operator: Optional[str]=None):
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    role = str(user.get('role', 'OPERATOR')).upper().strip()
    if role == 'OPERATOR':
        raise HTTPException(status_code=403, detail='Access Denied: Operators do not have permission to view Alert Audit Trails.')
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    return audit_db.get_audit_stats(district=eff_district, operator=eff_operator)

@app.get('/api/alerts/export-csv')
def export_alert_audit_csv(request: Request, district: Optional[str]=None, operator: Optional[str]=None):
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    role = str(user.get('role', 'OPERATOR')).upper().strip()
    if role == 'OPERATOR':
        raise HTTPException(status_code=403, detail='Access Denied: Operators do not have permission to export Alert Audit Trails.')
    eff_district, eff_operator = resolve_rbac_filters(user, district, operator)
    csv_data = audit_db.export_csv(district=eff_district, operator=eff_operator)
    clean_dist = (eff_district or 'statewide').replace(' ', '_')
    return StreamingResponse(io.StringIO(csv_data), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename=haryana_police_alert_audit_{clean_dist}.csv'})
upload_progress_tracker: Dict[str, Dict[str, Any]] = {}

def update_upload_progress(task_id: Optional[str], data: Dict[str, Any]):
    if not task_id:
        return
    now = time.time()
    stale = [k for k, v in upload_progress_tracker.items() if now - v.get('updated_at', 0) > 900]
    for k in stale:
        upload_progress_tracker.pop(k, None)
    entry = upload_progress_tracker.get(task_id, {})
    entry.update(data)
    entry['updated_at'] = now
    upload_progress_tracker[task_id] = entry

async def _handle_unified_upload_impl(file: UploadFile, target_fps: int=5, user: Optional[Dict[str, Any]]=None, task_id: Optional[str]=None, save_annotated: bool=True, target: str='both', location: Optional[str]=None, gps_coords: Optional[str]=None, captured_at: Optional[str]=None):
    registry_camera = resolve_camera(location=location)
    if registry_camera:
        _, location, gps_coords = camera_metadata(registry_camera)
    if str(target).lower() not in ('vehicle', 'vehicles', 'vehicle_only', 'vehicle only', 'anpr', 'both'):
        raise HTTPException(status_code=400, detail='Only vehicle analysis is supported')
    filename = file.filename or 'media'
    ext = os.path.splitext(filename)[1].lower()
    is_video = ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm'] or (file.content_type and 'video' in file.content_type)
    t_clean = str(target or 'both').strip().lower()
    target_clean = 'vehicle'
    run_anpr = target_clean in ('both', 'vehicle')
    if task_id:
        if is_video:
            status_init = f'Initialising {target_clean.title()} video analysis...' if target_clean != 'both' else 'Ingesting media stream...'
        elif target_clean == 'vehicle':
            status_init = 'Running ANPR vehicle & plate pipeline...'
        elif target_clean == 'vehicle':
            status_init = 'Running ANPR vehicle & plate pipeline...'
        else:
            status_init = 'Running ANPR vehicle & plate pipeline...'
        update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'video' if is_video else 'image', 'status': 'uploading', 'status_text': status_init, 'current_frame': 0, 'total_frames': 1 if not is_video else 0, 'pct': 2})
    contents = await file.read()
    if len(contents) == 0:
        if task_id:
            update_upload_progress(task_id, {'status': 'error', 'status_text': 'Uploaded file is empty', 'pct': 100})
        raise HTTPException(status_code=400, detail='Uploaded file is empty')
    u_district = (user.get('district') if user else None) or 'Panipat'
    u_op_username = (user.get('username') if user else None) or 'op_5421'
    u_op_id = str(user.get('id') if user and user.get('id') else u_op_username)
    u_station = (user.get('station') if user else None) or 'PHQ'
    unified = get_upload_unified_pipeline()
    if not is_video:
        if task_id:
            update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'image', 'status': 'processing', 'status_text': 'Running ANPR vehicle & plate pipeline...', 'current_frame': 1, 'total_frames': 1, 'pct': 50})
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail='Invalid image file format')
        frame_h, frame_w = image.shape[:2]
        result = await asyncio.to_thread(unified.process_image, image, district=u_district, operator_username=u_op_username, operator_id=u_op_id, station=u_station, target=target_clean)
        if not result.get('success', False):
            raise HTTPException(status_code=500, detail=result.get('error', 'Processing failed'))
        for v in result['vehicles']:
            raw_p = v.get('final_plate') or ''
            norm_plate = raw_p.replace(' ', '').upper()
            is_unreadable = not norm_plate or norm_plate == 'UNREADABLE'
            p_img = None
            v_img = None
            enh_img = None
            if v.get('plate_crop_base64'):
                try:
                    p_img = cv2.imdecode(np.frombuffer(base64.b64decode(v['plate_crop_base64']), np.uint8), cv2.IMREAD_COLOR)
                except Exception:
                    pass
            if v.get('vehicle_crop_base64'):
                try:
                    v_img = cv2.imdecode(np.frombuffer(base64.b64decode(v['vehicle_crop_base64']), np.uint8), cv2.IMREAD_COLOR)
                except Exception:
                    pass
            if v.get('enhanced_crop_base64'):
                try:
                    enh_img = cv2.imdecode(np.frombuffer(base64.b64decode(v['enhanced_crop_base64']), np.uint8), cv2.IMREAD_COLOR)
                except Exception:
                    pass
            prep_meta = v.get('preprocessing_meta')
            if not is_unreadable:
                db_match = vehicle_db.match_plate(norm_plate)
                hotlist_info_str = format_hotlist_info(db_match)
                v['is_hotlist_hit'] = db_match is not None
                v['hotlist_info'] = hotlist_info_str
                v['hotlist_match'] = db_match
                captured_db.add_capture(plate_number=norm_plate, display_plate=v.get('display_plate') or norm_plate, confidence=v.get('confidence', 90.0), plate_img=p_img, vehicle_img=v_img, annotated_img=image, location=location if location and location.strip() else 'Unified Media Hub / Photo', gps_coords=gps_coords, clip_name=filename, captured_at=captured_at, source_type='photo_upload', is_hotlist_hit=db_match is not None, hotlist_info=hotlist_info_str, blur_score=100.0, aspect_ratio=3.0, det_confidence=95.0, ocr_confidence=v.get('confidence', 90.0), format_type='standard', quality_gate_passed=v.get('is_verified', True), quality_reason='Unified Multi-Modal Verified', enhanced_img=enh_img, preprocessing_data=prep_meta, is_fallback=False, district=u_district, operator_id=u_op_id, operator_username=u_op_username, station=u_station, is_traffic_violation=bool(v.get('is_traffic_violation', False)), violation_type=v.get('violation_type'), violation_fine=v.get('violation_fine', 0), violation_id=v.get('violation_id'), violation_details=v.get('violation_details'))
                if v.get('is_verified') and db_match:
                    passage_id = f'unified_photo_{int(time.time())}_{norm_plate}'
                    trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=norm_plate, camera_id=registry_camera['id'] if registry_camera else 'UPLOAD-01', location=location or 'Uploaded media', captured_at=datetime.datetime.now().astimezone().isoformat(), confidence=v.get('confidence', 90.0), plate_img=p_img, vehicle_img=v_img, passage_id=passage_id, min_cooldown_seconds=1.0, district=u_district, operator_id=u_op_id, operator_username=u_op_username, station=u_station, gps_coords=gps_coords)
                if db_match:
                    audit_db.create_alert(alert_type='ANPR_HOTLIST', entity_identifier=norm_plate, display_name=v.get('display_plate') or norm_plate, case_info=hotlist_info_str or 'Watchlist Match', camera_id=registry_camera['id'] if registry_camera else 'UPLOAD-01', camera_location='Unified Media Hub / Photo', origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=u_district, confidence=float(v.get('confidence', 90.0)), snapshot_path=v.get('plate_crop_base64'))
            elif p_img is not None or (v_img is not None and v_img.shape[0] >= 100 and (v_img.shape[1] >= 100) and (v_img.shape[0] * v_img.shape[1] >= frame_h * frame_w * 0.05)):
                v['captured_id'] = captured_db.add_capture(plate_number='UNREADABLE', display_plate='UNREADABLE', confidence=0.0, plate_img=p_img, vehicle_img=v_img, annotated_img=image, location=location if location and location.strip() else 'Unified Media Hub / Photo', gps_coords=gps_coords, clip_name=filename, captured_at=captured_at, source_type='photo_upload', is_hotlist_hit=False, hotlist_info=None, blur_score=0.0, aspect_ratio=3.0, det_confidence=90.0, ocr_confidence=0.0, format_type='unreadable', quality_gate_passed=False, quality_reason='Unreadable Plate (Fallback)', enhanced_img=enh_img, preprocessing_data=prep_meta, is_fallback=True, district=u_district, operator_id=u_op_id, operator_username=u_op_username, station=u_station, is_traffic_violation=bool(v.get('is_traffic_violation', False)), violation_type=v.get('violation_type'), violation_fine=v.get('violation_fine', 0), violation_id=v.get('violation_id'), violation_details=v.get('violation_details'))
        if task_id:
            update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'image', 'status': 'completed', 'status_text': 'Analysis complete!', 'current_frame': 1, 'total_frames': 1, 'pct': 100})
        p_state = get_user_pipeline_state(u_op_username)
        p_state['results'] = {'verified_vehicles': [v for v in result['vehicles'] if v.get('is_verified')], 'needs_review': [v for v in result['vehicles'] if not v.get('is_verified')], 'unreadable_vehicles': [v for v in result['vehicles'] if v.get('final_plate') == 'UNREADABLE'], 'stats': {'verified_total': sum((1 for v in result['vehicles'] if v.get('is_verified'))), 'needs_review_total': sum((1 for v in result['vehicles'] if not v.get('is_verified'))), 'total_vehicles': len(result['vehicles'])}}
        p_state['is_processing'] = False
        p_state['progress'] = 100.0
        try:
            investigation_db.add_search({'username': u_op_username, 'officer_name': user.get('full_name') if user else 'Duty Officer', 'belt_number': user.get('belt_number') if user else '--', 'district': u_district, 'station': u_station, 'role': user.get('role') if user else 'OPERATOR', 'filename': filename, 'media_type': 'photo', 'target_scope': target_clean.upper(), 'vehicle_model': 'IISc UVH-26 SOTA', 'ocr_engine': 'PaddleOCR Dual-Pass SOTA', 'fps': 1, 'total_vehicles': len(result['vehicles']), 'total_plates': sum((1 for v in result['vehicles'] if v.get('final_plate') and v.get('final_plate') != 'UNREADABLE')), 'hotlist_hits': sum((1 for v in result['vehicles'] if v.get('is_hotlist_hit'))), 'vehicles_json': result['vehicles'], 'output_media_url': '', 'status': 'COMPLETED'})
        except Exception as e_hist:
            logger.warning(f'Failed to record photo search history: {e_hist}')
        return {'success': True, 'media_type': 'image', 'target': target_clean, 'vehicles': result['vehicles'], 'people_count': result['people_count'], 'correlation': result['correlation'], 'annotated_image_base64': result['annotated_image_base64'], 'stats': {'total_vehicles': len(result['vehicles']), 'people_count': result['people_count'], 'hotlist_vehicles': sum((1 for v in result['vehicles'] if v.get('is_hotlist_hit')))}}
    else:
        user_meta = {'district': u_district, 'operator_id': u_op_id, 'operator_username': u_op_username, 'station': u_station, 'officer_name': user.get('full_name') if user else 'Duty Officer', 'belt_number': user.get('belt_number') if user else '--', 'role': user.get('role') if user else 'OPERATOR'}
        return await asyncio.to_thread(_process_unified_video_sync, contents, filename, target_fps, user_meta, task_id, save_annotated, target_clean, location, gps_coords, captured_at)

def _process_unified_video_sync(contents: bytes, filename: str, target_fps: int=5, user_meta: Optional[Dict[str, Any]]=None, task_id: Optional[str]=None, save_annotated: bool=True, target: str='both', location: Optional[str]=None, gps_coords: Optional[str]=None, captured_at: Optional[str]=None) -> dict:
    registry_camera = resolve_camera(location=location)
    if registry_camera:
        _, location, gps_coords = camera_metadata(registry_camera)
    if str(target).lower() not in ('vehicle', 'vehicles', 'vehicle_only', 'vehicle only', 'anpr', 'both'):
        raise HTTPException(status_code=400, detail='Only vehicle analysis is supported')
    safe_fn = re.sub('[^a-zA-Z0-9_.-]', '_', os.path.basename(filename))
    in_fn = f'unified_in_{int(time.time())}_{safe_fn}'
    in_path = os.path.join(OUTPUTS_DIR, in_fn)
    with open(in_path, 'wb') as f:
        f.write(contents)
    u_district = (user_meta.get('district') if user_meta else None) or 'Panipat'
    u_op_username = (user_meta.get('operator_username') if user_meta else None) or 'op_5421'
    u_op_id = str(user_meta.get('operator_id') if user_meta else u_op_username)
    u_station = (user_meta.get('station') if user_meta else None) or 'PHQ'
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        cleanup_file_safely(in_path)
        raise HTTPException(status_code=400, detail='Could not decode video file')
    try:
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        target_w = orig_w if orig_w % 2 == 0 else orig_w - 1
        target_h = orig_h if orig_h % 2 == 0 else orig_h - 1
        out_fn = None
        out_path = None
        writer = None
        sampler = VideoFrameSampler(fps, target_fps)
        out_fps = sampler.output_fps
        sampled_total = sampler.count(total_frames)
        sampled_total = max(1, sampled_total)
        if save_annotated:
            out_fn = f'unified_out_{int(time.time())}.mp4'
            out_path = os.path.join(OUTPUTS_DIR, out_fn)
            for codec_str in ['mp4v', 'avc1', 'H264', 'XVID', 'MJPG']:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*codec_str)
                    w_candidate = cv2.VideoWriter(out_path, fourcc, out_fps, (target_w, target_h))
                    if w_candidate.isOpened():
                        writer = w_candidate
                        break
                except Exception:
                    continue
            if writer is None or not writer.isOpened():
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(out_path, fourcc, out_fps, (target_w, target_h))
        frame_idx = 0
        processed_sampled_count = 0
        all_vehicles = []
        max_people_seen = 0
        last_annotated_base64 = ''
        t_clean = str(target or 'both').strip().lower()
        target_clean = 'vehicle'
        run_anpr = target_clean in ('both', 'vehicle')
        unified = get_upload_unified_pipeline()
        anpr = None
        anpr = get_upload_anpr_pipeline()
        anpr.reset_state()
        dedicated_pm = None
        veh_supports_person = False
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if not sampler.includes(frame_idx):
                continue
            processed_sampled_count += 1
            if task_id:
                raw_pct = frame_idx / max(1, total_frames) * 87.0
                pct = min(92, max(5, int(5 + raw_pct)))
                display_total = max(sampled_total, processed_sampled_count)
                update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'video', 'status': 'processing', 'status_text': f'Analysing frame {processed_sampled_count} of {display_total}...', 'current_frame': processed_sampled_count, 'total_frames': display_total, 'pct': pct})
            time.sleep(0.002)
            if (frame.shape[1], frame.shape[0]) != (target_w, target_h):
                frame = cv2.resize(frame, (target_w, target_h))
            active_veh_displays = []
            if anpr:
                active_veh_displays = anpr.process_frame(frame, frame_idx=frame_idx, timestamp=frame_idx / max(1.0, fps), sync=True)
            f_events = []
            p_dets = []
            layers = {'vehicle_box': True, 'plate_box': True, 'ocr_text': True, 'person_box': False, 'people_counter': True}
            p_count = 0
            annotated = unified.annotate_frame(frame=frame, active_vehicles=active_veh_displays, people_detections=[], people_count=p_count, layers=layers)
            if save_annotated and writer is not None and writer.isOpened():
                if (annotated.shape[1], annotated.shape[0]) != (target_w, target_h):
                    annotated_to_write = cv2.resize(annotated, (target_w, target_h))
                else:
                    annotated_to_write = annotated
                writer.write(annotated_to_write)
            if frame_idx % 10 == 0 or frame_idx == total_frames:
                last_annotated_base64 = encode_image_base64(annotated)
        cap.release()
        if writer is not None:
            writer.release()
            writer = None
        if task_id:
            display_final = max(sampled_total, processed_sampled_count)
            update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'video', 'status': 'finalizing', 'status_text': 'Finalising tracks, OCR queue & consensus...', 'current_frame': display_final, 'total_frames': display_final, 'pct': 94})
        all_vehicles = []
        if anpr:
            anpr.drain_ocr_queue(timeout=15.0)
            final_data = anpr.finalize()
            all_vehicles = []
            seen_vehicle_plates = set()
            raw_candidates = list(final_data.get('verified_vehicles', [])) + list(final_data.get('needs_review', []))
            candidate_vehicles = []
            for v in raw_candidates:
                if not v.final_plate or v.final_plate == 'UNREADABLE':
                    continue
                is_dup = False
                for cv in candidate_vehicles:
                    sim = anpr.normalizer.calculate_levenshtein(v.final_plate, cv.final_plate)
                    time_diff = abs(v.first_timestamp - cv.first_timestamp)
                    if sim >= 0.8 and time_diff <= 3.5:
                        if v.final_confidence > cv.final_confidence:
                            cv.final_plate = v.final_plate
                            cv.final_confidence = v.final_confidence
                            cv.best_crop = v.best_crop
                            cv.best_vehicle_crop = v.best_vehicle_crop
                            cv.readings.extend(v.readings)
                        is_dup = True
                        break
                if not is_dup:
                    candidate_vehicles.append(v)
            for v in candidate_vehicles:
                raw_p = v.final_plate or ''
                norm_p = raw_p.replace(' ', '').upper()
                if not norm_p or norm_p == 'UNREADABLE':
                    continue
                if norm_p in seen_vehicle_plates:
                    continue
                seen_vehicle_plates.add(norm_p)
                db_match = vehicle_db.match_plate(norm_p)
                hotlist_info_str = format_hotlist_info(db_match)
                best_r = v.readings[0] if v.readings and len(v.readings) > 0 else None
                peak_ocr_pct = round(float(v.final_confidence) * 100, 1) if v.final_confidence else 90.0
                peak_det_pct = 95.0
                if v.readings:
                    for r in v.readings:
                        if r.ocr_confidence and r.ocr_confidence * 100 > peak_ocr_pct:
                            peak_ocr_pct = round(float(r.ocr_confidence) * 100, 1)
                        if r.detection_confidence and r.detection_confidence * 100 > peak_det_pct:
                            peak_det_pct = round(float(r.detection_confidence) * 100, 1)
                scene_evidence = getattr(v, 'best_annotated_frame', None)
                if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                    scene_evidence = v.best_vehicle_crop if v.best_vehicle_crop is not None else v.best_crop
                sorted_evidence_frames = sorted(getattr(v, 'evidence_frames', []), key=lambda ef: float(ef.confidence), reverse=True)
                evidence_list = [{'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'raw_text': getattr(ef, 'raw_text', ef.text), 'confidence': round(float(ef.confidence or 0.9) * 100, 1), 'ocr_confidence': round(float(getattr(ef, 'ocr_confidence', 0.0)) * 100, 1) if getattr(ef, 'ocr_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'ocr_confidence', 0.0)), 1), 'det_confidence': round(float(getattr(ef, 'det_confidence', 0.0)) * 100, 1) if getattr(ef, 'det_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'det_confidence', 0.0)), 1), 'crop_base64': encode_image_base64(ef.crop_image), 'vehicle_crop_base64': encode_image_base64(getattr(ef, 'vehicle_crop', None)) if getattr(ef, 'vehicle_crop', None) is not None else None, 'timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'video_timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0)), 'video_time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0))} for ef in sorted_evidence_frames]
                primary_track_id = next(iter(v.linked_track_ids)) if v.linked_track_ids else v.readings[0].track_id if v.readings else None
                linked_tracks_str = ','.join((str(tid) for tid in sorted(v.linked_track_ids))) if v.linked_track_ids else str(primary_track_id) if primary_track_id is not None else ''
                plate_b64 = encode_image_base64(v.best_crop) if v.best_crop is not None else ''
                veh_b64 = encode_image_base64(v.best_vehicle_crop) if v.best_vehicle_crop is not None else ''
                enh_b64 = encode_image_base64(v.best_enhanced_crop) if v.best_enhanced_crop is not None else ''
                v_cid = captured_db.add_capture(plate_number=v.final_plate, display_plate=v.display_plate or v.final_plate, confidence=peak_ocr_pct, plate_img=v.best_crop, vehicle_img=v.best_vehicle_crop, annotated_img=scene_evidence, location=location if location and location.strip() else 'Unified Media Hub / Video', gps_coords=gps_coords, clip_name=filename, captured_at=captured_at, source_type='video_upload', is_hotlist_hit=db_match is not None, hotlist_info=hotlist_info_str, blur_score=round(float(best_r.blur_score), 1) if best_r and best_r.blur_score is not None else 0.0, aspect_ratio=round(float(getattr(best_r, 'aspect_ratio', 0.0)), 2) if best_r else 0.0, det_confidence=peak_det_pct, ocr_confidence=peak_ocr_pct, format_type=getattr(v, 'format_type', None) or (best_r.format_type if best_r else 'standard'), quality_gate_passed=v.is_verified, quality_reason='Temporal Voting Multi-Frame Verified' if v.is_verified else v.review_reason or 'Needs Review', evidence_data=evidence_list, enhanced_img=getattr(v, 'best_enhanced_crop', None), preprocessing_data=getattr(v, 'preprocessing_meta', None), track_id=primary_track_id, linked_tracks=linked_tracks_str, vehicle_id=v.vehicle_id, district=u_district, operator_id=u_op_id, operator_username=u_op_username, station=u_station)
                if v.is_verified and db_match:
                    passage_id = f'unified_vid_{int(time.time())}_{norm_p}'
                    trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=v.final_plate, camera_id=filename or 'VIDEO-UPLOAD', location=location or 'Uploaded media', gps_coords=gps_coords, captured_at=captured_at or datetime.datetime.now().astimezone().isoformat(), confidence=peak_ocr_pct, plate_img=v.best_crop, vehicle_img=v.best_vehicle_crop, passage_id=passage_id, min_cooldown_seconds=1.0, district=u_district, operator_id=u_op_id, operator_username=u_op_username, station=u_station)
                if db_match:
                    audit_db.create_alert(alert_type='ANPR_HOTLIST', entity_identifier=v.final_plate, display_name=v.display_plate or v.final_plate, case_info=hotlist_info_str or 'Watchlist Match', camera_id=registry_camera['id'] if registry_camera else 'VIDEO-UPLOAD', camera_location='Unified Media Hub / Video', origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=u_district, confidence=peak_ocr_pct)
                v_tid = list(v.linked_track_ids)[0] if v.linked_track_ids else 1
                v_bbox_coords = getattr(v, 'last_vehicle_bbox', None)
                if not v_bbox_coords and v.readings:
                    v_bbox_coords = getattr(v.readings[0], 'vehicle_box', None)
                all_vehicles.append({'captured_id': v_cid, 'bbox': list(v_bbox_coords) if v_bbox_coords else None, 'vehicle_id': f'VEH-{v.vehicle_id}', 'track_id': f'V-{v_tid}', 'raw_track_id': v_tid, 'cls_name': 'Vehicle', 'final_plate': v.final_plate, 'display_plate': v.display_plate or v.final_plate, 'confidence': peak_ocr_pct, 'is_verified': v.is_verified, 'is_hotlist_hit': db_match is not None, 'hotlist_info': hotlist_info_str, 'hotlist_match': db_match, 'plate_crop_base64': plate_b64, 'vehicle_crop_base64': veh_b64, 'enhanced_crop_base64': enh_b64, 'preprocessing_meta': getattr(v, 'preprocessing_meta', None)})
            unreadable_targets = list(final_data.get('unreadable_vehicles', [])) + list(final_data.get('unreadable', []))
            for uv in unreadable_targets:
                first_r = uv.readings[0] if uv.readings and len(uv.readings) > 0 else None
                det_conf = round(float(first_r.detection_confidence) * 100, 1) if first_r and first_r.detection_confidence is not None else round(float(getattr(uv, 'confidence', 0.85)) * 100, 1)
                if det_conf < 25.0:
                    continue
                scene_evidence = getattr(uv, 'best_annotated_frame', None)
                if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                    scene_evidence = uv.best_vehicle_crop if uv.best_vehicle_crop is not None else uv.best_crop
                evidence_list = [{'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'raw_text': getattr(ef, 'raw_text', ef.text), 'confidence': round(float(ef.confidence or 0.9) * 100, 1), 'ocr_confidence': round(float(getattr(ef, 'ocr_confidence', 0.0)) * 100, 1) if getattr(ef, 'ocr_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'ocr_confidence', 0.0)), 1), 'det_confidence': round(float(getattr(ef, 'det_confidence', 0.0)) * 100, 1) if getattr(ef, 'det_confidence', 0.0) <= 1.0 else round(float(getattr(ef, 'det_confidence', 0.0)), 1), 'crop_base64': encode_image_base64(ef.crop_image), 'vehicle_crop_base64': encode_image_base64(getattr(ef, 'vehicle_crop', None)) if getattr(ef, 'vehicle_crop', None) is not None else None, 'timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'video_timestamp': round(float(getattr(ef, 'timestamp', 0.0)), 2), 'time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0)), 'video_time_str': format_seconds_to_timestamp_str(getattr(ef, 'timestamp', 0.0))} for ef in getattr(uv, 'evidence_frames', [])]
                primary_track_id = next(iter(uv.linked_track_ids)) if uv.linked_track_ids else uv.readings[0].track_id if uv.readings else None
                linked_tracks_str = ','.join((str(tid) for tid in sorted(uv.linked_track_ids))) if uv.linked_track_ids else str(primary_track_id) if primary_track_id is not None else ''
                captured_db.add_capture(plate_number='UNREADABLE', display_plate='UNREADABLE (LOW EVIDENCE)', confidence=det_conf, plate_img=uv.best_crop, vehicle_img=uv.best_vehicle_crop, annotated_img=scene_evidence, location=location if location and location.strip() else 'Unified Media Hub / Video', gps_coords=gps_coords, clip_name=filename, captured_at=captured_at, source_type='video_upload', is_hotlist_hit=False, hotlist_info=None, blur_score=round(float(first_r.blur_score), 1) if first_r and first_r.blur_score is not None else 0.0, aspect_ratio=round(float(getattr(first_r, 'aspect_ratio', 0.0)), 2) if first_r else 0.0, det_confidence=det_conf, ocr_confidence=0.0, format_type='UNREADABLE', quality_gate_passed=False, quality_reason=uv.review_reason or f'Distant/Low Resolution Plate (<=50% OCR, {len(uv.readings)} frames detected)', evidence_data=evidence_list, track_id=primary_track_id, linked_tracks=linked_tracks_str, vehicle_id=uv.vehicle_id, district=u_district, operator_id=u_op_id, operator_username=u_op_username, station=u_station)
                uv_tid = list(uv.linked_track_ids)[0] if uv.linked_track_ids else 1
                all_vehicles.append({'vehicle_id': f'VEH-{uv.vehicle_id}', 'track_id': f'V-{uv_tid}', 'raw_track_id': uv_tid, 'cls_name': 'Vehicle', 'final_plate': 'UNREADABLE', 'display_plate': 'UNREADABLE (LOW EVIDENCE)', 'confidence': det_conf, 'is_verified': False, 'is_hotlist_hit': False, 'hotlist_info': None, 'plate_crop_base64': encode_image_base64(uv.best_crop) if uv.best_crop is not None else '', 'vehicle_crop_base64': encode_image_base64(uv.best_vehicle_crop) if uv.best_vehicle_crop is not None else '', 'enhanced_crop_base64': '', 'preprocessing_meta': None})
        final_video_url = None
        if save_annotated and out_path and os.path.exists(out_path):
            if task_id:
                display_final = max(sampled_total, processed_sampled_count)
                update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'video', 'status': 'transcoding', 'status_text': 'Transcoding H.264 stream for web player...', 'current_frame': display_final, 'total_frames': display_final, 'pct': 98})
            web_out_fn = f'unified_web_{int(time.time())}.mp4'
            web_out_path = os.path.join(OUTPUTS_DIR, web_out_fn)
            if transcode_to_h264_web(out_path, web_out_path):
                cleanup_file_safely(out_path)
                final_video_url = f'/outputs/{web_out_fn}'
            else:
                final_video_url = f'/outputs/{out_fn}'
        if task_id:
            update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'video', 'status': 'completed', 'status_text': 'Analysis complete!', 'current_frame': sampled_total, 'total_frames': sampled_total, 'pct': 100})
        p_state = get_user_pipeline_state(u_op_username)
        p_state['results'] = {'verified_vehicles': [v for v in all_vehicles if v.get('is_verified')], 'needs_review': [v for v in all_vehicles if not v.get('is_verified') and v.get('final_plate') != 'UNREADABLE'], 'unreadable_vehicles': [v for v in all_vehicles if v.get('final_plate') == 'UNREADABLE'], 'stats': {'verified_total': sum((1 for v in all_vehicles if v.get('is_verified'))), 'needs_review_total': sum((1 for v in all_vehicles if not v.get('is_verified') and v.get('final_plate') != 'UNREADABLE')), 'total_vehicles': len(all_vehicles)}}
        p_state['is_processing'] = False
        p_state['progress'] = 100.0
        try:
            investigation_db.add_search({'username': u_op_username, 'officer_name': user_meta.get('officer_name') if user_meta else 'Duty Officer', 'belt_number': user_meta.get('belt_number') if user_meta else '--', 'district': u_district, 'station': u_station, 'role': user_meta.get('role') if user_meta else 'OPERATOR', 'filename': filename, 'media_type': 'video', 'target_scope': target_clean.upper(), 'vehicle_model': 'IISc UVH-26 SOTA', 'ocr_engine': 'PaddleOCR Dual-Pass SOTA', 'fps': target_fps, 'total_vehicles': len(all_vehicles), 'total_plates': sum((1 for v in all_vehicles if v.get('final_plate') and v.get('final_plate') != 'UNREADABLE')), 'hotlist_hits': sum((1 for v in all_vehicles if v.get('is_hotlist_hit'))), 'vehicles_json': all_vehicles, 'output_media_url': final_video_url, 'status': 'COMPLETED'})
        except Exception as e_hist:
            logger.warning(f'Failed to record video search history: {e_hist}')
        return {'success': True, 'media_type': 'video', 'target': target_clean, 'output_video_url': final_video_url, 'vehicles': all_vehicles, 'people_count': max_people_seen, 'stats': {'total_vehicles': len(all_vehicles), 'people_count': max_people_seen, 'hotlist_vehicles': sum((1 for v in all_vehicles if v.get('is_hotlist_hit')))}, 'last_frame_base64': last_annotated_base64}
    except Exception as exc:
        if task_id:
            update_upload_progress(task_id, {'task_id': task_id, 'media_type': 'video', 'status': 'error', 'status_text': f'Error: {str(exc)}', 'pct': 100})
        raise
    finally:
        cap.release()
        cleanup_file_safely(in_path)

_background_upload_lock = asyncio.Lock()

@app.post('/api/unified/upload')
async def unified_upload_and_test(request: Request, file: UploadFile=File(...), fps: int=Form(5), task_id: Optional[str]=Form(None), save_annotated_video: str=Form('true'), target: Optional[str]=Form(None), location: Optional[str]=Form(None), gps_coords: Optional[str]=Form(None), captured_at: Optional[str]=Form(None), registered_camera_id: Optional[str]=Form(None), background: bool=Form(False), background_tasks: BackgroundTasks=None):
    if registered_camera_id:
        selected_camera = resolve_camera(registered_camera_id)
        if not selected_camera:
            raise HTTPException(status_code=400, detail='Unknown Karnal camera ID')
        _, location, gps_coords = camera_metadata(selected_camera)
    try:
        if not target or str(target).strip() == '':
            target = request.query_params.get('target') or 'both'
        save_annotated = str(save_annotated_video).strip().lower() in ('true', '1', 'yes', 'on')
        user = get_current_user_optional(request)
        if background:
            task_id = task_id or uuid.uuid4().hex
            # Own the bytes: FastAPI closes the request upload after returning 202.
            media = await file.read()
            detached = UploadFile(filename=file.filename, file=io.BytesIO(media), headers=file.headers)
            update_upload_progress(task_id, {'task_id': task_id, 'status': 'queued', 'pct': 0, 'status_text': 'Queued for analysis'})
            async def process_upload():
                context_token = current_user_cv.set(user)
                try:
                    async with _background_upload_lock:
                        result = await _handle_unified_upload_impl(detached, target_fps=fps, user=user, task_id=task_id, save_annotated=save_annotated, target=target, location=location, gps_coords=gps_coords, captured_at=captured_at)
                        update_upload_progress(task_id, {'status': 'completed', 'pct': 100, 'status_text': 'Analysis complete', 'result': result})
                except Exception as exc:
                    logger.exception('Background upload failed')
                    update_upload_progress(task_id, {'status': 'error', 'status_text': str(exc), 'pct': 100})
                finally:
                    await detached.close()
                    current_user_cv.reset(context_token)
            background_tasks.add_task(process_upload)
            return JSONResponse({'task_id': task_id, 'status': 'queued'}, status_code=202)
        return await _handle_unified_upload_impl(file, target_fps=fps, user=user, task_id=task_id, save_annotated=save_annotated, target=target, location=location, gps_coords=gps_coords, captured_at=captured_at)
    except HTTPException:
        raise
    except Exception as exc:
        if task_id:
            update_upload_progress(task_id, {'task_id': task_id, 'status': 'error', 'status_text': f'Unified processing error: {str(exc)}', 'pct': 100})
        logger.exception(f'Unified upload processing failed: {exc}')
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'Unified processing error: {str(exc)}')

@app.get('/api/unified/upload-progress')
def get_unified_upload_progress(task_id: str):
    """Returns live frame progress and status for unified video and image uploads."""
    prog = upload_progress_tracker.get(task_id)
    if not prog:
        return {'task_id': task_id, 'status': 'waiting', 'status_text': 'Initializing media ingestion...', 'current_frame': 0, 'total_frames': 0, 'pct': 0}
    return prog
def _vehicle_trail_review_context(request):
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in")
    from src.database.trail_review_db import review_store
    captures = captured_db._get_target()
    store = review_store(os.path.dirname(captures.db_path))
    district, operator = resolve_rbac_filters(user)
    return user, captures, store, district, operator

@app.get("/api/vehicle-trails/observations")
def list_vehicle_trail_observations(request: Request):
    user, captures, store, district, operator = _vehicle_trail_review_context(request)
    # Import existing visible captures as well as new stream/upload observations.
    for record in captures.get_recent(limit=1000, district=district, operator=operator):
        store.observe(record)
    rows = store.list(district, operator)
    return {"success": True, "observations": rows, "pending_count": sum(r["status"]=="PENDING" for r in rows)}

@app.post("/api/vehicle-trails/observations/{observation_id}/decision")
async def decide_vehicle_trail_observation(observation_id: int, request: Request):
    user, captures, store, district, operator = _vehicle_trail_review_context(request)
    payload = await request.json()
    try:
        row = store.decide(observation_id, str(payload.get("decision", "")).upper(), user["username"], district, operator, payload.get("detected_plate"), payload.get("candidate_plate"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    matched = row["status"]=="SAME"
    # Preserve the observed number; a human confirmation links, rather than rewrites, the evidence.
    captures.update_capture(row["capture_id"], is_hotlist_hit=matched,
        hotlist_info=("Human confirmed match: " + row["candidate_plate"]) if matched else "",
        update_timestamp=False)
    return {"success": True, "observation": row}

if __name__ == '__main__':
    server_port = int(os.getenv('PORT', '8000'))
    uvicorn.run('app:app', host='0.0.0.0', port=server_port, reload=False)


