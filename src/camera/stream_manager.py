"""
Camera Stream Manager Module
Handles background frame ingestion from local Webcams, RTSP streams, and HTTP/HTTPS links.
Generates MJPEG multipart streaming responses for web display.
Supports on-the-fly toggling of the AI ANPR Pipeline (Raw mode vs Full ANPR mode)
without modifying the core recognition pipeline.
"""
from typing import Optional, Union, Dict, Any, Generator, List
import threading
import collections
import time
import datetime
import os
import base64
import cv2
import numpy as np
try:
    import torch
    if hasattr(torch, 'set_num_threads'):
        torch.set_num_threads(2)
except Exception:
    pass
from config import ANPRConfig
from src.pipeline.anpr_pipeline import ANPRPipeline
from src.database.vehicle_db import VehicleDB
from src.database.captured_db import CapturedDB
from src.database.trail_db import TrailDB

class CameraStreamManager:

    def __init__(self, vehicle_db: Optional[VehicleDB]=None, captured_db: Optional[CapturedDB]=None, trail_db: Optional[TrailDB]=None, config: Optional[ANPRConfig]=None, audit_db: Optional[Any]=None, district: str='Panipat'):
        self.vehicle_db = vehicle_db
        self.captured_db = captured_db
        self.trail_db = trail_db
        self.config = config or ANPRConfig()
        self.audit_db = audit_db
        self.district = district
        self.operator_username = 'op_5421'
        self.operator_id = None
        self.station = 'PHQ'
        self._pipeline: Optional[ANPRPipeline] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._ai_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ai_trigger_event = threading.Event()
        self._latest_ai_frame: Optional[np.ndarray] = None
        self._latest_ai_frame_idx: int = 0
        self._ai_busy: bool = False
        self.is_running: bool = False
        self.is_paused: bool = False
        self.anpr_enabled: bool = True
        self.source: Optional[Union[int, str]] = None
        self.source_type: str = 'standby'
        self.camera_id: str = 'CAM-01'
        self.location: str = 'Main Surveillance Gate'
        self.gps_coords: Optional[str] = None
        self.current_fps: float = 0.0
        self.source_fps: float = 25.0
        self.target_frame_interval: int = 1
        self.resolution: str = '1080P WDR'
        self.last_frame: Optional[np.ndarray] = None
        self.last_annotated_frame: Optional[np.ndarray] = None
        self.frame_count: int = 0
        self.current_people_count: int = 0
        self.total_unique_people: int = 0
        self.connection_status: str = 'CONNECTED'
        self.reconnect_attempt: int = 0
        self.max_reconnect_attempts: int = 15
        self.last_successful_frame_time: float = time.time()
        self._rolling_frame_buffer: collections.deque = collections.deque(maxlen=90)
        self.recorded_clips_cooldown: Dict[str, float] = {}
        self._cached_displays: List[Dict[str, Any]] = []
        self._cached_persons: List[Dict[str, Any]] = []
        self._cached_jpeg_bytes: Optional[bytes] = None
        self._track_velocities: Dict[int, Tuple[float, float, float, Tuple[int, int, int, int]]] = {}
        self.passage_session_id: str = ''
        self.logged_sightings_in_passage = set()
        self.passage_captures: Dict[str, int] = {}
        self.passage_confidences: Dict[str, float] = {}
        self.audit_alert_cooldown: Dict[str, float] = {}
        self.overlay_layers: Dict[str, bool] = {'vehicle_box': True, 'bytetrack': True, 'plate_box': True, 'ocr_text': True, 'person_box': True, 'people_counter': True}

    def _get_pipeline(self) -> ANPRPipeline:
        if self._pipeline is None:
            config = self.config or ANPRConfig()
            config.voting.min_supporting_frames = 2
            self._pipeline = ANPRPipeline(config=config, async_ocr=False)
            self._pipeline.on_verified_sighting = self._handle_verified_plate_sighting
            self._pipeline.init_models()
        elif getattr(self._pipeline, 'on_verified_sighting', None) is None:
            self._pipeline.on_verified_sighting = self._handle_verified_plate_sighting
        return self._pipeline

    def switch_pipeline_models(self, vehicle_model: Optional[str]=None, plate_model: Optional[str]=None, ocr_model: Optional[str]=None):
        """Propagates model switch to the camera stream's active ANPR pipeline."""
        # Standby slots should use the selection when connected, without loading
        # a separate set of heavy models during every profile change.
        if self._pipeline is None:
            if vehicle_model:
                self.config.vehicle_model_name = vehicle_model
            if plate_model:
                self.config.plate_model_path = plate_model
            if ocr_model:
                self.config.ocr_model = ocr_model
            return
        pipeline = self._pipeline
        if vehicle_model:
            pipeline.switch_vehicle_model(vehicle_model)
        if plate_model:
            pipeline.switch_plate_model(plate_model)
        if ocr_model:
            pipeline.switch_ocr_model(ocr_model)

    def _create_capture(self) -> cv2.VideoCapture:
        """Helper to create cv2.VideoCapture with optimized DirectShow backend on Windows for webcams."""
        if isinstance(self.source, int) and os.name == 'nt':
            cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
        return cv2.VideoCapture(self.source)

    def start_stream(self, source: Union[int, str], source_type: str='webcam', camera_id: str='CAM-01', location: str='Main Surveillance Gate', gps_coords: Optional[str]=None, target_frame: int=1) -> bool:
        from src.camera.registry import resolve_camera, camera_metadata
        registered = resolve_camera(location=location)
        if registered:
            _, location, gps_coords = camera_metadata(registered)
            self.district = registered['district']
            self.station = registered['station']
        'Starts background frame grabbing and processing.'
        self.stop_stream()
        self.source = source
        self.source_type = source_type
        self.camera_id = camera_id
        self.location = location
        self.gps_coords = gps_coords.strip() if gps_coords and gps_coords.strip() else None
        self.passage_session_id = f'stream_{camera_id}_{int(time.time())}'
        self.logged_sightings_in_passage.clear()
        self.passage_captures.clear()
        self.passage_confidences.clear()
        self.frame_count = 0
        self._cached_displays = []
        self._cached_persons = []
        self.current_people_count = 0
        self.total_unique_people = 0
        self._latest_ai_frame = None
        self._ai_busy = False
        self._stop_event.clear()
        self._ai_trigger_event.clear()
        self.is_paused = False
        self.set_target_frame_interval(target_frame)
        cap = self._create_capture()
        if not cap.isOpened():
            print(f'[CameraStreamManager] Error: Unable to open stream source: {self.source}')
            return False
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
        self.resolution = f'{w}x{h}'
        cap.release()
        if self.anpr_enabled:
            try:
                self._get_pipeline()
            except Exception as pe:
                print(f'[CameraStreamManager {self.camera_id}] Pre-warm error: {pe}')
        self.is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name=f'CamCapture-{self.camera_id}')
        self._thread.start()
        self._ai_thread = threading.Thread(target=self._ai_worker_loop, daemon=True, name=f'CamAI-{self.camera_id}')
        self._ai_thread.start()
        print(f'[CameraStreamManager] Stream started on {self.camera_id} ({self.source_type}): {self.source} (GPS: {self.gps_coords})')
        return True

    def stop_stream(self):
        """Stops the active camera stream."""
        if self.is_running:
            self._stop_event.set()
            self._ai_trigger_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            if self._ai_thread and self._ai_thread.is_alive():
                self._ai_thread.join(timeout=2.0)
            self.is_running = False
            self.is_paused = False
            self.source = None
            self.source_type = 'standby'
            self.last_frame = None
            self.last_annotated_frame = None
            self._cached_displays = []
            self._cached_persons = []
            self._cached_jpeg_bytes = None
            self._latest_ai_frame = None
            self._ai_busy = False
            if self._pipeline:
                self._pipeline.drain_ocr_queue(timeout=1.0)
            self._track_velocities.clear()
            print('[CameraStreamManager] Stream stopped.')

    def toggle_pause(self, paused: Optional[bool]=None) -> bool:
        """Toggles or sets video playback pause for forensic inspection."""
        if paused is not None:
            self.is_paused = bool(paused)
        else:
            self.is_paused = not self.is_paused
        self._cached_jpeg_bytes = None
        print(f"[CameraStreamManager] Camera {self.camera_id} pause toggled: {('PAUSED' if self.is_paused else 'RESUMED')}")
        return self.is_paused

    def set_target_frame_interval(self, interval: int) -> int:
        """Sets target frame analysis cadence (1 to 20)."""
        try:
            val = int(interval)
            self.target_frame_interval = max(1, min(20, val))
        except (ValueError, TypeError):
            self.target_frame_interval = 1
        print(f'[CameraStreamManager {self.camera_id}] Target frame cadence set to: every {self.target_frame_interval} frame(s)')
        return self.target_frame_interval

    def set_anpr_enabled(self, enabled: bool) -> bool:
        """Toggles AI ANPR detection and recognition on/off."""
        self.anpr_enabled = bool(enabled)
        if not self.anpr_enabled:
            with self._lock:
                self._cached_displays = []
                self._cached_persons = []
        print(f"[CameraStreamManager] AI ANPR Pipeline toggled: {('ENABLED' if self.anpr_enabled else 'PAUSED')}")
        return self.anpr_enabled

    def set_overlay_layers(self, layers: Dict[str, bool]) -> Dict[str, bool]:
        """Toggles selective visual HUD overlay elements on live stream."""
        for k, v in layers.items():
            if k in self.overlay_layers:
                self.overlay_layers[k] = bool(v)
        return self.overlay_layers.copy()

    def trigger_evidence_clip_recording(self, entity_id: str, is_vehicle: bool=True, capture_id: Optional[int]=None):
        """Asynchronously compiles and records a 5-second incident evidence clip for hotlist/suspect matches."""
        if not entity_id or not capture_id:
            return
        now = time.time()
        last_rec = self.recorded_clips_cooldown.get(entity_id, 0.0)
        if now - last_rec < 30.0:
            return
        self.recorded_clips_cooldown[entity_id] = now
        with self._lock:
            pre_frames = [f.copy() for _, f in list(self._rolling_frame_buffer)] if hasattr(self, '_rolling_frame_buffer') else []

        def _clip_worker():
            try:
                post_frames = []
                for _ in range(45):
                    time.sleep(0.05)
                    with self._lock:
                        if self.last_annotated_frame is not None:
                            post_frames.append(self.last_annotated_frame.copy())
                all_clip_frames = pre_frames[-45:] + post_frames
                from src.utils.evidence_recorder import compile_evidence_clip
                clip_url = compile_evidence_clip(all_clip_frames, entity_id=entity_id, fps=max(15.0, self.current_fps))
                if clip_url:
                    if is_vehicle and self.captured_db:
                        self.captured_db.update_capture(capture_id, evidence_video_path=clip_url)
                        print(f'[EvidenceWatchdog {self.camera_id}] Stored Incident Evidence Video for {entity_id}: {clip_url}')
            except Exception as ex:
                print(f'[EvidenceWatchdog {self.camera_id}] Evidence clip error: {ex}')
        threading.Thread(target=_clip_worker, daemon=True, name=f'ClipRec-{entity_id}').start()

    def get_status(self) -> Dict[str, Any]:
        """Returns current live stream status."""
        return {'is_running': self.is_running, 'is_paused': self.is_paused, 'anpr_enabled': self.anpr_enabled, 'active_models': {'vehicle': os.path.basename(str(getattr(getattr(self._pipeline, 'vehicle_detector', None), 'model_name', 'Not loaded'))), 'plate': os.path.basename(str(getattr(getattr(self._pipeline, 'plate_detector', None), 'model_path', 'Not loaded'))), 'ocr': getattr(getattr(self._pipeline, 'ocr_engine', None), 'active_model', 'Not loaded')}, 'target_frame': self.target_frame_interval, 'people_count': self.current_people_count, 'total_unique_people': self.total_unique_people, 'overlay_layers': self.overlay_layers.copy(), 'source': str(self.source) if self.source is not None else None, 'source_type': self.source_type, 'camera_id': self.camera_id, 'location': self.location, 'gps_coords': self.gps_coords, 'fps': 0.0 if self.is_paused else round(self.current_fps, 1), 'resolution': self.resolution, 'frame_count': self.frame_count, 'connection_status': getattr(self, 'connection_status', 'CONNECTED'), 'reconnect_attempt': getattr(self, 'reconnect_attempt', 0)}

    def _handle_verified_plate_sighting(self, v_rec: Any, frame: np.ndarray, pbox: Any, vbox: Any):
        """
        Asynchronously invoked from ANPR pipeline's OCR worker thread
        whenever a vehicle's license plate identity is verified by temporal voting.
        Persists sighting into CapturedDB, triggers hotlist audits, and updates on-screen HUD tags.
        """
        try:
            if not v_rec or not getattr(v_rec, 'final_plate', None):
                return
            norm_plate = v_rec.final_plate
            disp_plate = v_rec.display_plate or (self._pipeline.normalizer.format_display(norm_plate) if self._pipeline and getattr(self._pipeline, 'normalizer', None) else norm_plate)
            final_conf_pct = round(float(getattr(v_rec, 'final_confidence', 0.0)) * 100, 1)
            is_valid = bool(getattr(v_rec, 'is_verified', False))
            db_match, match_type = self.vehicle_db.match_plate_with_type(norm_plate) if self.vehicle_db and norm_plate else (None, 'NONE')
            hotlist_str = None
            if match_type == 'EXACT':
                v_rec.alert_state = 'HOTLIST'
                v_rec.is_saturated = True
                hotlist_str = f"POLICE CASE: {db_match.get('offence_type', 'Crime')} | FIR: {db_match.get('fir_number', 'N/A')}" if db_match.get('involved_in_case') else f"LOST VEHICLE: {db_match.get('lost_location', 'Unknown')}"
                v_rec.alert_reason = hotlist_str
                now_t = time.time()
                last_alert_t = self.audit_alert_cooldown.get(norm_plate, 0.0)
                if now_t - last_alert_t > 30.0 and self.audit_db:
                    self.audit_alert_cooldown[norm_plate] = now_t
                    try:
                        p_crop_b64 = None
                        if frame is not None and getattr(frame, 'size', 0) > 0 and pbox:
                            fh, fw = frame.shape[:2]
                            c_img = frame[max(0, pbox[1]):min(fh, pbox[3]), max(0, pbox[0]):min(fw, pbox[2])]
                            if c_img.size > 0:
                                _, buf = cv2.imencode('.jpg', c_img)
                                p_crop_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
                        self.audit_db.create_alert(alert_type='ANPR_HOTLIST', entity_identifier=norm_plate, display_name=disp_plate, case_info=hotlist_str, camera_id=self.camera_id, camera_location=self.location, origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=getattr(self, 'district', 'All Haryana'), confidence=max(final_conf_pct, 85.0), snapshot_path=p_crop_b64)
                    except Exception as ae:
                        print(f'[CameraStreamManager {self.camera_id}] Hotlist audit alert error: {ae}')
            elif match_type == 'NEAR_MATCH':
                v_rec.alert_state = 'SUSPECT'
                suspect_str = f"SUSPECT NEAR-MATCH: {db_match.get('vehicle_number')} (Sim: {db_match.get('similarity', 0.85)})"
                v_rec.alert_reason = suspect_str
                now_t = time.time()
                last_alert_t = self.audit_alert_cooldown.get(norm_plate, 0.0)
                if now_t - last_alert_t > 30.0 and self.audit_db:
                    self.audit_alert_cooldown[norm_plate] = now_t
                    try:
                        p_crop_b64 = None
                        if frame is not None and getattr(frame, 'size', 0) > 0 and pbox:
                            fh, fw = frame.shape[:2]
                            c_img = frame[max(0, pbox[1]):min(fh, pbox[3]), max(0, pbox[0]):min(fw, pbox[2])]
                            if c_img.size > 0:
                                _, buf = cv2.imencode('.jpg', c_img)
                                p_crop_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
                        self.audit_db.create_alert(alert_type='ANPR_SUSPECT', entity_identifier=norm_plate, display_name=disp_plate, case_info=suspect_str, camera_id=self.camera_id, camera_location=self.location, origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=getattr(self, 'district', 'All Haryana'), confidence=max(final_conf_pct, 75.0), snapshot_path=p_crop_b64)
                    except Exception as ae:
                        print(f'[CameraStreamManager {self.camera_id}] Suspect near-match alert error: {ae}')
            else:
                v_rec.alert_state = 'NORMAL'
            frame_h, frame_w = frame.shape[:2] if frame is not None and getattr(frame, 'size', 0) > 0 else (1080, 1920)
            px1, py1, px2, py2 = pbox if pbox is not None else (0, 0, frame_w, frame_h)
            vx1, vy1, vx2, vy2 = vbox if vbox is not None else (0, 0, frame_w, frame_h)
            passage_key = f'{self.passage_session_id}_{v_rec.vehicle_id}'
            p_crop = getattr(v_rec, 'best_crop', None)
            if (p_crop is None or getattr(p_crop, 'size', 0) == 0) and pbox is not None and (frame is not None):
                p_crop = frame[max(0, py1):min(frame_h, py2), max(0, px1):min(frame_w, px2)]
            v_crop = getattr(v_rec, 'best_vehicle_crop', None)
            if (v_crop is None or getattr(v_crop, 'size', 0) == 0) and frame is not None:
                v_crop = frame[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)]
            scene_evidence = getattr(v_rec, 'best_annotated_frame', None)
            if (scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0) and frame is not None:
                scene_evidence = frame
            best_r = getattr(v_rec, 'best_reading', None)
            if best_r is None and getattr(v_rec, 'readings', None):
                best_r = max(v_rec.readings, key=lambda r: (r.ocr_confidence, getattr(r, 'blur_score', 0.0)))
            evidence_list = []
            for ef in getattr(v_rec, 'evidence_frames', []):
                b64_crop = ''
                if getattr(ef, 'crop_image', None) is not None and ef.crop_image.size > 0:
                    ok, buf = cv2.imencode('.jpg', ef.crop_image, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    if ok:
                        b64_crop = base64.b64encode(buf).decode('utf-8')
                evidence_list.append({'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'confidence': round(float(ef.confidence) * 100, 1), 'crop_base64': b64_crop})
            if self.captured_db:
                with self._lock:
                    is_existing = passage_key in self.passage_captures
                    existing_cid = self.passage_captures.get(passage_key)
                    prev_conf = self.passage_confidences.get(passage_key, 0.0)
                if is_existing and existing_cid:
                    if final_conf_pct > prev_conf:
                        self.captured_db.update_capture(capture_id=existing_cid, confidence=final_conf_pct, plate_img=p_crop, vehicle_img=v_crop, annotated_img=scene_evidence, det_confidence=round(float(best_r.detection_confidence or 0.0) * 100, 1) if best_r else 0.0, ocr_confidence=round(float(best_r.ocr_confidence or 0.0) * 100, 1) if best_r else 0.0, blur_score=round(float(best_r.blur_score or 0.0), 1) if best_r else 0.0, display_plate=disp_plate, plate_number=norm_plate, is_hotlist_hit=match_type == 'EXACT', hotlist_info=hotlist_str or '', evidence_data=evidence_list, quality_gate_passed=is_valid, quality_reason='Live Camera Ingestion Verified Apex', track_id=getattr(best_r, 'track_id', None) or (list(v_rec.linked_track_ids)[0] if getattr(v_rec, 'linked_track_ids', None) else None), vehicle_id=getattr(v_rec, 'vehicle_id', None))
                        with self._lock:
                            self.passage_confidences[passage_key] = final_conf_pct
                else:
                    new_cid = self.captured_db.add_capture(plate_number=norm_plate, display_plate=disp_plate, confidence=final_conf_pct, plate_img=p_crop, vehicle_img=v_crop, annotated_img=scene_evidence, location=self.location, source_type=f'stream_{self.source_type}', is_hotlist_hit=match_type == 'EXACT', hotlist_info=hotlist_str or '', blur_score=round(float(best_r.blur_score or 0.0), 1) if best_r else 0.0, aspect_ratio=round(float(getattr(best_r, 'aspect_ratio', 0.0)), 2) if best_r else 0.0, det_confidence=round(float(best_r.detection_confidence or 0.0) * 100, 1) if best_r else 0.0, ocr_confidence=round(float(best_r.ocr_confidence or 0.0) * 100, 1) if best_r else 0.0, format_type=getattr(v_rec, 'format_type', None) or (best_r.format_type if best_r else 'standard'), quality_gate_passed=is_valid, quality_reason='Live Camera Ingestion Verified' if is_valid else 'Needs Review', evidence_data=evidence_list, is_fallback=final_conf_pct < 60.0, track_id=getattr(best_r, 'track_id', None) or (list(v_rec.linked_track_ids)[0] if getattr(v_rec, 'linked_track_ids', None) else None), vehicle_id=getattr(v_rec, 'vehicle_id', None), district=getattr(self, 'district', 'Panipat'), operator_id=getattr(self, 'operator_id', None), operator_username=getattr(self, 'operator_username', 'op_5421'), station=getattr(self, 'station', 'PHQ'))
                    if new_cid and new_cid > 0:
                        with self._lock:
                            self.passage_captures[passage_key] = new_cid
                            self.passage_confidences[passage_key] = final_conf_pct
                            self.logged_sightings_in_passage.add(passage_key)
                        print(f'[CameraStreamManager {self.camera_id}] Live verified plate logged to CapturedDB: #{new_cid} | Plate: {norm_plate} ({final_conf_pct}%)')
            if match_type == 'EXACT' and db_match and self.trail_db:
                trail_key = f'trail_{passage_key}'
                already_trailed = False
                with self._lock:
                    if trail_key in self.logged_sightings_in_passage:
                        already_trailed = True
                    else:
                        self.logged_sightings_in_passage.add(trail_key)
                if not already_trailed:
                    try:
                        self.trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=norm_plate, camera_id=self.camera_id, location=self.location, gps_coords=self.gps_coords, captured_at=datetime.datetime.now().astimezone().isoformat(), confidence=round(float(v_rec.final_confidence) * 100, 1), plate_img=p_crop, vehicle_img=v_crop, passage_id=passage_key, min_cooldown_seconds=4.0, district=getattr(self, 'district', 'Panipat'), operator_id=getattr(self, 'operator_id', None), operator_username=getattr(self, 'operator_username', 'op_5421'), station=getattr(self, 'station', 'PHQ'))
                    except Exception as te:
                        print(f'[CameraStreamManager {self.camera_id}] Trail record error: {te}')
            with self._lock:
                for ad in self._cached_displays:
                    if ad.get('vehicle_id') == v_rec.vehicle_id or ad.get('track_id') in getattr(v_rec, 'linked_track_ids', []):
                        ad['disp_plate'] = disp_plate
                        ad['final_conf_pct'] = final_conf_pct
                        ad['is_valid'] = is_valid
                        ad['alert_state'] = v_rec.alert_state
                        ad['alert_reason'] = getattr(v_rec, 'alert_reason', '')
                        ad['is_analyzing'] = False
        except Exception as ex:
            print(f'[CameraStreamManager {self.camera_id}] Sighting callback error: {ex}')

    def inspect_target_at_coords(self, norm_x: float, norm_y: float) -> Optional[Dict[str, Any]]:
        with self._lock:
            frame = self.last_frame.copy() if self.last_frame is not None else None
            cached_displays = list(self._cached_displays)
            cached_persons = list(self._cached_persons)
            frame_idx = self.frame_count
            cam_id = self.camera_id
            location = self.location
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if frame is None or getattr(frame, 'size', 0) == 0:
            return None
        fh, fw = frame.shape[:2]
        cx = int(norm_x * fw)
        cy = int(norm_y * fh)
        pad = 22
        t_click = time.time()
        matched_target = None
        target_kind = None
        matched_box = None
        matched_pbox = None
        for ad in cached_displays:
            ai_time = ad.get('ai_time', t_click)
            age = max(0.0, t_click - ai_time)
            if age > 0.45:
                continue
            dx = max(-120, min(120, int(ad.get('vx', 0.0) * age)))
            dy = max(-120, min(120, int(ad.get('vy', 0.0) * age)))
            pbox = ad.get('plate_bbox')
            if pbox:
                px1 = max(0, min(fw - 1, pbox[0] + dx))
                px2 = max(0, min(fw - 1, pbox[1] + dx))
                py1 = max(0, min(fh - 1, pbox[2] + dy))
                py2 = max(0, min(fh - 1, pbox[3] + dy))
                px1, py1, px2, py2 = (max(0, min(fw - 1, pbox[0] + dx)), max(0, min(fh - 1, pbox[1] + dy)), max(0, min(fw - 1, pbox[2] + dx)), max(0, min(fh - 1, pbox[3] + dy)))
                if px1 - pad <= cx <= px2 + pad and py1 - pad <= cy <= py2 + pad:
                    matched_target = ad
                    target_kind = 'VEHICLE'
                    matched_pbox = (px1, py1, px2, py2)
                    vbox = ad.get('bbox')
                    if vbox:
                        matched_box = (max(0, min(fw - 1, vbox[0] + dx)), max(0, min(fh - 1, vbox[1] + dy)), max(0, min(fw - 1, vbox[2] + dx)), max(0, min(fh - 1, vbox[3] + dy)))
                    break
        if not matched_target:
            pass
        if not matched_target:
            for ad in cached_displays:
                ai_time = ad.get('ai_time', t_click)
                age = max(0.0, t_click - ai_time)
                if age > 0.45:
                    continue
                dx = max(-120, min(120, int(ad.get('vx', 0.0) * age)))
                dy = max(-120, min(120, int(ad.get('vy', 0.0) * age)))
                vbox = ad.get('bbox')
                if vbox:
                    vx1 = max(0, min(fw - 1, vbox[0] + dx))
                    vy1 = max(0, min(fh - 1, vbox[1] + dy))
                    vx2 = max(0, min(fw - 1, vbox[2] + dx))
                    vy2 = max(0, min(fh - 1, vbox[3] + dy))
                    if vx1 - pad <= cx <= vx2 + pad and vy1 - pad <= cy <= vy2 + pad:
                        matched_target = ad
                        target_kind = 'VEHICLE'
                        matched_box = (vx1, vy1, vx2, vy2)
                        pbox = ad.get('plate_bbox')
                        if pbox:
                            matched_pbox = (max(0, min(fw - 1, pbox[0] + dx)), max(0, min(fh - 1, pbox[1] + dy)), max(0, min(fw - 1, pbox[2] + dx)), max(0, min(fh - 1, pbox[3] + dy)))
                        break
        if not matched_target:
            pass
        if not matched_target:
            for ad in cached_displays:
                vbox = ad.get('bbox')
                if vbox:
                    vx1, vy1, vx2, vy2 = vbox
                    if vx1 - pad - 12 <= cx <= vx2 + pad + 12 and vy1 - pad - 12 <= cy <= vy2 + pad + 12:
                        matched_target = ad
                        target_kind = 'VEHICLE'
                        matched_box = (vx1, vy1, vx2, vy2)
                        matched_pbox = ad.get('plate_bbox')
                        break
        if not matched_target:
            pass
        if not matched_target:
            return None

        def encode_b64(img: Optional[np.ndarray], quality: int=80) -> str:
            if img is None or getattr(img, 'size', 0) == 0:
                return ''
            ret, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ret:
                return ''
            return 'data:image/jpeg;base64,' + base64.b64encode(buf.tobytes()).decode('utf-8')
        scene_preview = frame.copy()
        if target_kind == 'VEHICLE':
            vx1, vy1, vx2, vy2 = matched_box if matched_box else [int(v) for v in matched_target.get('bbox', (0, 0, fw, fh))]
            vx1, vy1 = (max(0, vx1), max(0, vy1))
            vx2, vy2 = (min(fw, vx2), min(fh, vy2))
            v_rec = self._pipeline.track_merger.vehicles.get(matched_target.get('vehicle_id')) if self._pipeline and getattr(self._pipeline, 'track_merger', None) and ('vehicle_id' in matched_target) else None
            vehicle_crop = getattr(v_rec, 'best_vehicle_crop', None)
            if vehicle_crop is None or getattr(vehicle_crop, 'size', 0) == 0:
                vehicle_crop = frame[vy1:vy2, vx1:vx2] if vx2 > vx1 and vy2 > vy1 else None
            plate_crop = getattr(v_rec, 'best_crop', None)
            pbox = matched_pbox or matched_target.get('plate_bbox')
            if plate_crop is None or getattr(plate_crop, 'size', 0) == 0:
                if pbox:
                    px1, py1, px2, py2 = [int(v) for v in pbox]
                    px1, py1 = (max(0, px1), max(0, py1))
                    px2, py2 = (min(fw, px2), min(fh, py2))
                    if px2 > px1 and py2 > py1:
                        plate_crop = frame[py1:py2, px1:px2]
            cv2.rectangle(scene_preview, (vx1, vy1), (vx2, vy2), (255, 140, 0), 1)
            if pbox:
                cv2.rectangle(scene_preview, (int(pbox[0]), int(pbox[1])), (int(pbox[2]), int(pbox[3])), (16, 185, 129), 1)
            disp_plate = matched_target.get('disp_plate') or 'ANALYZING...'
            raw_c = float(matched_target.get('confidence', matched_target.get('det_confidence', 0.92)))
            conf_val = round(raw_c * (100.0 if raw_c <= 1.0 else 1.0), 1)
            linked_cap_id = None
            if self.captured_db and disp_plate and (disp_plate != 'ANALYZING...'):
                try:
                    recs = self.captured_db.get_recent(limit=1, search=disp_plate)
                    if recs:
                        linked_cap_id = recs[0].get('id')
                except Exception:
                    pass
            return {'type': 'VEHICLE', 'track_id': f"VEH-{matched_target.get('track_id', 1)}", 'raw_track_id': matched_target.get('track_id', 1), 'class_name': matched_target.get('cls_name', 'Vehicle').capitalize(), 'confidence': conf_val, 'plate_number': disp_plate, 'ocr_confidence': matched_target.get('final_conf_pct', 0.0), 'alert_state': matched_target.get('alert_state', 'NORMAL'), 'alert_reason': matched_target.get('alert_reason'), 'frame_number': frame_idx, 'timestamp': now_str, 'camera_id': cam_id, 'location': location, 'raw_scene_base64': encode_b64(scene_preview, 75), 'target_crop_base64': encode_b64(vehicle_crop, 85), 'target_crop_label': 'Vehicle Body Crop', 'sub_crop_base64': encode_b64(plate_crop, 90) if plate_crop is not None else '', 'sub_crop_label': 'License Plate Crop' if plate_crop is not None else '', 'bbox': [vx1, vy1, vx2, vy2], 'plate_bbox': list(pbox) if pbox else None, 'linked_capture_id': linked_cap_id}
        else:
            return {'error': 'No vehicle found at this position'}

    def _render_hud_overlay(self, frame: np.ndarray) -> np.ndarray:
        display_frame = frame.copy()
        with self._lock:
            cached_persons = list(self._cached_persons)
            cached_displays = list(self._cached_displays)
            people_cnt = self.current_people_count
        if self.overlay_layers.get('person_box', True):
            for p in cached_persons:
                bx1, by1, bx2, by2 = p.get('bbox', (0, 0, 0, 0))
                p_col = (34, 197, 94)
                cv2.rectangle(display_frame, (bx1, by1), (bx2, by2), p_col, 1)
                p_txt = 'Person'
                (ptw, pth), _ = cv2.getTextSize(p_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                cv2.rectangle(display_frame, (bx1, max(0, by1 - pth - 4)), (bx1 + ptw + 4, by1), p_col, -1)
                cv2.putText(display_frame, p_txt, (bx1 + 2, max(pth + 1, by1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        show_veh = self.overlay_layers.get('vehicle_box', True)
        show_track = self.overlay_layers.get('bytetrack', True)
        show_plate = self.overlay_layers.get('plate_box', True)
        show_ocr = self.overlay_layers.get('ocr_text', True)
        t_display = time.time()
        f_h, f_w = display_frame.shape[:2]
        active_veh_count = 0
        is_file_source = getattr(self, '_is_file_source', False)
        for ad in cached_displays:
            ai_time = ad.get('ai_time', t_display)
            age = max(0.0, t_display - ai_time)
            if not is_file_source and age > 0.45:
                continue
            raw_vbox = ad.get('bbox', (0, 0, 0, 0))
            vx1, vy1, vx2, vy2 = raw_vbox
            if is_file_source:
                dx = 0
                dy = 0
            else:
                vx_speed = ad.get('vx', 0.0)
                vy_speed = ad.get('vy', 0.0)
                dx = max(-120, min(120, int(vx_speed * age)))
                dy = max(-120, min(120, int(vy_speed * age)))
            vx1 = max(0, min(f_w - 1, vx1 + dx))
            vx2 = max(0, min(f_w - 1, vx2 + dx))
            vy1 = max(0, min(f_h - 1, vy1 + dy))
            vy2 = max(0, min(f_h - 1, vy2 + dy))
            if vx2 - vx1 < 15 or vy2 - vy1 < 15:
                continue
            active_veh_count += 1
            tid = ad.get('track_id', 1)
            cls_name = ad.get('cls_name', 'Vehicle').capitalize()
            alert_st = ad.get('alert_state', 'NORMAL')
            veh_color = (255, 140, 0)
            if show_veh:
                cv2.rectangle(display_frame, (vx1, vy1), (vx2, vy2), veh_color, 1)
            if show_track:
                veh_lbl = f'{cls_name}'
                (vtw, vth), _ = cv2.getTextSize(veh_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                cv2.rectangle(display_frame, (vx1, max(0, vy1 - vth - 4)), (vx1 + vtw + 4, vy1), veh_color, -1)
                cv2.putText(display_frame, veh_lbl, (vx1 + 2, max(vth + 1, vy1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
            pbox = ad.get('plate_bbox')
            if pbox is not None:
                px1, py1, px2, py2 = pbox
                px1 = max(0, min(f_w - 1, px1 + dx))
                px2 = max(0, min(f_w - 1, px2 + dx))
                py1 = max(0, min(f_h - 1, py1 + dy))
                py2 = max(0, min(f_h - 1, py2 + dy))
                disp_plate = ad.get('disp_plate')
                final_conf_pct = ad.get('final_conf_pct', 0.0)
                is_valid = ad.get('is_valid', False)
                if disp_plate:
                    if alert_st == 'HOTLIST':
                        plate_color = (0, 0, 255)
                        plate_lbl = f'HOTLIST: {disp_plate}'
                    elif alert_st == 'SUSPECT':
                        plate_color = (0, 140, 255)
                        plate_lbl = f'SUSPECT: {disp_plate}'
                    else:
                        plate_color = (16, 185, 129) if is_valid else (11, 158, 245)
                        plate_lbl = f'{disp_plate}'
                    if show_plate:
                        cv2.rectangle(display_frame, (px1, py1), (px2, py2), plate_color, 1)
                    if show_ocr:
                        (ptw, pth), _ = cv2.getTextSize(plate_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                        cv2.rectangle(display_frame, (px1, max(0, py1 - pth - 4)), (px1 + ptw + 4, py1), plate_color, -1)
                        text_col = (255, 255, 255) if alert_st in ('HOTLIST', 'SUSPECT') else (0, 0, 0)
                        cv2.putText(display_frame, plate_lbl, (px1 + 2, max(pth + 1, py1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, text_col, 1)
                elif ad.get('is_analyzing'):
                    analyzing_color = (0, 165, 255)
                    if show_plate:
                        cv2.rectangle(display_frame, (px1, py1), (px2, py2), analyzing_color, 1)
                    if show_ocr:
                        plate_lbl = 'Analyzing...'
                        (ptw, pth), _ = cv2.getTextSize(plate_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)
                        cv2.rectangle(display_frame, (px1, max(0, py1 - pth - 4)), (px1 + ptw + 4, py1), analyzing_color, -1)
                        cv2.putText(display_frame, plate_lbl, (px1 + 2, max(pth + 1, py1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 0), 1)
        if self.overlay_layers.get('people_counter', True):
            hud_txt = f'PEOPLE: {people_cnt} | VEHICLES: {active_veh_count}'
            (htw, hth), _ = cv2.getTextSize(hud_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            f_w = display_frame.shape[1]
            f_h = display_frame.shape[0]
            pad = 8
            hx2 = f_w - 16
            hx1 = hx2 - htw - pad * 2
            hy1 = 14
            hy2 = hy1 + hth + pad * 2
            if hy2 <= f_h and hx2 <= f_w and (hx1 >= 0):
                roi = display_frame[hy1:hy2, hx1:hx2]
                badge = np.full_like(roi, (15, 23, 42))
                cv2.addWeighted(badge, 0.85, roi, 0.15, 0, roi)
                cv2.rectangle(display_frame, (hx1, hy1), (hx2, hy2), (56, 189, 248), 1)
                cv2.putText(display_frame, hud_txt, (hx1 + pad, hy1 + hth + pad - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        return display_frame

    def _worker_loop(self):
        """Dedicated background thread acquiring video frames smoothly and rendering OSD."""
        cap = self._create_capture()
        if not cap.isOpened():
            self.is_running = False
            return
        is_file = isinstance(self.source, str) and os.path.isfile(self.source)
        self._is_file_source = is_file
        file_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if file_fps <= 0 or file_fps > 60:
            file_fps = 25.0
        self.source_fps = file_fps
        target_interval = 1.0 / file_fps
        frame_idx = 0
        fps_timer = time.time()
        fps_frame_count = 0
        while not self._stop_event.is_set():
            t_frame_start = time.time()
            if self.is_paused:
                time.sleep(0.04)
                continue
            ret, frame = cap.read()
            if not ret:
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret:
                        cap.release()
                        cap = self._create_capture()
                        time.sleep(0.01)
                        continue
                    with self._lock:
                        self.passage_session_id = f'stream_{self.camera_id}_{int(time.time())}'
                        self.passage_captures.clear()
                        self.passage_confidences.clear()
                        self.logged_sightings_in_passage.clear()
                        self._track_velocities.clear()
                    if self._pipeline:
                        try:
                            self._pipeline.track_merger.reset()
                        except Exception:
                            pass
                else:
                    now_t = time.time()
                    if now_t - self.last_successful_frame_time > 2.5:
                        self.connection_status = 'RECONNECTING'
                        self.reconnect_attempt += 1
                        backoff_sec = min(10.0, 1.2 ** min(self.reconnect_attempt, 10))
                        print(f'[Watchdog {self.camera_id}] Live RTSP/CCTV connection interrupted! Auto-heal attempt {self.reconnect_attempt} (Backoff {round(backoff_sec, 1)}s)...')
                        if self.last_annotated_frame is not None:
                            recon_frame = self.last_annotated_frame.copy()
                            recon_frame = cv2.addWeighted(recon_frame, 0.4, np.zeros_like(recon_frame), 0.6, 0)
                            cv2.rectangle(recon_frame, (15, 60), (recon_frame.shape[1] - 15, 150), (15, 23, 42), -1)
                            cv2.rectangle(recon_frame, (15, 60), (recon_frame.shape[1] - 15, 150), (0, 140, 255), 1)
                            cv2.putText(recon_frame, f'RECONNECTING CCTV FEED [ATTEMPT {self.reconnect_attempt}]', (30, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                            cv2.putText(recon_frame, f'Source: {str(self.source)[:45]} | Next retry in {round(backoff_sec, 1)}s...', (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1)
                            with self._lock:
                                self.last_annotated_frame = recon_frame
                        try:
                            cap.release()
                        except Exception:
                            pass
                        time.sleep(backoff_sec)
                        cap = self._create_capture()
                        if cap.isOpened():
                            ret_test, frame_test = cap.read()
                            if ret_test and frame_test is not None:
                                print(f'[Watchdog {self.camera_id}] Stream auto-healed successfully on attempt {self.reconnect_attempt}!')
                                self.connection_status = 'CONNECTED'
                                self.reconnect_attempt = 0
                                self.last_successful_frame_time = time.time()
                                continue
                    time.sleep(0.04)
                    continue
            frame_idx += 1
            self.frame_count = frame_idx
            fps_frame_count += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                self.current_fps = fps_frame_count / elapsed
                fps_frame_count = 0
                fps_timer = time.time()
            should_analyze = self.anpr_enabled and frame_idx % self.target_frame_interval == 0
            if should_analyze:
                if not self._ai_busy:
                    self._latest_ai_frame = frame.copy()
                    self._latest_ai_frame_idx = frame_idx
                    self._ai_busy = True
                    self._ai_trigger_event.set()
            display_frame = self._render_hud_overlay(frame) if self.anpr_enabled else frame.copy()
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(display_frame, f'REC [LIVE]  {now_str}', (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            cv2.putText(display_frame, f'{self.camera_id}: {self.location.upper()} | {round(self.current_fps, 1)} FPS', (20, display_frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            mode_tag = 'ANPR ENGAGED' if self.anpr_enabled else 'RAW SURVEILLANCE'
            mode_color = (0, 255, 0) if self.anpr_enabled else (200, 200, 200)
            cv2.putText(display_frame, mode_tag, (display_frame.shape[1] - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, mode_color, 2)
            with self._lock:
                self.last_frame = frame
                self.last_annotated_frame = display_frame
            if is_file:
                elapsed_frame = time.time() - t_frame_start
                sleep_sec = target_interval - elapsed_frame
                if sleep_sec > 0.001:
                    time.sleep(sleep_sec)
            else:
                time.sleep(0.002)
        cap.release()
        self.is_running = False

    def _ai_worker_loop(self):
        while not self._stop_event.is_set():
            triggered = self._ai_trigger_event.wait(timeout=0.1)
            if self._stop_event.is_set():
                break
            if not triggered or self._latest_ai_frame is None:
                continue
            self._ai_trigger_event.clear()
            self._ai_busy = True
            ai_frame = self._latest_ai_frame
            frame_idx = self._latest_ai_frame_idx
            self._latest_ai_frame = None
            new_displays = []
            new_persons = []
            try:
                if self.anpr_enabled:
                    try:
                        pipeline = self._get_pipeline()
                        timestamp = frame_idx / 30.0
                        raw_displays = pipeline.process_frame(ai_frame, frame_idx=frame_idx, timestamp=timestamp)
                        if hasattr(pipeline, 'vehicle_detector'):
                            vd = pipeline.vehicle_detector
                            new_persons = list(getattr(vd, 'last_persons', []))
                            if not new_persons and (not getattr(vd, 'person_classes', None)):
                                try:
                                    from src.detection.model_registry import registry
                                    p_model = registry.get_person_detector()
                                    if p_model is not None:
                                        p_res = p_model(ai_frame, conf=0.35, verbose=False)
                                        if p_res and len(p_res) > 0 and (p_res[0].boxes is not None):
                                            p_boxes = p_res[0].boxes.xyxy.cpu().numpy()
                                            p_confs = p_res[0].boxes.conf.cpu().numpy()
                                            p_clses = p_res[0].boxes.cls.cpu().numpy().astype(int)
                                            p_names = getattr(p_model, 'names', {})
                                            for bi in range(len(p_boxes)):
                                                cid = int(p_clses[bi])
                                                cname = str(p_names.get(cid, '')).lower()
                                                if cid == 0 or 'person' in cname or 'pedestrian' in cname:
                                                    new_persons.append({'track_id': bi + 1, 'bbox': (int(p_boxes[bi][0]), int(p_boxes[bi][1]), int(p_boxes[bi][2]), int(p_boxes[bi][3])), 'conf': float(p_confs[bi]), 'cls_id': cid, 'cls_name': 'person'})
                                except Exception:
                                    pass
                            self.current_people_count = len(new_persons)
                            self.total_unique_people = len(getattr(vd, 'unique_person_tracks', []))
                        frame_h, frame_w = ai_frame.shape[:2]
                        t_ai_now = time.time()
                        for ad in raw_displays:
                            tid = ad.get('track_id')
                            vbox = ad.get('bbox', (0, 0, 0, 0))
                            if tid is not None and tid in self._track_velocities:
                                prev_vx, prev_vy, prev_t, prev_vbox = self._track_velocities[tid]
                                dt = max(0.02, t_ai_now - prev_t)
                                cur_vx = ((vbox[0] + vbox[2]) / 2.0 - (prev_vbox[0] + prev_vbox[2]) / 2.0) / dt
                                cur_vy = ((vbox[1] + vbox[3]) / 2.0 - (prev_vbox[1] + prev_vbox[3]) / 2.0) / dt
                                vx = 0.65 * cur_vx + 0.35 * prev_vx
                                vy = 0.65 * cur_vy + 0.35 * prev_vy
                            else:
                                vx = 0.0
                                vy = 0.0
                            if tid is not None:
                                self._track_velocities[tid] = (vx, vy, t_ai_now, vbox)
                            ad['vx'] = vx
                            ad['vy'] = vy
                            ad['ai_time'] = t_ai_now
                            pbox = ad.get('plate_bbox')
                            v_rec = pipeline.track_merger.vehicles.get(ad.get('vehicle_id')) if 'vehicle_id' in ad else None
                            if v_rec:
                                v_rec.live_observation_count = getattr(v_rec, 'live_observation_count', 0) + 1
                            reading = v_rec.readings[-1] if v_rec and v_rec.readings else None
                            if v_rec and v_rec.final_plate or (reading and reading.ocr_confidence >= 0.4):
                                norm_plate = v_rec.final_plate if v_rec and v_rec.final_plate else reading.normalized_text if reading and reading.normalized_text and (reading.normalized_text != 'UNREADABLE') else ''
                                disp_plate = v_rec.display_plate if v_rec and v_rec.display_plate else pipeline.normalizer.format_display(norm_plate) if norm_plate else ''
                                final_conf_pct = round(float(v_rec.final_confidence) * 100, 1) if v_rec and v_rec.final_confidence else round(reading.ocr_confidence * 100, 1) if reading else 0.0
                                is_valid = v_rec.is_verified if v_rec else reading.is_valid_format if reading else False
                                ad['disp_plate'] = disp_plate
                                ad['final_conf_pct'] = final_conf_pct
                                ad['is_valid'] = is_valid
                                db_match, match_type = self.vehicle_db.match_plate_with_type(norm_plate) if self.vehicle_db and norm_plate else (None, 'NONE')
                                hotlist_str = None
                                now_ai_t = time.time()
                                if match_type == 'EXACT':
                                    ad['alert_state'] = 'HOTLIST'
                                    if v_rec:
                                        v_rec.alert_state = 'HOTLIST'
                                        v_rec.is_saturated = True
                                    hotlist_str = f"POLICE CASE: {db_match.get('offence_type', 'Crime')} | FIR: {db_match.get('fir_number', 'N/A')}" if db_match.get('involved_in_case') else f"LOST VEHICLE: {db_match.get('lost_location', 'Unknown')}"
                                    ad['alert_reason'] = hotlist_str
                                    if v_rec:
                                        v_rec.alert_reason = hotlist_str
                                    last_alert_t = self.audit_alert_cooldown.get(norm_plate, 0.0)
                                    if now_ai_t - last_alert_t > 30.0 and self.audit_db:
                                        self.audit_alert_cooldown[norm_plate] = now_ai_t
                                        try:
                                            p_crop_b64 = None
                                            if ai_frame is not None and getattr(ai_frame, 'size', 0) > 0 and pbox:
                                                fh, fw = ai_frame.shape[:2]
                                                c_img = ai_frame[max(0, pbox[1]):min(fh, pbox[3]), max(0, pbox[0]):min(fw, pbox[2])]
                                                if c_img.size > 0:
                                                    _, buf = cv2.imencode('.jpg', c_img)
                                                    p_crop_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
                                            self.audit_db.create_alert(alert_type='ANPR_HOTLIST', entity_identifier=norm_plate, display_name=disp_plate, case_info=hotlist_str, camera_id=self.camera_id, camera_location=self.location, origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=self.district, confidence=max(final_conf_pct, 85.0), snapshot_path=p_crop_b64)
                                        except Exception as e:
                                            print(f'[StreamManager] Alert error: {e}')
                                elif match_type == 'NEAR_MATCH':
                                    ad['alert_state'] = 'SUSPECT'
                                    if v_rec:
                                        v_rec.alert_state = 'SUSPECT'
                                    suspect_str = f"SUSPECT NEAR-MATCH: {db_match.get('vehicle_number')} (Sim: {db_match.get('similarity', 0.85)})"
                                    ad['alert_reason'] = suspect_str
                                    if v_rec:
                                        v_rec.alert_reason = suspect_str
                                    last_alert_t = self.audit_alert_cooldown.get(norm_plate, 0.0)
                                    if now_ai_t - last_alert_t > 30.0 and self.audit_db:
                                        self.audit_alert_cooldown[norm_plate] = now_ai_t
                                        try:
                                            p_crop_b64 = None
                                            if ai_frame is not None and getattr(ai_frame, 'size', 0) > 0 and pbox:
                                                fh, fw = ai_frame.shape[:2]
                                                c_img = ai_frame[max(0, pbox[1]):min(fh, pbox[3]), max(0, pbox[0]):min(fw, pbox[2])]
                                                if c_img.size > 0:
                                                    _, buf = cv2.imencode('.jpg', c_img)
                                                    p_crop_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
                                            self.audit_db.create_alert(alert_type='ANPR_SUSPECT', entity_identifier=norm_plate, display_name=disp_plate, case_info=suspect_str, camera_id=self.camera_id, camera_location=self.location, origin_district=db_match.get('district_name') or 'All Haryana', origin_station=db_match.get('police_station') or 'PHQ', spotting_district=self.district, confidence=max(final_conf_pct, 75.0), snapshot_path=p_crop_b64)
                                        except Exception as e:
                                            print(f'[StreamManager] Alert error: {e}')
                                else:
                                    ad['alert_state'] = 'NORMAL'
                                    if v_rec and v_rec.alert_state == 'SUSPECT':
                                        v_rec.alert_state = 'NORMAL'
                                        v_rec.alert_reason = ''
                                is_readable_plate = bool(norm_plate and norm_plate != 'UNREADABLE' and (final_conf_pct >= 40.0))
                                if v_rec and (is_readable_plate or v_rec.is_verified):
                                    px1, py1, px2, py2 = pbox if pbox is not None else (0, 0, frame_w, frame_h)
                                    vx1, vy1, vx2, vy2 = ad.get('bbox', (0, 0, frame_w, frame_h))
                                    passage_key = f'{self.passage_session_id}_{v_rec.vehicle_id}'
                                    ad['passage_key'] = passage_key
                                    ad['vehicle_id'] = getattr(v_rec, 'vehicle_id', None)
                                    ad['plate_number'] = norm_plate
                                    p_crop = getattr(v_rec, 'best_crop', None)
                                    if (p_crop is None or getattr(p_crop, 'size', 0) == 0) and pbox is not None:
                                        p_crop = ai_frame[max(0, py1):min(frame_h, py2), max(0, px1):min(frame_w, px2)]
                                    v_crop = getattr(v_rec, 'best_vehicle_crop', None)
                                    if v_crop is None or getattr(v_crop, 'size', 0) == 0:
                                        v_crop = ai_frame[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)]
                                    scene_evidence = getattr(v_rec, 'best_annotated_frame', None)
                                    if scene_evidence is None or getattr(scene_evidence, 'size', 0) == 0:
                                        scene_evidence = ai_frame
                                    best_r = getattr(v_rec, 'best_reading', None)
                                    if best_r is None and v_rec and v_rec.readings:
                                        best_r = max(v_rec.readings, key=lambda r: (r.ocr_confidence, getattr(r, 'blur_score', 0.0)))
                                    if best_r is None:
                                        best_r = reading
                                    evidence_list = []
                                    for ef in getattr(v_rec, 'evidence_frames', []):
                                        b64_crop = ''
                                        if getattr(ef, 'crop_image', None) is not None and ef.crop_image.size > 0:
                                            ok, buf = cv2.imencode('.jpg', ef.crop_image, [cv2.IMWRITE_JPEG_QUALITY, 90])
                                            if ok:
                                                b64_crop = base64.b64encode(buf).decode('utf-8')
                                        evidence_list.append({'frame_idx': ef.frame_idx, 'track_id': ef.track_id, 'text': ef.text, 'confidence': round(float(ef.confidence) * 100, 1), 'crop_base64': b64_crop})
                                    if self.captured_db:
                                        with self._lock:
                                            is_existing = passage_key in self.passage_captures
                                            existing_cid = self.passage_captures.get(passage_key)
                                            prev_conf = self.passage_confidences.get(passage_key, 0.0)
                                        if is_existing and existing_cid:
                                            if final_conf_pct > prev_conf:
                                                self.captured_db.update_capture(capture_id=existing_cid, confidence=final_conf_pct, plate_img=p_crop, vehicle_img=v_crop, annotated_img=scene_evidence, det_confidence=round(float(best_r.detection_confidence or 0.0) * 100, 1) if best_r else 0.0, ocr_confidence=round(float(best_r.ocr_confidence or 0.0) * 100, 1) if best_r else 0.0, blur_score=round(float(best_r.blur_score or 0.0), 1) if best_r else 0.0, display_plate=disp_plate, plate_number=norm_plate, is_hotlist_hit=match_type == 'EXACT', hotlist_info=hotlist_str or '', evidence_data=evidence_list, quality_gate_passed=is_valid, quality_reason='Live Camera Ingestion Apex Update', track_id=getattr(best_r, 'track_id', tid), vehicle_id=getattr(v_rec, 'vehicle_id', None))
                                                with self._lock:
                                                    self.passage_confidences[passage_key] = final_conf_pct
                                        else:
                                            new_cid = self.captured_db.add_capture(plate_number=norm_plate, display_plate=disp_plate, confidence=final_conf_pct, plate_img=p_crop, vehicle_img=v_crop, annotated_img=scene_evidence, location=self.location, source_type=f'stream_{self.source_type}', is_hotlist_hit=match_type == 'EXACT', hotlist_info=hotlist_str or '', blur_score=round(float(best_r.blur_score or 0.0), 1) if best_r else 0.0, aspect_ratio=round(float(getattr(best_r, 'aspect_ratio', 0.0)), 2) if best_r else 0.0, det_confidence=round(float(best_r.detection_confidence or 0.0) * 100, 1) if best_r else 0.0, ocr_confidence=round(float(best_r.ocr_confidence or 0.0) * 100, 1) if best_r else 0.0, format_type=getattr(v_rec, 'format_type', None) or (best_r.format_type if best_r else 'standard'), quality_gate_passed=is_valid, quality_reason='Live Camera Ingestion Verified' if is_valid else 'Needs Review (Format/Confidence)', evidence_data=evidence_list, is_fallback=final_conf_pct < 60.0, track_id=getattr(best_r, 'track_id', tid), vehicle_id=getattr(v_rec, 'vehicle_id', None), district=getattr(self, 'district', 'Panipat'), operator_id=getattr(self, 'operator_id', None), operator_username=getattr(self, 'operator_username', 'op_5421'), station=getattr(self, 'station', 'PHQ'))
                                            if new_cid and new_cid > 0:
                                                with self._lock:
                                                    self.passage_captures[passage_key] = new_cid
                                                    self.passage_confidences[passage_key] = final_conf_pct
                                                    self.logged_sightings_in_passage.add(passage_key)
                                    if match_type == 'EXACT' and db_match and self.trail_db:
                                        trail_key = f'trail_{passage_key}'
                                        if trail_key not in self.logged_sightings_in_passage:
                                            self.logged_sightings_in_passage.add(trail_key)
                                            self.trail_db.record_sighting(vehicle_id=db_match['id'], registration_number=norm_plate, camera_id=self.camera_id, location=self.location, gps_coords=self.gps_coords, captured_at=datetime.datetime.now().astimezone().isoformat(), confidence=round(float(v_rec.final_confidence) * 100, 1), plate_img=p_crop, vehicle_img=v_crop, passage_id=passage_key, min_cooldown_seconds=4.0, district=getattr(self, 'district', 'Panipat'), operator_id=getattr(self, 'operator_id', None), operator_username=getattr(self, 'operator_username', 'op_5421'), station=getattr(self, 'station', 'PHQ'))
                            if v_rec and getattr(v_rec, 'live_observation_count', 0) >= 3 and (not getattr(v_rec, 'logged_fallback', False)) and not v_rec.final_plate:
                                passage_key = f'{self.passage_session_id}_{v_rec.vehicle_id}'
                                ad['passage_key'] = passage_key
                                ad['vehicle_id'] = getattr(v_rec, 'vehicle_id', None)
                                ad['plate_number'] = 'UNREADABLE'
                                vx1, vy1, vx2, vy2 = ad.get('bbox', (0, 0, frame_w, frame_h))
                                v_crop = getattr(v_rec, 'best_vehicle_crop', None)
                                if v_crop is None or getattr(v_crop, 'size', 0) == 0:
                                    v_crop = ai_frame[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)]
                                if self.captured_db and v_crop is not None and (getattr(v_crop, 'size', 0) > 0):
                                    fb_cid = self.captured_db.add_capture(plate_number='UNREADABLE', display_plate='UNREADABLE', confidence=0.0, plate_img=None, vehicle_img=v_crop, annotated_img=ai_frame, location=self.location, source_type=f'stream_{self.source_type}', is_hotlist_hit=False, format_type='unreadable', quality_gate_passed=False, quality_reason='Live Stream Unreadable Vehicle', is_fallback=True, track_id=tid, vehicle_id=getattr(v_rec, 'vehicle_id', None), district=getattr(self, 'district', 'Panipat'), operator_id=getattr(self, 'operator_id', None), operator_username=getattr(self, 'operator_username', 'op_5421'), station=getattr(self, 'station', 'PHQ'))
                                    if fb_cid and fb_cid > 0:
                                        with self._lock:
                                            self.passage_captures[passage_key] = fb_cid
                                            self.passage_confidences[passage_key] = 0.0
                                            v_rec.logged_fallback = True
                            new_displays.append(ad)
                    except Exception as e:
                        print(f'[CameraStreamManager] Error during frame ANPR: {e}')
                with self._lock:
                    self._cached_displays = new_displays
                    self._cached_persons = new_persons
            except Exception as outer_err:
                print(f'[CameraStreamManager {self.camera_id}] AI error: {outer_err}')
            finally:
                time.sleep(0.005)
                self._ai_busy = False

    def generate_mjpeg_frames(self) -> Generator[bytes, None, None]:
        """Generator yielding MJPEG multipart frames for HTTP streaming."""
        last_yield_time = 0.0
        while self.is_running and (not self._stop_event.is_set()):
            if self.is_paused and self._cached_jpeg_bytes is not None:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + self._cached_jpeg_bytes + b'\r\n')
                time.sleep(0.08)
                continue
            t_now = time.time()
            source_fps = getattr(self, 'source_fps', 30.0) or 30.0
            min_yield_interval = 1.0 / max(10.0, min(60.0, source_fps))
            if t_now - last_yield_time < min_yield_interval:
                time.sleep(0.002)
                continue
            frame = None
            with self._lock:
                frame = self.last_annotated_frame if self.anpr_enabled else self.last_frame
            if frame is None:
                time.sleep(0.02)
                continue
            stream_img = frame.copy() if self.is_paused else frame
            dh, dw = frame.shape[:2]
            if self.is_paused:
                badge_img = stream_img.copy()
                sh, sw = badge_img.shape[:2]
                badge_text = 'PAUSED [INSPECTION]'
                (btw, bth), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_DUPLEX, 0.55, 1)
                bx1 = (sw - btw) // 2 - 12
                by1 = 10
                bx2 = bx1 + btw + 24
                by2 = by1 + bth + 14
                if by2 <= sh and bx2 <= sw and (bx1 >= 0):
                    roi = badge_img[by1:by2, bx1:bx2]
                    amber_bg = np.full_like(roi, (15, 140, 245))
                    cv2.addWeighted(amber_bg, 0.85, roi, 0.15, 0, roi)
                    cv2.rectangle(badge_img, (bx1, by1), (bx2, by2), (0, 200, 255), 1)
                    cv2.putText(badge_img, badge_text, (bx1 + 12, by1 + bth + 5), cv2.FONT_HERSHEY_DUPLEX, 0.55, (0, 0, 0), 1)
                stream_img = badge_img
            ret, buffer = cv2.imencode('.jpg', stream_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                continue
            last_yield_time = time.time()
            frame_bytes = buffer.tobytes()
            if self.is_paused:
                self._cached_jpeg_bytes = frame_bytes
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

class MultiCameraStreamManager:
    """
    Manages a pool of 4 camera stream slots (CAM-01, CAM-02, CAM-03, CAM-04)
    for 2x2 grid surveillance, with independent connections, locations, GPS,
    and ANPR toggles.
    """
    SLOTS = ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04']

    def __init__(self, vehicle_db: Optional[VehicleDB]=None, captured_db: Optional[CapturedDB]=None, trail_db: Optional[TrailDB]=None, config: Optional[ANPRConfig]=None, audit_db: Optional[Any]=None, district: str='Panipat', operator_username: str='op_5421', operator_id: Optional[str]=None, station: str='PHQ'):
        self.vehicle_db = vehicle_db
        self.captured_db = captured_db
        self.trail_db = trail_db
        self.config = config or ANPRConfig()
        self.audit_db = audit_db
        self.district = district
        self.operator_username = operator_username
        self.operator_id = operator_id
        self.station = station
        self.cameras: Dict[str, CameraStreamManager] = {}
        for slot in self.SLOTS:
            cam = CameraStreamManager(vehicle_db=self.vehicle_db, captured_db=self.captured_db, trail_db=self.trail_db, config=self.config, audit_db=self.audit_db, district=self.district)
            cam.camera_id = slot
            cam.location = f"Surveillance Post {slot.split('-')[-1]}"
            cam.operator_username = self.operator_username
            cam.operator_id = self.operator_id
            cam.station = self.station
            self.cameras[slot] = cam

    def switch_pipeline_models(self, vehicle_model: Optional[str]=None, plate_model: Optional[str]=None, ocr_model: Optional[str]=None):
        """Propagates model switch to all active camera stream slots."""
        for cam in self.cameras.values():
            try:
                cam.switch_pipeline_models(vehicle_model=vehicle_model, plate_model=plate_model, ocr_model=ocr_model)
            except Exception:
                pass

    def get_camera(self, camera_id: str='CAM-01') -> Optional[CameraStreamManager]:
        cid = camera_id.upper()
        if cid not in self.cameras and cid.startswith('CAM-'):
            cam = CameraStreamManager(vehicle_db=self.vehicle_db, captured_db=self.captured_db, trail_db=self.trail_db, config=self.config, audit_db=self.audit_db, district=self.district)
            cam.camera_id = cid
            cam.operator_username = self.operator_username
            cam.operator_id = self.operator_id
            cam.station = self.station
            self.cameras[cid] = cam
        return self.cameras.get(cid)

    def set_target_frame_interval(self, interval: int, camera_id: Optional[str]=None) -> int:
        """Propagates target frame cadence setting (1-20) to one or all cameras."""
        if camera_id and camera_id.upper() in self.cameras:
            return self.cameras[camera_id.upper()].set_target_frame_interval(interval)
        res = 1
        for cam in self.cameras.values():
            res = cam.set_target_frame_interval(interval)
        return res

    def start_stream(self, source: Union[int, str], source_type: str='webcam', camera_id: str='CAM-01', location: str='Main Surveillance Gate', gps_coords: Optional[str]=None, target_frame: int=1) -> bool:
        from src.camera.registry import resolve_camera, camera_metadata
        registered = resolve_camera(location=location)
        if registered:
            _, location, gps_coords = camera_metadata(registered)
            self.district = registered['district']
            self.station = registered['station']
        cam = self.get_camera(camera_id)
        if not cam:
            return False
        return cam.start_stream(source=source, source_type=source_type, camera_id=camera_id.upper(), location=location, gps_coords=gps_coords, target_frame=target_frame)

    def stop_stream(self, camera_id: Optional[str]=None):
        if camera_id is None or camera_id == '':
            cam = self.get_camera('CAM-01')
            if cam:
                cam.stop_stream()
        else:
            cam = self.get_camera(camera_id)
            if cam:
                cam.stop_stream()

    def stop_all(self):
        for cam in self.cameras.values():
            cam.stop_stream()

    def set_anpr_enabled(self, enabled: bool, camera_id: str='CAM-01') -> bool:
        cam = self.get_camera(camera_id)
        if cam:
            return cam.set_anpr_enabled(enabled)
        return False

    def set_overlay_layers(self, layers: Dict[str, bool], camera_id: Optional[str]=None) -> Dict[str, bool]:
        """Toggles selective visual HUD overlay elements across one or all cameras."""
        if camera_id and camera_id.upper() in self.cameras:
            return self.cameras[camera_id.upper()].set_overlay_layers(layers)
        last_layers = {}
        for cam in self.cameras.values():
            last_layers = cam.set_overlay_layers(layers)
        return last_layers

    def get_overlay_layers(self, camera_id: Optional[str]=None) -> Dict[str, bool]:
        cid = (camera_id or 'CAM-01').upper()
        cam = self.cameras.get(cid) or self.cameras.get('CAM-01')
        return cam.overlay_layers.copy() if cam else {'vehicle_box': True, 'bytetrack': True, 'plate_box': True, 'ocr_text': True, 'person_box': True, 'people_counter': True}

    def get_status(self, camera_id: Optional[str]=None) -> Dict[str, Any]:
        if camera_id and camera_id.upper() in self.cameras:
            cam = self.get_camera(camera_id)
            return cam.get_status() if cam else {}
        cameras_status = {cid: cam.get_status() for cid, cam in self.cameras.items()}
        primary = self.cameras.get('CAM-01')
        primary_status = primary.get_status() if primary else {}
        return {**primary_status, 'cameras': cameras_status, 'total_slots': len(self.cameras), 'active_count': sum((1 for c in self.cameras.values() if c.is_running))}

    def generate_mjpeg_frames(self, camera_id: str='CAM-01'):
        cam = self.get_camera(camera_id)
        if not cam or not cam.is_running:
            raise ValueError(f'Camera {camera_id} is not active')
        return cam.generate_mjpeg_frames()

    def get_snapshot(self, camera_id: str='CAM-04') -> Optional[np.ndarray]:
        """Returns the most recent clean raw frame from the specified camera or any active camera."""
        cid = (camera_id or 'CAM-04').upper()
        cam = self.get_camera(cid)
        if cam and cam.last_frame is not None:
            with cam._lock:
                return cam.last_frame.copy() if cam.last_frame is not None else None
        for c in self.cameras.values():
            if c.is_running and c.last_frame is not None:
                with c._lock:
                    return c.last_frame.copy() if c.last_frame is not None else None
        try:
            temp_cap = cv2.VideoCapture(0)
            if temp_cap.isOpened():
                ret, frame = temp_cap.read()
                temp_cap.release()
                if ret and frame is not None:
                    return frame
        except Exception as e:
            logger.warning(f'Fallback direct webcam capture failed: {e}')
        return None

    def toggle_pause(self, camera_id: Optional[str]=None, paused: Optional[bool]=None) -> Dict[str, Any]:
        """
        Toggles or sets pause state for a specific camera or all active cameras.
        If camera_id is None, 'ALL', or empty, toggles/sets all active cameras.
        """
        cid = camera_id.strip().upper() if camera_id else None
        if cid and cid in self.cameras:
            cam = self.cameras[cid]
            is_p = cam.toggle_pause(paused=paused)
            return {cid: {'is_paused': is_p, 'status': 'paused' if is_p else 'live'}}
        elif cid == 'ALL' or not cid:
            res = {}
            for k, c in self.cameras.items():
                if c.is_running:
                    is_p = c.toggle_pause(paused=paused)
                    res[k] = {'is_paused': is_p, 'status': 'paused' if is_p else 'live'}
            return res
        return {}

    @property
    def is_running(self) -> bool:
        cam = self.get_camera('CAM-01')
        return cam.is_running if cam else False

    @property
    def is_paused(self) -> bool:
        cam = self.get_camera('CAM-01')
        return cam.is_paused if cam else False

    @property
    def anpr_enabled(self) -> bool:
        cam = self.get_camera('CAM-01')
        return cam.anpr_enabled if cam else True

    def inspect_target_at_coords(self, camera_id: Optional[str], norm_x: float, norm_y: float) -> Optional[Dict[str, Any]]:
        """Finds active camera and inspects target at normalized click coordinates."""
        cid = (camera_id or 'CAM-01').strip().upper()
        cam = self.get_camera(cid)
        if not cam or not cam.is_running:
            for c in self.cameras.values():
                if c.is_running:
                    cam = c
                    break
        if not cam or not cam.is_running:
            return None
        return cam.inspect_target_at_coords(norm_x, norm_y)
