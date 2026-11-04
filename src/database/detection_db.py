"""
Detection History Database Module
Maintains a strict FIFO ring buffer of the most recent 100 ANPR detections.
Automatically prunes the oldest records and cleans up disk image crops.
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

class DetectionDB:
    def __init__(self, db_path: Optional[str] = None, max_records: int = 100):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "detections_history.sqlite")

        self.db_path = db_path
        self.max_records = max_records
        self.crops_dir = os.path.join(os.path.dirname(self.db_path), "detection_crops")
        os.makedirs(self.crops_dir, exist_ok=True)
        self.normalizer = IndianPlateNormalizer()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detections_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT NOT NULL,
                    display_plate TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    plate_pic_path TEXT,
                    vehicle_pic_path TEXT,
                    captured_at TEXT NOT NULL,
                    location TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    is_hotlist_hit INTEGER DEFAULT 0,
                    hotlist_info TEXT,
                    created_epoch REAL NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detection_plate ON detections_history (plate_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detection_epoch ON detections_history (created_epoch DESC)")
            conn.commit()
        finally:
            conn.close()

    def _save_crop_image(self, img_data: Optional[Union[np.ndarray, bytes]], prefix: str, plate_clean: str) -> Optional[str]:
        if img_data is None:
            return None

        file_tag = f"{prefix}_{plate_clean}_{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg"
        abs_path = os.path.join(self.crops_dir, file_tag)

        try:
            if isinstance(img_data, np.ndarray):
                if img_data.size == 0:
                    return None
                cv2.imwrite(abs_path, img_data, [cv2.IMWRITE_JPEG_QUALITY, 90])
            elif isinstance(img_data, bytes):
                if len(img_data) == 0:
                    return None
                with open(abs_path, "wb") as f:
                    f.write(img_data)
            else:
                return None
            return f"/data/detection_crops/{file_tag}"
        except Exception as e:
            print(f"[DetectionDB Error] Failed to save crop: {e}")
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

    def add_detection(
        self,
        plate_number: str,
        display_plate: Optional[str] = None,
        confidence: float = 0.0,
        plate_img: Optional[Union[np.ndarray, bytes]] = None,
        vehicle_img: Optional[Union[np.ndarray, bytes]] = None,
        location: str = "Main Surveillance Gate",
        source_type: str = "video_upload",
        is_hotlist_hit: bool = False,
        hotlist_info: Optional[str] = None
    ) -> int:
        """
        Inserts a new detection record at #1 position (newest).
        Enforces FIFO limit (max 100 entries):
        If count >= max_records, deletes the oldest record(s) and their image crops from disk.
        """
        cleaned = self.normalizer.clean_raw_text(plate_number)
        disp = display_plate or self.normalizer.format_display(cleaned)
        now_epoch = time.time()
        now_str = datetime.datetime.fromtimestamp(now_epoch).strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 1. FIFO Pruning: Check current count
            cursor.execute("SELECT COUNT(*) FROM detections_history")
            total_count = cursor.fetchone()[0]

            if total_count >= self.max_records:
                excess = (total_count - self.max_records) + 1
                cursor.execute(
                    "SELECT id, plate_pic_path, vehicle_pic_path FROM detections_history ORDER BY id ASC LIMIT ?",
                    (excess,)
                )
                old_rows = cursor.fetchall()
                for old in old_rows:
                    self._remove_disk_file(old["plate_pic_path"])
                    self._remove_disk_file(old["vehicle_pic_path"])
                    cursor.execute("DELETE FROM detections_history WHERE id = ?", (old["id"],))

            # 2. Save image crops to disk
            plate_pic_url = self._save_crop_image(plate_img, "plate", cleaned)
            vehicle_pic_url = self._save_crop_image(vehicle_img, "vehicle", cleaned)

            # 3. Insert new record (will be at top / highest id)
            cursor.execute("""
                INSERT INTO detections_history (
                    plate_number, display_plate, confidence, plate_pic_path,
                    vehicle_pic_path, captured_at, location, source_type,
                    is_hotlist_hit, hotlist_info, created_epoch
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cleaned,
                disp,
                round(float(confidence), 1),
                plate_pic_url,
                vehicle_pic_url,
                now_str,
                location or "Surveillance Feed",
                source_type or "unknown",
                1 if is_hotlist_hit else 0,
                hotlist_info or "",
                now_epoch
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        hotlist_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Returns recent detections ordered newest first (FIFO reverse).
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []

            if hotlist_only:
                conditions.append("is_hotlist_hit = 1")

            if search:
                term = f"%{search.strip()}%"
                conditions.append("(plate_number LIKE ? OR display_plate LIKE ? OR location LIKE ? OR hotlist_info LIKE ?)")
                params.extend([term, term, term, term])

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"""
                SELECT * FROM detections_history
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            params.extend([min(limit, self.max_records), offset])
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_total_count(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM detections_history")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def get_by_id(self, detection_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM detections_history WHERE id = ?", (detection_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete(self, detection_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT plate_pic_path, vehicle_pic_path FROM detections_history WHERE id = ?", (detection_id,))
            row = cursor.fetchone()
            if row:
                self._remove_disk_file(row["plate_pic_path"])
                self._remove_disk_file(row["vehicle_pic_path"])
                cursor.execute("DELETE FROM detections_history WHERE id = ?", (detection_id,))
                conn.commit()
                return cursor.rowcount > 0
            return False
        finally:
            conn.close()

    def clear_all(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT plate_pic_path, vehicle_pic_path FROM detections_history")
            rows = cursor.fetchall()
            for r in rows:
                self._remove_disk_file(r["plate_pic_path"])
                self._remove_disk_file(r["vehicle_pic_path"])
            cursor.execute("DELETE FROM detections_history")
            conn.commit()
        finally:
            conn.close()
