PUBLIC_FIELDS = {'is_hotlist_hit', 'display_plate', 'plate_pic_path', 'clip_name', 'operator_username', 'evidence_video_path', 'vehicle_pic_path', 'location', 'blur_score', 'preprocessing_json', 'confidence', 'gps_coords', 'hotlist_info', 'evidence_json', 'track_id', 'violation_id', 'district', 'violation_fine', 'vehicle_id', 'id', 'is_traffic_violation', 'created_epoch', 'quality_gate_passed', 'aspect_ratio', 'det_confidence', 'station', 'ocr_confidence', 'enhanced_pic_path', 'captured_at', 'linked_tracks', 'violation_details', 'quality_reason', 'annotated_pic_path', 'source_type', 'plate_number', 'operator_id', 'violation_type', 'format_type'}
'\nCaptured DB Module\nMaintains a strict FIFO ring buffer of the most recent 100 captured vehicle detections.\nSupports storing annotated images, plate/vehicle crops, and full technical quality metrics.\nAutomatically prunes the oldest records (entry #100+) and deletes disk image crops.\n'
from typing import List, Dict, Any, Optional, Union
import os
import json
import sqlite3
import datetime
import time
import uuid
import cv2
import numpy as np
from src.ocr.normalizer import IndianPlateNormalizer

