"""
Vehicle Trail DB Module
Manages persistent vehicle sightings linked to registered vehicles in Vehicle DB.
Completely independent of the Captured DB FIFO ring buffer.
Supports recording one sighting per passage, duplicate prevention, chronological history,
filtering by date/camera/location, and preserving plate/vehicle snapshot photos.
"""
from typing import List, Dict, Any, Optional, Union
import os
import sqlite3
import datetime
import time
import uuid
import cv2
import numpy as np
from src.ocr.normalizer import IndianPlateNormalizer

class TrailDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "vehicle_trail.sqlite")

        self.db_path = db_path
        self.photos_dir = os.path.join(os.path.dirname(self.db_path), "trail_photos")
        os.makedirs(self.photos_dir, exist_ok=True)
        self.normalizer = IndianPlateNormalizer()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vehicle_sightings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id INTEGER NOT NULL,
                    registration_number TEXT NOT NULL,
                    display_number TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    location TEXT NOT NULL,
                    gps_coords TEXT,
                    captured_at TEXT NOT NULL,
                    captured_epoch REAL NOT NULL,
                    confidence REAL NOT NULL,
                    plate_photo_path TEXT,
                    vehicle_photo_path TEXT,
                    passage_id TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            # Safe column migration for existing DB
            existing_cols = {col["name"] for col in cursor.execute("PRAGMA table_info(vehicle_sightings)").fetchall()}
            for col_name, col_type in [
                ("gps_coords", "TEXT"),
                ("district", "TEXT DEFAULT 'Panipat'"),
                ("operator_id", "INTEGER"),
                ("operator_username", "TEXT DEFAULT 'op_5421'"),
                ("station", "TEXT DEFAULT 'PHQ'")
            ]:
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE vehicle_sightings ADD COLUMN {col_name} {col_type}")
                    except Exception as e:
                        print(f"[TrailDB Migration]: {e}")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_vehicle_id ON vehicle_sightings (vehicle_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_epoch ON vehicle_sightings (captured_epoch DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_passage ON vehicle_sightings (passage_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_camera ON vehicle_sightings (camera_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_district ON vehicle_sightings (district)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_operator ON vehicle_sightings (operator_username)")
            conn.commit()
        finally:
            conn.close()

    def _save_photo(self, img_data: Optional[Union[np.ndarray, bytes]], prefix: str, plate_clean: str) -> Optional[str]:
        if img_data is None:
            return None
        is_plate = prefix == 'plate'
        extension = 'png' if is_plate else 'jpg'
        file_tag = f'{prefix}_{plate_clean}_{int(time.time())}_{uuid.uuid4().hex[:6]}.{extension}'
        abs_path = os.path.join(self.photos_dir, file_tag)

        try:
            if is_plate and isinstance(img_data, bytes):
                if not img_data:
                    return None
                img_data = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_UNCHANGED)
            if isinstance(img_data, np.ndarray):
                if img_data.size == 0:
                    return None
                options = [] if is_plate else [cv2.IMWRITE_JPEG_QUALITY, 90]
                if not cv2.imwrite(abs_path, img_data, options):
                    return None
            elif isinstance(img_data, bytes):
                if len(img_data) == 0:
                    return None
                with open(abs_path, "wb") as f:
                    f.write(img_data)
            else:
                return None

            return f"/data/trail_photos/{file_tag}"
        except Exception as e:
            print(f"[TrailDB] Error saving photo: {e}")
            return None

    def record_sighting(
        self,
        vehicle_id: int,
        registration_number: str,
        camera_id: str = "CAM-01",
        location: str = "Surveillance Post",
        gps_coords: Optional[str] = None,
        captured_at: Optional[str] = None,
        confidence: float = 0.0,
        plate_img: Optional[Union[np.ndarray, bytes]] = None,
        vehicle_img: Optional[Union[np.ndarray, bytes]] = None,
        passage_id: Optional[str] = None,
        min_cooldown_seconds: float = 5.0,
        district: str = "Panipat",
        operator_id: Optional[int] = None,
        operator_username: str = "op_5421",
        station: str = "PHQ"
    ) -> Optional[int]:
        """
        Appends a sighting linked to vehicle_id.
        Prevents duplicate entries from processing retries using passage_id or rapid temporal cooldown.
        Returns sighting_id if recorded, or None if skipped as duplicate.
        """
        from src.camera.registry import resolve_camera, camera_metadata
        registered = resolve_camera(camera_id, location)
        if registered:
            camera_id, location, gps_coords = camera_metadata(registered)
            district = registered["district"]
            station = registered["station"]

        cleaned_plate = self.normalizer.clean_raw_text(registration_number)
        display_num = self.normalizer.format_display(cleaned_plate)

        now = datetime.datetime.now().astimezone()
        now_epoch = now.timestamp()
        if captured_at:
            event_time = datetime.datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                from zoneinfo import ZoneInfo
                event_time = event_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            now_epoch = event_time.timestamp()
            iso_timestamp = event_time.isoformat()
        else:
            iso_timestamp = now.isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 1. Exact passage duplicate check
            if passage_id:
                cursor.execute(
                    "SELECT id FROM vehicle_sightings WHERE vehicle_id = ? AND camera_id = ? AND passage_id = ?",
                    (vehicle_id, camera_id, passage_id)
                )
                if cursor.fetchone():
                    # Duplicate entry for this passage session; skip recording
                    return None

            # 2. Cooldown check: prevent duplicate insertion within cooldown on same camera
            cursor.execute(
                "SELECT id, captured_epoch FROM vehicle_sightings WHERE vehicle_id = ? AND camera_id = ? ORDER BY captured_epoch DESC LIMIT 1",
                (vehicle_id, camera_id)
            )
            last_sighting = cursor.fetchone()
            if last_sighting:
                delta = abs(now_epoch - last_sighting["captured_epoch"])
                if delta < min_cooldown_seconds:
                    # Within cooldown window on the same camera; skip duplicate retry
                    return None

            # Save evidence photos to dedicated trail_photos directory
            plate_photo_path = self._save_photo(plate_img, "plate", cleaned_plate)
            vehicle_photo_path = self._save_photo(vehicle_img, "vehicle", cleaned_plate)

            cursor.execute("""
                INSERT INTO vehicle_sightings (
                    vehicle_id, registration_number, display_number, camera_id, location, gps_coords,
                    captured_at, captured_epoch, confidence, plate_photo_path,
                    vehicle_photo_path, passage_id, created_at,
                    district, operator_id, operator_username, station
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vehicle_id,
                cleaned_plate,
                display_num,
                camera_id,
                location,
                gps_coords,
                iso_timestamp,
                now_epoch,
                round(float(confidence), 1),
                plate_photo_path,
                vehicle_photo_path,
                passage_id,
                now.isoformat(),
                district,
                operator_id,
                operator_username,
                station
            ))

            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_vehicle_trails_summary(
        self,
        search: Optional[str] = None,
        district: Optional[str] = None,
        operator: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns summary for all vehicles with recorded sightings:
        vehicle_id, registration_number, display_number, sighting_count,
        last_seen_camera, last_seen_location, last_seen_gps, last_seen_time, last_seen_epoch.
        Filtered by district and operator when specified.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            where_clauses = []
            params = []
            if district and district.upper() != "ALL":
                where_clauses.append("UPPER(s.district) = UPPER(?)")
                params.append(district.strip())
            if operator and operator.upper() != "ALL":
                where_clauses.append("UPPER(s.operator_username) = UPPER(?)")
                params.append(operator.strip())

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            # Aggregate per vehicle_id
            sql = f"""
                SELECT 
                    s.vehicle_id,
                    s.registration_number,
                    s.display_number,
                    COUNT(s.id) as sighting_count,
                    MAX(s.captured_epoch) as last_seen_epoch
                FROM vehicle_sightings s
                {where_sql}
                GROUP BY s.vehicle_id
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            summaries = []
            for r in rows:
                v_id = r["vehicle_id"]
                # Get the most recent sighting details under same filter
                latest_sql = "SELECT camera_id, location, gps_coords, captured_at, confidence, plate_photo_path, vehicle_photo_path, district, operator_username, station FROM vehicle_sightings WHERE vehicle_id = ?"
                latest_params = [v_id]
                if district and district.upper() != "ALL":
                    latest_sql += " AND UPPER(district) = UPPER(?)"
                    latest_params.append(district.strip())
                if operator and operator.upper() != "ALL":
                    latest_sql += " AND UPPER(operator_username) = UPPER(?)"
                    latest_params.append(operator.strip())
                latest_sql += " ORDER BY captured_epoch DESC LIMIT 1"

                cursor.execute(latest_sql, latest_params)
                latest = cursor.fetchone()

                item = {
                    "vehicle_id": v_id,
                    "registration_number": r["registration_number"],
                    "display_number": r["display_number"],
                    "sighting_count": r["sighting_count"],
                    "last_seen_epoch": r["last_seen_epoch"],
                    "last_seen_camera": latest["camera_id"] if latest else "N/A",
                    "last_seen_location": latest["location"] if latest else "N/A",
                    "last_seen_gps": latest["gps_coords"] if latest and latest["gps_coords"] else None,
                    "last_seen_time": latest["captured_at"] if latest else "N/A",
                    "latest_confidence": latest["confidence"] if latest else 0.0,
                    "latest_plate_photo": latest["plate_photo_path"] if latest else None,
                    "latest_vehicle_photo": latest["vehicle_photo_path"] if latest else None,
                    "district": latest["district"] if latest and "district" in latest.keys() else "Panipat",
                    "operator_username": latest["operator_username"] if latest and "operator_username" in latest.keys() else "op_5421",
                    "station": latest["station"] if latest and "station" in latest.keys() else "PHQ"
                }

                if search:
                    st = search.strip().upper()
                    if (st not in item["registration_number"].upper() and
                        st not in item["display_number"].upper() and
                        st not in item["last_seen_location"].upper() and
                        (not item["last_seen_gps"] or st not in item["last_seen_gps"].upper()) and
                        st not in item["last_seen_camera"].upper() and
                        st not in item["district"].upper() and
                        st not in item["operator_username"].upper()):
                        continue

                summaries.append(item)

            # Sort descending by latest sighting
            summaries.sort(key=lambda x: x["last_seen_epoch"], reverse=True)
            return summaries
        finally:
            conn.close()

    def get_vehicle_history(
        self,
        vehicle_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        camera_id: Optional[str] = None,
        location: Optional[str] = None,
        ascending: bool = True,
        district: Optional[str] = None,
        operator: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns the chronological history of sightings for a given vehicle_id,
        filtered optionally by date range, camera_id, location, district, or operator.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            sql = "SELECT * FROM vehicle_sightings WHERE vehicle_id = ?"
            params: List[Any] = [vehicle_id]

            if district and district.upper() != "ALL":
                sql += " AND UPPER(district) = UPPER(?)"
                params.append(district.strip())

            if operator and operator.upper() != "ALL":
                sql += " AND UPPER(operator_username) = UPPER(?)"
                params.append(operator.strip())

            if start_date:
                sql += " AND captured_at >= ?"
                params.append(start_date)

            if end_date:
                val = end_date + "T23:59:59" if "T" not in end_date else end_date
                sql += " AND captured_at <= ?"
                params.append(val)

            if camera_id and camera_id.strip():
                sql += " AND UPPER(camera_id) = UPPER(?)"
                params.append(camera_id.strip())

            if location and location.strip():
                sql += " AND UPPER(location) LIKE ?"
                params.append(f"%{location.strip().upper()}%")

            order = "ASC" if ascending else "DESC"
            sql += f" ORDER BY captured_epoch {order}"

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_total_sightings_count(self, district: Optional[str] = None, operator: Optional[str] = None) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            sql = "SELECT COUNT(*) FROM vehicle_sightings WHERE 1=1"
            params: List[Any] = []
            if district and district.upper() != "ALL":
                sql += " AND UPPER(district) = UPPER(?)"
                params.append(district.strip())
            if operator and operator.upper() != "ALL":
                sql += " AND UPPER(operator_username) = UPPER(?)"
                params.append(operator.strip())
            cursor.execute(sql, params)
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def delete_sighting(self, sighting_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT plate_photo_path, vehicle_photo_path FROM vehicle_sightings WHERE id = ?", (sighting_id,))
            row = cursor.fetchone()
            if row:
                for col in ["plate_photo_path", "vehicle_photo_path"]:
                    if row[col]:
                        fname = os.path.basename(row[col])
                        fpath = os.path.join(self.photos_dir, fname)
                        if os.path.exists(fpath):
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass

            cursor.execute("DELETE FROM vehicle_sightings WHERE id = ?", (sighting_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_vehicle_trail(self, vehicle_id: int) -> int:
        """Deletes all trail sightings for a vehicle and cleans up crop files."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT plate_photo_path, vehicle_photo_path FROM vehicle_sightings WHERE vehicle_id = ?", (vehicle_id,))
            rows = cursor.fetchall()
            for row in rows:
                for col in ["plate_photo_path", "vehicle_photo_path"]:
                    if row[col]:
                        fname = os.path.basename(row[col])
                        fpath = os.path.join(self.photos_dir, fname)
                        if os.path.exists(fpath):
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
            cursor.execute("DELETE FROM vehicle_sightings WHERE vehicle_id = ?", (vehicle_id,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def delete_vehicle_trail_by_plate(self, plate_number: str) -> int:
        """Deletes all trail sightings for a plate number."""
        cleaned = self.normalizer.clean_raw_text(plate_number)
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM vehicle_sightings WHERE UPPER(REPLACE(plate_number, ' ', '')) = ?", (cleaned,))
            rows = cursor.fetchall()
            deleted = 0
            for r in rows:
                if self.delete_sighting(r["id"]):
                    deleted += 1
            return deleted
        finally:
            conn.close()


    def clear_all(self):
        """Clears all records and photos from the trail db (useful for testing/reset)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vehicle_sightings")
            conn.commit()
        finally:
            conn.close()

        # Clean photos directory
        for f in os.listdir(self.photos_dir):
            p = os.path.join(self.photos_dir, f)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
