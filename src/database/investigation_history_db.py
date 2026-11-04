PUBLIC_FIELDS = {'filename', 'timestamp', 'status', 'vehicle_model', 'session_id', 'belt_number', 'vehicles_json', 'time_display', 'output_media_url', 'files_json', 'district', 'fps', 'search_id', 'id', 'hotlist_hits', 'username', 'station', 'route_coords_json', 'total_plates', 'session_title', 'media_type', 'total_vehicles', 'total_files', 'target_scope', 'officer_name', 'role', 'ocr_engine'}
import os
import sqlite3
import json
import datetime
from typing import List, Dict, Any, Optional

class InvestigationHistoryDB:

    def __init__(self, db_path: Optional[str]=None, seed_samples: bool=False):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            data_dir = os.path.join(base_dir, 'data')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'investigation_history.sqlite')
        self.db_path = db_path
        self.seed_samples = seed_samples
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA busy_timeout=30000;')
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("\n                CREATE TABLE IF NOT EXISTS investigation_searches (id INTEGER PRIMARY KEY AUTOINCREMENT,\nsearch_id TEXT UNIQUE NOT NULL,\ntimestamp TEXT NOT NULL,\ntime_display TEXT NOT NULL,\nusername TEXT NOT NULL,\nofficer_name TEXT,\nbelt_number TEXT,\ndistrict TEXT,\nstation TEXT,\nrole TEXT,\nfilename TEXT NOT NULL,\nmedia_type TEXT NOT NULL,\ntarget_scope TEXT NOT NULL,\nvehicle_model TEXT,\nocr_engine TEXT,\nfps INTEGER DEFAULT 5,\ntotal_vehicles INTEGER DEFAULT 0,\ntotal_plates INTEGER DEFAULT 0,\nhotlist_hits INTEGER DEFAULT 0,\nvehicles_json TEXT,\noutput_media_url TEXT,\nstatus TEXT DEFAULT 'COMPLETED')\n            ")
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_inv_district ON investigation_searches(district)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_inv_username ON investigation_searches(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_inv_timestamp ON investigation_searches(timestamp DESC)')
            cursor.execute("\n                CREATE TABLE IF NOT EXISTS upload_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,\nsession_id TEXT UNIQUE NOT NULL,\nsession_title TEXT NOT NULL,\ntimestamp TEXT NOT NULL,\ntime_display TEXT NOT NULL,\nusername TEXT NOT NULL,\nofficer_name TEXT,\nbelt_number TEXT,\ndistrict TEXT,\nstation TEXT,\nrole TEXT,\ntotal_files INTEGER DEFAULT 0,\ntotal_vehicles INTEGER DEFAULT 0,\nfiles_json TEXT DEFAULT '[]',\nvehicles_json TEXT DEFAULT '[]',\nroute_coords_json TEXT DEFAULT '[]',\nstatus TEXT DEFAULT 'COMPLETED')\n            ")
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sess_district ON upload_sessions(district)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sess_timestamp ON upload_sessions(timestamp DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sess_username ON upload_sessions(username)')
            conn.commit()
        finally:
            conn.close()

    def add_search(self, search_data: Dict[str, Any]) -> Dict[str, Any]:
        """Records a completed forensic investigation search."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            search_id = search_data.get('search_id')
            if not search_id:
                now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                search_id = f'srch_{now_str}_{os.urandom(3).hex()}'
            now_iso = search_data.get('timestamp') or datetime.datetime.now().astimezone().isoformat()
            time_display = search_data.get('time_display') or datetime.datetime.now().strftime('%I:%M %p Today')
            v_json = search_data.get('vehicles_json')
            if isinstance(v_json, (list, dict)):
                v_json = json.dumps(v_json)
            cursor.execute('\n                INSERT INTO investigation_searches (search_id, timestamp, time_display, username, officer_name, belt_number, district, station, role, filename, media_type, target_scope, vehicle_model, ocr_engine, fps, total_vehicles, total_plates, hotlist_hits, vehicles_json, output_media_url, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            ', (search_id, now_iso, time_display, search_data.get('username', 'Unknown'), search_data.get('officer_name', 'Duty Officer'), search_data.get('belt_number', '--'), search_data.get('district', 'Panipat'), search_data.get('station', 'General Post'), search_data.get('role', 'OPERATOR'), search_data.get('filename', 'uploaded_media'), search_data.get('media_type', 'photo'), search_data.get('target_scope', 'BOTH'), search_data.get('vehicle_model', 'Default Detector'), search_data.get('ocr_engine', 'Default OCR'), search_data.get('fps', 5), search_data.get('total_vehicles', 0), search_data.get('total_plates', 0), search_data.get('hotlist_hits', 0), v_json or '[]', search_data.get('output_media_url', ''), search_data.get('status', 'COMPLETED')))
            conn.commit()
            return {'success': True, 'search_id': search_id}
        finally:
            conn.close()

    def list_searches(self, requesting_role: str='STATE_ADMIN', requesting_district: Optional[str]=None, limit: int=50) -> List[Dict[str, Any]]:
        """
        Lists investigation searches respecting RBAC:
        - STATE_ADMIN: Sees all statewide searches.
        - DISTRICT_ADMIN: Sees all searches in their district.
        - OPERATOR: Sees searches in their district.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if requesting_role in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
                cursor.execute('\n                    SELECT * FROM investigation_searches\n                    ORDER BY timestamp DESC\n                    LIMIT ?\n                ', (limit,))
            else:
                cursor.execute('\n                    SELECT * FROM investigation_searches\n                    WHERE district = ?\n                    ORDER BY timestamp DESC\n                    LIMIT ?\n                ', (requesting_district or 'Panipat', limit))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = {k: v for k, v in dict(r).items() if k in PUBLIC_FIELDS}
                try:
                    item['vehicles'] = json.loads(item.get('vehicles_json') or '[]')
                except Exception:
                    item['vehicles'] = []
                results.append(item)
            return results
        finally:
            conn.close()

    def get_search_by_id(self, search_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM investigation_searches WHERE search_id = ?', (search_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = {k: v for k, v in dict(row).items() if k in PUBLIC_FIELDS}
            try:
                item['vehicles'] = json.loads(item.get('vehicles_json') or '[]')
            except Exception:
                item['vehicles'] = []
            return item
        finally:
            conn.close()

    def clear_searches(self, requesting_role: str, requesting_district: Optional[str]=None) -> bool:
        """Clears searches based on role authority."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if requesting_role in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
                cursor.execute('DELETE FROM investigation_searches')
            else:
                cursor.execute('DELETE FROM investigation_searches WHERE district = ?', (requesting_district or 'Panipat',))
            conn.commit()
            return True
        finally:
            conn.close()

    def add_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Records an upload & analysis session containing all files and detections."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            session_id = session_data.get('session_id')
            if not session_id:
                now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                session_id = f'sess_{now_str}_{os.urandom(3).hex()}'
            now_iso = session_data.get('timestamp') or datetime.datetime.now().astimezone().isoformat()
            time_display = session_data.get('time_display') or datetime.datetime.now().strftime('%I:%M %p Today, %d %b %Y')
            files_json = session_data.get('files_json') or session_data.get('files') or []
            if isinstance(files_json, (list, dict)):
                files_json = json.dumps(files_json)
            v_json = session_data.get('vehicles_json') or session_data.get('vehicles') or []
            if isinstance(v_json, (list, dict)):
                v_json = json.dumps(v_json)
            route_json = session_data.get('route_coords_json') or session_data.get('route_coords') or []
            if isinstance(route_json, (list, dict)):
                route_json = json.dumps(route_json)
            total_files = int(session_data.get('total_files') or len(json.loads(files_json)))
            total_vehicles = int(session_data.get('total_vehicles') or len(json.loads(v_json)))
            cursor.execute('\n                INSERT INTO upload_sessions (session_id, session_title, timestamp, time_display, username, officer_name, belt_number, district, station, role, total_files, total_vehicles, files_json, vehicles_json, route_coords_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            ', (session_id, session_data.get('session_title', 'Batch Surveillance Upload'), now_iso, time_display, session_data.get('username', 'Unknown'), session_data.get('officer_name', 'Duty Officer'), session_data.get('belt_number', '--'), session_data.get('district', 'Panipat'), session_data.get('station', 'General Post'), session_data.get('role', 'OPERATOR'), total_files, total_vehicles, files_json, v_json, route_json, session_data.get('status', 'COMPLETED')))
            conn.commit()
            return {'success': True, 'session_id': session_id}
        finally:
            conn.close()

    def list_sessions(self, requesting_role: str='STATE_ADMIN', requesting_district: Optional[str]=None, requesting_operator: Optional[str]=None, limit: int=50) -> List[Dict[str, Any]]:
        """Lists upload sessions with parsed JSON and RBAC filtering."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            clauses = []
            params = []
            if requesting_role not in ('STATE_ADMIN', 'DEVELOPER_ADMIN'):
                clauses.append('LOWER(district) = LOWER(?)')
                params.append(requesting_district or 'Panipat')
            elif requesting_district and requesting_district.upper() not in ('ALL', 'ALL HARYANA', 'ALL HARYANA (STATE HQ)'):
                clauses.append('LOWER(district) = LOWER(?)')
                params.append(requesting_district)
            if requesting_operator and requesting_operator.upper() not in ('ALL', 'ALL OPERATORS'):
                clauses.append('(LOWER(username) = LOWER(?) OR LOWER(officer_name) = LOWER(?))')
                params.extend([requesting_operator, requesting_operator])
            where_sql = 'WHERE ' + ' AND '.join(clauses) if clauses else ''
            sql = f'\n                SELECT * FROM upload_sessions\n                {where_sql}\n                ORDER BY timestamp DESC\n                LIMIT ?\n            '
            params.append(limit)
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = {k: v for k, v in dict(r).items() if k in PUBLIC_FIELDS}
                try:
                    item['files'] = json.loads(item.get('files_json') or '[]')
                except Exception:
                    item['files'] = []
                try:
                    item['vehicles'] = json.loads(item.get('vehicles_json') or '[]')
                except Exception:
                    item['vehicles'] = []
                try:
                    item['route_coords'] = json.loads(item.get('route_coords_json') or '[]')
                except Exception:
                    item['route_coords'] = []
                results.append(item)
            return results
        finally:
            conn.close()

    def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM upload_sessions WHERE session_id = ?', (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = {k: v for k, v in dict(row).items() if k in PUBLIC_FIELDS}
            try:
                item['files'] = json.loads(item.get('files_json') or '[]')
            except Exception:
                item['files'] = []
            try:
                item['vehicles'] = json.loads(item.get('vehicles_json') or '[]')
            except Exception:
                item['vehicles'] = []
            try:
                item['route_coords'] = json.loads(item.get('route_coords_json') or '[]')
            except Exception:
                item['route_coords'] = []
            return item
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM upload_sessions WHERE session_id = ?', (session_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