class CapturedDB:

    def __init__(self, db_path: Optional[str]=None, max_records: int=100):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            data_dir = os.path.join(base_dir, 'data')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'captured_db.sqlite')
        self.db_path = db_path
        self.max_records = max_records
        self.crops_dir = os.path.join(os.path.dirname(self.db_path), 'captured_crops')
        os.makedirs(self.crops_dir, exist_ok=True)
        self.normalizer = IndianPlateNormalizer()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode = WAL;')
        conn.execute('PRAGMA busy_timeout = 30000;')
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('\n                CREATE TABLE IF NOT EXISTS captured_vehicles (id INTEGER PRIMARY KEY AUTOINCREMENT,\nplate_number TEXT NOT NULL,\ndisplay_plate TEXT NOT NULL,\nconfidence REAL NOT NULL,\nplate_pic_path TEXT,\nvehicle_pic_path TEXT,\nannotated_pic_path TEXT,\ncaptured_at TEXT NOT NULL,\nlocation TEXT NOT NULL,\nsource_type TEXT NOT NULL,\nis_hotlist_hit INTEGER DEFAULT 0,\nhotlist_info TEXT,\ncreated_epoch REAL NOT NULL,\nblur_score REAL DEFAULT 0.0,\naspect_ratio REAL DEFAULT 0.0,\ndet_confidence REAL DEFAULT 0.0,\nocr_confidence REAL DEFAULT 0.0,\nformat_type TEXT,\nquality_gate_passed INTEGER DEFAULT 1,\nquality_reason TEXT,\nevidence_json TEXT,\nenhanced_pic_path TEXT,\npreprocessing_json TEXT)\n            ')
            existing_cols = {col['name'] for col in cursor.execute('PRAGMA table_info(captured_vehicles)').fetchall()}
            for col_name, col_type in [('annotated_pic_path', 'TEXT'), ('blur_score', 'REAL DEFAULT 0.0'), ('aspect_ratio', 'REAL DEFAULT 0.0'), ('det_confidence', 'REAL DEFAULT 0.0'), ('ocr_confidence', 'REAL DEFAULT 0.0'), ('format_type', 'TEXT'), ('quality_gate_passed', 'INTEGER DEFAULT 1'), ('quality_reason', 'TEXT'), ('evidence_json', 'TEXT'), ('enhanced_pic_path', 'TEXT'), ('preprocessing_json', 'TEXT'), ('track_id', 'INTEGER'), ('linked_tracks', 'TEXT'), ('vehicle_id', 'INTEGER'), ('district', "TEXT DEFAULT 'Panipat'"), ('operator_id', 'INTEGER'), ('operator_username', "TEXT DEFAULT 'op_5421'"), ('station', "TEXT DEFAULT 'PHQ'"), ('evidence_video_path', 'TEXT'), ('is_traffic_violation', 'INTEGER DEFAULT 0'), ('violation_type', 'TEXT'), ('violation_fine', 'INTEGER DEFAULT 0'), ('violation_details', 'TEXT'), ('violation_id', 'TEXT'), ('gps_coords', 'TEXT'), ('clip_name', 'TEXT')]:
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f'ALTER TABLE captured_vehicles ADD COLUMN {col_name} {col_type}')
                    except Exception as e:
                        print(f'[CapturedDB Migration Notice]: {e}')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_captured_plate ON captured_vehicles (plate_number)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_captured_epoch ON captured_vehicles (created_epoch DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_captured_track ON captured_vehicles (track_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_captured_district ON captured_vehicles (district)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_captured_operator ON captured_vehicles (operator_username)')
            cursor.execute('SELECT id, evidence_json FROM captured_vehicles WHERE track_id IS NULL AND evidence_json IS NOT NULL')
            to_backfill = cursor.fetchall()
            for r in to_backfill:
                if r['evidence_json']:
                    try:
                        ev = json.loads(r['evidence_json'])
                        if isinstance(ev, list) and len(ev) > 0:
                            tids = [x.get('track_id') for x in ev if x.get('track_id') is not None]
                            if tids:
                                primary_tid = tids[0]
                                linked_str = ','.join((str(t) for t in sorted(set(tids))))
                                cursor.execute('UPDATE captured_vehicles SET track_id = ?, linked_tracks = ?, vehicle_id = ? WHERE id = ?', (primary_tid, linked_str, primary_tid, r['id']))
                    except Exception:
                        pass
            cursor.execute('UPDATE captured_vehicles SET vehicle_id = track_id WHERE vehicle_id IS NULL AND track_id IS NOT NULL')
            conn.commit()
        finally:
            conn.close()

    def _save_crop_image(self, img_data: Optional[Union[np.ndarray, bytes]], prefix: str, plate_clean: str) -> Optional[str]:
        if img_data is None:
            return None
        file_tag = f'{prefix}_{plate_clean}_{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg'
        abs_path = os.path.join(self.crops_dir, file_tag)
        try:
            if isinstance(img_data, np.ndarray):
                if img_data.size == 0:
                    return None
                cv2.imwrite(abs_path, img_data, [cv2.IMWRITE_JPEG_QUALITY, 90])
            elif isinstance(img_data, bytes):
                if len(img_data) == 0:
                    return None
                with open(abs_path, 'wb') as f:
                    f.write(img_data)
            else:
                return None
            return f'/data/captured_crops/{file_tag}'
        except Exception as e:
            print(f'[CapturedDB Error] Failed to save crop: {e}')
            return None

    def _remove_disk_file(self, web_path: Optional[str]):
        if not web_path:
            return
        fname = os.path.basename(web_path)
        full_path = os.path.join(self.crops_dir, fname)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception:
                pass

    def add_capture(self, plate_number: str, display_plate: Optional[str]=None, confidence: float=0.0, plate_img: Optional[Union[np.ndarray, bytes]]=None, vehicle_img: Optional[Union[np.ndarray, bytes]]=None, annotated_img: Optional[Union[np.ndarray, bytes]]=None, location: str='Main Surveillance Gate', source_type: str='video_upload', is_hotlist_hit: bool=False, hotlist_info: Optional[str]=None, blur_score: float=0.0, aspect_ratio: float=0.0, det_confidence: float=0.0, ocr_confidence: float=0.0, format_type: Optional[str]=None, quality_gate_passed: bool=True, quality_reason: Optional[str]=None, evidence_data: Optional[Union[str, List[Dict[str, Any]]]]=None, enhanced_img: Optional[Union[np.ndarray, bytes]]=None, preprocessing_data: Optional[Union[str, Dict[str, Any]]]=None, is_fallback: bool=False, track_id: Optional[int]=None, linked_tracks: Optional[str]=None, vehicle_id: Optional[int]=None, district: str='Panipat', operator_id: Optional[int]=None, operator_username: str='op_5421', station: str='PHQ', cooldown_seconds: float=20.0, evidence_video_path: Optional[str]=None, is_traffic_violation: bool=False, violation_type: Optional[str]=None, violation_fine: int=0, violation_details: Optional[str]=None, violation_id: Optional[str]=None, gps_coords: Optional[str]=None, clip_name: Optional[str]=None, captured_at: Optional[str]=None) -> int:
        from src.camera.registry import resolve_camera, camera_metadata
        registered = resolve_camera(location=location)
        if registered:
            _, location, gps_coords = camera_metadata(registered)
            district = registered['district']
            station = registered['station']
        '\n        Inserts a new capture record at #1 position (newest) with full metrics, annotated image, supporting evidence frames,\n        and enhanced plate image with de-skew diagnostics.\n        Enforces FIFO limit (strictly max 100 entries):\n        If count >= max_records, deletes the oldest record(s) and their image crops from disk.\n        '
        effective_conf = confidence if confidence > 0 else ocr_confidence
        if effective_conf < 60.0 and (not is_fallback):
            return -1
        cleaned = self.normalizer.clean_raw_text(plate_number)
        incomplete = cleaned != 'UNREADABLE' and not (self.normalizer.config.min_length <= len(cleaned) <= self.normalizer.config.max_length)
        if incomplete:
            cleaned='UNREADABLE';display_plate='UNREADABLE (INCOMPLETE OCR)'
            quality_gate_passed=False;is_hotlist_hit=False;hotlist_info=''
        disp = display_plate or self.normalizer.format_display(cleaned)
        now_epoch = time.time()
        now_str = captured_at if captured_at else datetime.datetime.fromtimestamp(now_epoch).strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(evidence_data, list):
            evidence_json_str = json.dumps(evidence_data)
        elif isinstance(evidence_data, str):
            evidence_json_str = evidence_data
        else:
            evidence_json_str = '[]'
        if isinstance(preprocessing_data, dict):

            def _safe_val(v):
                if isinstance(v, (np.ndarray, np.generic)):
                    return None
                return v
            clean_meta = {k: _safe_val(v) for k, v in preprocessing_data.items() if not isinstance(v, np.ndarray)}
            try:
                preprocessing_json_str = json.dumps(clean_meta)
            except Exception:
                preprocessing_json_str = '{}'
        elif isinstance(preprocessing_data, str):
            preprocessing_json_str = preprocessing_data
        else:
            preprocessing_json_str = None
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if cooldown_seconds > 0:
                match_id = None
                matched_row = None
                target_op = (operator_username or 'op_5421').strip().lower()
                target_dist = (district or 'Panipat').strip().lower()
                if cleaned and cleaned != 'UNREADABLE':
                    cursor.execute('SELECT id, confidence, ocr_confidence, evidence_json FROM captured_vehicles WHERE plate_number = ? AND location = ? AND (? - created_epoch) <= ? AND LOWER(operator_username) = ? AND LOWER(district) = ? ORDER BY id DESC LIMIT 1', (cleaned, location or 'Main Surveillance Gate', now_epoch, cooldown_seconds, target_op, target_dist))
                    matched_row = cursor.fetchone()
                    if matched_row:
                        match_id = matched_row['id']
                elif track_id is not None:
                    cursor.execute('SELECT id, confidence, ocr_confidence, evidence_json FROM captured_vehicles WHERE track_id = ? AND location = ? AND (? - created_epoch) <= ? AND LOWER(operator_username) = ? AND LOWER(district) = ? ORDER BY id DESC LIMIT 1', (track_id, location or 'Main Surveillance Gate', now_epoch, cooldown_seconds, target_op, target_dist))
                    matched_row = cursor.fetchone()
                    if matched_row:
                        match_id = matched_row['id']
                if match_id is not None:
                    merged_evidence = evidence_data
                    if matched_row and matched_row['evidence_json'] and evidence_data:
                        try:
                            old_ev = json.loads(matched_row['evidence_json']) if isinstance(matched_row['evidence_json'], str) else []
                            new_ev = evidence_data if isinstance(evidence_data, list) else json.loads(evidence_data)
                            seen_frames = set()
                            combined_ev = []
                            for ev_item in old_ev + new_ev:
                                f_idx = ev_item.get('frame_idx')
                                if f_idx not in seen_frames:
                                    seen_frames.add(f_idx)
                                    combined_ev.append(ev_item)
                            merged_evidence = combined_ev
                        except Exception:
                            pass
                    existing_conf = float(matched_row['confidence'] or 0.0) if matched_row else 0.0
                    should_upgrade_crops = effective_conf >= existing_conf
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self.update_capture(capture_id=match_id, confidence=max(effective_conf, existing_conf), plate_img=plate_img if should_upgrade_crops else None, vehicle_img=vehicle_img if should_upgrade_crops else None, annotated_img=annotated_img if should_upgrade_crops else None, det_confidence=det_confidence if should_upgrade_crops else None, ocr_confidence=ocr_confidence if should_upgrade_crops else None, blur_score=blur_score if should_upgrade_crops else None, display_plate=disp, plate_number=cleaned, is_hotlist_hit=is_hotlist_hit, hotlist_info=hotlist_info, evidence_data=merged_evidence, quality_gate_passed=quality_gate_passed, quality_reason=quality_reason or 'Consolidated Live Sighting', track_id=track_id, vehicle_id=vehicle_id, linked_tracks=linked_tracks, update_timestamp=True)
                    return match_id
            cursor.execute('SELECT COUNT(*) FROM captured_vehicles WHERE is_hotlist_hit = 0 AND is_traffic_violation = 0')
            routine_count = cursor.fetchone()[0]
            if routine_count >= self.max_records:
                excess = routine_count - self.max_records + 1
                cursor.execute('SELECT id, plate_pic_path, vehicle_pic_path, annotated_pic_path, enhanced_pic_path, evidence_video_path FROM captured_vehicles WHERE is_hotlist_hit = 0 AND is_traffic_violation = 0 ORDER BY id ASC LIMIT ?', (excess,))
                old_rows = cursor.fetchall()
                for old in old_rows:
                    self._remove_disk_file(old['plate_pic_path'])
                    self._remove_disk_file(old['vehicle_pic_path'])
                    if 'annotated_pic_path' in old.keys():
                        self._remove_disk_file(old['annotated_pic_path'])
                    if 'enhanced_pic_path' in old.keys():
                        self._remove_disk_file(old['enhanced_pic_path'])
                    if 'evidence_video_path' in old.keys():
                        self._remove_disk_file(old['evidence_video_path'])
                    cursor.execute('DELETE FROM captured_vehicles WHERE id = ?', (old['id'],))
            plate_pic_url = self._save_crop_image(plate_img, 'plate', cleaned)
            vehicle_pic_url = self._save_crop_image(vehicle_img, 'vehicle', cleaned)
            annotated_pic_url = self._save_crop_image(annotated_img, 'annotated', cleaned)
            enhanced_pic_url = self._save_crop_image(enhanced_img, 'enhanced', cleaned) if enhanced_img is not None else None
            cursor.execute('\n                INSERT INTO captured_vehicles (plate_number, display_plate, confidence, plate_pic_path, vehicle_pic_path, annotated_pic_path, captured_at, location, source_type, is_hotlist_hit, hotlist_info, created_epoch, blur_score, aspect_ratio, det_confidence, ocr_confidence, format_type, quality_gate_passed, quality_reason, evidence_json, enhanced_pic_path, preprocessing_json, track_id, linked_tracks, vehicle_id, district, operator_id, operator_username, station, evidence_video_path, is_traffic_violation, violation_type, violation_fine, violation_details, violation_id, gps_coords, clip_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            ', (cleaned, disp, round(float(confidence), 1), plate_pic_url, vehicle_pic_url, annotated_pic_url, now_str, location or 'Surveillance Feed', source_type or 'unknown', 1 if is_hotlist_hit else 0, hotlist_info or '', now_epoch, round(float(blur_score), 1), round(float(aspect_ratio), 2), round(float(det_confidence), 1), round(float(ocr_confidence), 1), format_type or 'Standard', 1 if quality_gate_passed else 0, quality_reason or 'Verified Crop', evidence_json_str, enhanced_pic_url, preprocessing_json_str, track_id, linked_tracks, vehicle_id, district or 'Panipat', operator_id, operator_username or 'op_5421', station or 'PHQ', evidence_video_path, 1 if is_traffic_violation else 0, violation_type, violation_fine, violation_details, violation_id, gps_coords, clip_name))
            conn.commit()
            capture_id = cursor.lastrowid
            self._record_trail_observation(capture_id)
            return capture_id
        finally:
            conn.close()
    add_detection = add_capture

    def update_capture(self, capture_id: int, confidence: Optional[float]=None, plate_img: Optional[Union[np.ndarray, bytes]]=None, vehicle_img: Optional[Union[np.ndarray, bytes]]=None, annotated_img: Optional[Union[np.ndarray, bytes]]=None, det_confidence: Optional[float]=None, ocr_confidence: Optional[float]=None, blur_score: Optional[float]=None, display_plate: Optional[str]=None, plate_number: Optional[str]=None, is_hotlist_hit: Optional[bool]=None, hotlist_info: Optional[str]=None, evidence_data: Optional[Union[str, List[Dict[str, Any]]]]=None, quality_gate_passed: Optional[bool]=None, quality_reason: Optional[str]=None, track_id: Optional[int]=None, vehicle_id: Optional[int]=None, linked_tracks: Optional[str]=None, update_timestamp: bool=True, evidence_video_path: Optional[str]=None, is_traffic_violation: Optional[bool]=None, violation_type: Optional[str]=None, violation_fine: Optional[int]=None, violation_details: Optional[str]=None, violation_id: Optional[str]=None) -> bool:
        """
        Updates an existing capture entry in-place with sharper crops and peak metrics.
        Prevents duplicate rows while elevating evidence quality to apex levels.
        """
        if capture_id <= 0:
            return False
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM captured_vehicles WHERE id = ?', (capture_id,))
            row = cursor.fetchone()
            if not row:
                return False
            cleaned = self.normalizer.clean_raw_text(plate_number) if plate_number else row['plate_number']
            updates = []
            params = []
            if plate_number is not None:
                updates.append('plate_number = ?')
                params.append(cleaned)
            if is_hotlist_hit is not None:
                updates.append('is_hotlist_hit = ?')
                params.append(1 if is_hotlist_hit else 0)
            if hotlist_info is not None:
                updates.append('hotlist_info = ?')
                params.append(hotlist_info)
            if confidence is not None:
                updates.append('confidence = ?')
                params.append(round(float(confidence), 1))
            if display_plate is not None:
                updates.append('display_plate = ?')
                params.append(display_plate)
            if det_confidence is not None:
                updates.append('det_confidence = ?')
                params.append(round(float(det_confidence), 1))
            if ocr_confidence is not None:
                updates.append('ocr_confidence = ?')
                params.append(round(float(ocr_confidence), 1))
            if blur_score is not None:
                updates.append('blur_score = ?')
                params.append(round(float(blur_score), 1))
            if quality_gate_passed is not None:
                updates.append('quality_gate_passed = ?')
                params.append(1 if quality_gate_passed else 0)
            if quality_reason is not None:
                updates.append('quality_reason = ?')
                params.append(quality_reason)
            if evidence_data is not None:
                ev_str = json.dumps(evidence_data) if isinstance(evidence_data, list) else evidence_data
                updates.append('evidence_json = ?')
                params.append(ev_str)
            if plate_img is not None and getattr(plate_img, 'size', 0) > 0:
                self._remove_disk_file(row['plate_pic_path'])
                new_plate_path = self._save_crop_image(plate_img, 'plate', cleaned)
                if new_plate_path:
                    updates.append('plate_pic_path = ?')
                    params.append(new_plate_path)
            if vehicle_img is not None and getattr(vehicle_img, 'size', 0) > 0:
                self._remove_disk_file(row['vehicle_pic_path'])
                new_veh_path = self._save_crop_image(vehicle_img, 'vehicle', cleaned)
                if new_veh_path:
                    updates.append('vehicle_pic_path = ?')
                    params.append(new_veh_path)
            if annotated_img is not None and getattr(annotated_img, 'size', 0) > 0:
                if 'annotated_pic_path' in row.keys():
                    self._remove_disk_file(row['annotated_pic_path'])
                new_ann_path = self._save_crop_image(annotated_img, 'annotated', cleaned)
                if new_ann_path:
                    updates.append('annotated_pic_path = ?')
                    params.append(new_ann_path)
            if track_id is not None:
                updates.append('track_id = ?')
                params.append(track_id)
            if vehicle_id is not None:
                updates.append('vehicle_id = ?')
                params.append(vehicle_id)
            if linked_tracks is not None:
                updates.append('linked_tracks = ?')
                params.append(linked_tracks)
            if evidence_video_path is not None:
                updates.append('evidence_video_path = ?')
                params.append(evidence_video_path)
            if is_traffic_violation is not None:
                updates.append('is_traffic_violation = ?')
                params.append(1 if is_traffic_violation else 0)
            if violation_type is not None:
                updates.append('violation_type = ?')
                params.append(violation_type)
            if violation_fine is not None:
                updates.append('violation_fine = ?')
                params.append(violation_fine)
            if violation_details is not None:
                updates.append('violation_details = ?')
                params.append(violation_details)
            if violation_id is not None:
                updates.append('violation_id = ?')
                params.append(violation_id)
            if update_timestamp:
                now_epoch = time.time()
                now_str = datetime.datetime.fromtimestamp(now_epoch).strftime('%Y-%m-%d %H:%M:%S')
                updates.append('captured_at = ?')
                params.append(now_str)
                updates.append('created_epoch = ?')
                params.append(now_epoch)
            if not updates:
                return True
            sql = f"UPDATE captured_vehicles SET {', '.join(updates)} WHERE id = ?"
            params.append(capture_id)
            cursor.execute(sql, params)
            conn.commit()
            self._record_trail_observation(capture_id)
            return True
        finally:
            conn.close()

    def _present_capture(self, record):
        if not record:
            return record
        plate=self.normalizer.clean_raw_text(record.get('plate_number') or '')
        if plate != 'UNREADABLE' and not(self.normalizer.config.min_length <= len(plate) <= self.normalizer.config.max_length):
            record['raw_ocr_text']=record.get('plate_number')
            record['plate_number']='UNREADABLE'
            record['display_plate']='UNREADABLE (INCOMPLETE OCR)'
            record['quality_gate_passed']=0
            record['is_hotlist_hit']=0
            record['hotlist_info']=''
        return record

    def _record_trail_observation(self, capture_id):
        if not capture_id or capture_id <= 0:
            return
        try:
            from src.database.trail_review_db import review_store
            record = self.get_by_id(capture_id)
            if record:
                review_store(os.path.dirname(self.db_path)).observe(record)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Could not persist vehicle trail observation")

    def get_recent(self, limit: int=100, offset: int=0, search: Optional[str]=None, hotlist_only: bool=False, district: Optional[str]=None, operator: Optional[str]=None, source: Optional[str]=None) -> List[Dict[str, Any]]:
        """
        Returns recent captures ordered newest first (FIFO reverse).
        Supports RBAC scoping by district and operator.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            if hotlist_only:
                conditions.append('is_hotlist_hit = 1')
            if district and district.lower() not in ['all', 'all haryana', 'all haryana (state hq)']:
                conditions.append('LOWER(district) = LOWER(?)')
                params.append(district.strip())
            if operator and operator.lower() not in ['all', 'all operators']:
                conditions.append('LOWER(operator_username) = LOWER(?)')
                params.append(operator.strip())
            if source:
                s_clean = str(source).strip().lower()
                if s_clean == 'upload':
                    conditions.append("LOWER(source_type) LIKE '%upload%'")
                elif s_clean == 'live':
                    conditions.append("LOWER(source_type) NOT LIKE '%upload%'")
            if search:
                term = f'%{search.strip()}%'
                conditions.append('(plate_number LIKE ? OR display_plate LIKE ? OR location LIKE ? OR hotlist_info LIKE ?)')
                params.extend([term, term, term, term])
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
            query = f'\n                SELECT * FROM captured_vehicles\n                {where_clause}\n                ORDER BY id DESC\n                LIMIT ? OFFSET ?\n            '
            params.extend([min(limit, self.max_records), offset])
            cursor.execute(query, params)
            return [self._present_capture({k: v for k, v in dict(row).items() if k in PUBLIC_FIELDS}) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_full(self, query: str) -> List[Dict[str, Any]]:
        """
        Comprehensive search across captured vehicles by plate number or ByteTrack tracking ID.
        Returns matching records with parsed evidence_json for forensics inspection.
        """
        if not query or not query.strip():
            return []
        cleaned_query = query.strip()
        cleaned_plate = self.normalizer.clean_raw_text(cleaned_query)
        numeric_part = ''.join((c for c in cleaned_query if c.isdigit()))
        track_id_val = int(numeric_part) if numeric_part else None
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            params = []
            plate_conds = []
            if cleaned_plate:
                plate_conds.append('plate_number LIKE ?')
                params.append(f'%{cleaned_plate}%')
            plate_conds.append('display_plate LIKE ?')
            params.append(f'%{cleaned_query}%')
            if track_id_val is not None:
                track_conds = ['track_id = ?', 'vehicle_id = ?', 'linked_tracks LIKE ?', 'evidence_json LIKE ?']
                params.extend([track_id_val, track_id_val, f'%{track_id_val}%', f'%"track_id": {track_id_val}%'])
                combined = f"(({' OR '.join(plate_conds)}) OR ({' OR '.join(track_conds)}))"
            else:
                combined = f"({' OR '.join(plate_conds)})"
            query_sql = f'\n                SELECT * FROM captured_vehicles\n                WHERE {combined}\n                ORDER BY id DESC\n                LIMIT 100\n            '
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                row_dict = self._present_capture({k: v for k, v in dict(r).items() if k in PUBLIC_FIELDS})
                ev_data = []
                if row_dict.get('evidence_json'):
                    try:
                        ev_data = json.loads(row_dict['evidence_json'])
                    except Exception:
                        ev_data = []
                row_dict['evidence_frames'] = ev_data
                results.append(row_dict)
            return results
        finally:
            conn.close()

    def get_total_count(self, district: Optional[str]=None, operator: Optional[str]=None, source: Optional[str]=None) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            if district and district.lower() not in ['all', 'all haryana', 'all haryana (state hq)']:
                conditions.append('LOWER(district) = LOWER(?)')
                params.append(district.strip())
            if operator and operator.lower() not in ['all', 'all operators']:
                conditions.append('LOWER(operator_username) = LOWER(?)')
                params.append(operator.strip())
            if source:
                s_clean = str(source).strip().lower()
                if s_clean == 'upload':
                    conditions.append("LOWER(source_type) LIKE '%upload%'")
                elif s_clean == 'live':
                    conditions.append("LOWER(source_type) NOT LIKE '%upload%'")
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
            cursor.execute(f'SELECT COUNT(*) FROM captured_vehicles {where_clause}', params)
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def get_by_id(self, capture_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM captured_vehicles WHERE id = ?', (capture_id,))
            row = cursor.fetchone()
            return self._present_capture({k: v for k, v in dict(row).items() if k in PUBLIC_FIELDS}) if row else None
        finally:
            conn.close()

    def update_plate(self, old_plate: str, new_plate: str, confidence: float=90.0) -> bool:
        """
        Updates an existing capture record when a user manually corrects the plate in Human Review.
        """
        cleaned_old = self.normalizer.clean_raw_text(old_plate)
        cleaned_new = self.normalizer.clean_raw_text(new_plate)
        disp_new = self.normalizer.format_display(cleaned_new)
        if not cleaned_old or not cleaned_new:
            return False
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("\n                UPDATE captured_vehicles\n                SET plate_number = ?, display_plate = ?, confidence = ?, ocr_confidence = ?, quality_reason = 'Human Review Confirmed'\n                WHERE plate_number = ?\n            ", (cleaned_new, disp_new, round(float(confidence), 1), round(float(confidence), 1), cleaned_old))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete(self, capture_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT plate_pic_path, vehicle_pic_path, annotated_pic_path, enhanced_pic_path FROM captured_vehicles WHERE id = ?', (capture_id,))
            row = cursor.fetchone()
            if row:
                self._remove_disk_file(row['plate_pic_path'])
                self._remove_disk_file(row['vehicle_pic_path'])
                if 'annotated_pic_path' in row.keys():
                    self._remove_disk_file(row['annotated_pic_path'])
                if 'enhanced_pic_path' in row.keys():
                    self._remove_disk_file(row['enhanced_pic_path'])
                cursor.execute('DELETE FROM captured_vehicles WHERE id = ?', (capture_id,))
                conn.commit()
                return cursor.rowcount > 0
            return False
        finally:
            conn.close()

    def clear_all(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT plate_pic_path, vehicle_pic_path, annotated_pic_path, enhanced_pic_path FROM captured_vehicles')
            rows = cursor.fetchall()
            for r in rows:
                self._remove_disk_file(r['plate_pic_path'])
                self._remove_disk_file(r['vehicle_pic_path'])
                if 'annotated_pic_path' in r.keys():
                    self._remove_disk_file(r['annotated_pic_path'])
                if 'enhanced_pic_path' in r.keys():
                    self._remove_disk_file(r['enhanced_pic_path'])
            cursor.execute('DELETE FROM captured_vehicles')
            conn.commit()
        finally:
            conn.close()

    def export_pdf(self, district: Optional[str]=None, operator: Optional[str]=None) -> bytes:
        from src.utils.pdf_exporter import build_captured_vehicles_pdf
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            if district and district.lower() not in ['all', 'all haryana', 'all haryana (state hq)']:
                conditions.append('LOWER(district) = LOWER(?)')
                params.append(district.strip())
            if operator and operator.lower() not in ['all', 'all operators']:
                conditions.append('LOWER(operator_username) = LOWER(?)')
                params.append(operator.strip())
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
            cursor.execute(f'SELECT * FROM captured_vehicles {where} ORDER BY id DESC', params)
            rows = [{k: v for k, v in dict(r).items() if k in PUBLIC_FIELDS} for r in cursor.fetchall()]
            stats = {'total': len(rows), 'hotlist_hits': sum((1 for r in rows if r.get('is_hotlist_hit')))}
            return build_captured_vehicles_pdf(rows, stats=stats)
        finally:
            conn.close()

    def export_csv(self, district: Optional[str]=None, operator: Optional[str]=None) -> str:
        import csv
        import io
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            if district and district.lower() not in ['all', 'all haryana', 'all haryana (state hq)']:
                conditions.append('LOWER(district) = LOWER(?)')
                params.append(district.strip())
            if operator and operator.lower() not in ['all', 'all operators']:
                conditions.append('LOWER(operator_username) = LOWER(?)')
                params.append(operator.strip())
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
            cursor.execute(f'\n                SELECT id, captured_at, location, plate_number, display_plate,\n                       confidence, det_confidence, ocr_confidence, is_hotlist_hit, hotlist_info, quality_reason,\n                       district, operator_username\n                FROM captured_vehicles {where} ORDER BY id DESC\n            ', params)
            rows = cursor.fetchall()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Captured At', 'Location', 'Plate Number', 'Display Plate', 'Confidence (%)', 'Detection Conf (%)', 'OCR Conf (%)', 'Is Hotlist Hit', 'Hotlist Info', 'Quality Reason', 'District', 'Operator'])
            for r in rows:
                writer.writerow([r['id'], r['captured_at'], r['location'], r['plate_number'], r['display_plate'], f"{r['confidence']:.1f}", f"{r['det_confidence']:.1f}", f"{r['ocr_confidence']:.1f}", r['is_hotlist_hit'], r['hotlist_info'], r['quality_reason'], r['district'] if 'district' in r.keys() else 'Panipat', r['operator_username'] if 'operator_username' in r.keys() else 'op_5421'])
            return output.getvalue()
        finally:
            conn.close()
