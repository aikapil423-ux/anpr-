"""
Vehicle DB Module
Manages hotlist, crime-linked, and lost/missing vehicle records in SQLite.
Provides CRUD operations, plate matching, and photo storage.
"""
from typing import List, Dict, Any, Optional, Tuple
import os
import sqlite3
import datetime
from src.ocr.normalizer import IndianPlateNormalizer

class VehicleDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "vehicle_db.sqlite")

        self.db_path = db_path
        self.photos_dir = os.path.join(os.path.dirname(self.db_path), "vehicle_photos")
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
                CREATE TABLE IF NOT EXISTS vehicles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_number TEXT NOT NULL,
                    display_number TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    vehicle_color TEXT NOT NULL,
                    involved_in_case INTEGER NOT NULL,
                    offence_type TEXT,
                    fir_number TEXT,
                    police_station TEXT,
                    io_number TEXT,
                    case_summary TEXT,
                    lost_location TEXT,
                    lost_details TEXT,
                    manual_location TEXT,
                    photo_path TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'ACTIVE'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vehicle_number ON vehicles (vehicle_number)")
            
            # Safe schema migration for centralized multi-district tracking
            existing_cols = {col["name"] for col in cursor.execute("PRAGMA table_info(vehicles)").fetchall()}
            if "district_name" not in existing_cols:
                cursor.execute("ALTER TABLE vehicles ADD COLUMN district_name TEXT DEFAULT 'All Haryana'")
            if "created_by_officer" not in existing_cols:
                cursor.execute("ALTER TABLE vehicles ADD COLUMN created_by_officer TEXT DEFAULT 'Duty Officer'")
            if "owner_name" not in existing_cols:
                cursor.execute("ALTER TABLE vehicles ADD COLUMN owner_name TEXT DEFAULT ''")
            if "owner_father_name" not in existing_cols:
                cursor.execute("ALTER TABLE vehicles ADD COLUMN owner_father_name TEXT DEFAULT ''")
            if "owner_mobile" not in existing_cols:
                cursor.execute("ALTER TABLE vehicles ADD COLUMN owner_mobile TEXT DEFAULT ''")
            if "owner_address" not in existing_cols:
                cursor.execute("ALTER TABLE vehicles ADD COLUMN owner_address TEXT DEFAULT ''")
            
            conn.commit()
        finally:
            conn.close()

    def add_vehicle(
        self,
        vehicle_number: str,
        vehicle_type: str,
        vehicle_color: str,
        involved_in_case: bool,
        manual_location: Optional[str] = None,
        # Case fields
        offence_type: Optional[str] = None,
        fir_number: Optional[str] = None,
        police_station: Optional[str] = None,
        io_number: Optional[str] = None,
        case_summary: Optional[str] = None,
        # Lost fields
        lost_location: Optional[str] = None,
        lost_details: Optional[str] = None,
        # District & Officer tracking
        district_name: Optional[str] = "All Haryana",
        created_by_officer: Optional[str] = "Duty Officer",
        # Registered Owner details
        owner_name: Optional[str] = None,
        owner_father_name: Optional[str] = None,
        owner_mobile: Optional[str] = None,
        owner_address: Optional[str] = None,
        # Photo
        photo_bytes: Optional[bytes] = None,
        photo_filename: Optional[str] = None
    ) -> int:
        """
        Inserts a new vehicle record with automatic timestamp and normalized plate.
        """
        # Normalize plate
        cleaned = self.normalizer.clean_raw_text(vehicle_number)
        is_valid, fmt, norm_plate = self.normalizer.validate(cleaned)
        norm_num = norm_plate if is_valid else cleaned.upper()
        disp_num = self.normalizer.format_display(norm_num)

        # Save photo if provided
        saved_photo_path = None
        if photo_bytes and photo_filename:
            ext = os.path.splitext(photo_filename)[1] or ".jpg"
            safe_name = f"{norm_num}_{int(datetime.datetime.now().timestamp())}{ext}"
            full_path = os.path.join(self.photos_dir, safe_name)
            with open(full_path, "wb") as f:
                f.write(photo_bytes)
            # Store relative path for web serving
            saved_photo_path = f"/data/vehicle_photos/{safe_name}"

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO vehicles (
                    vehicle_number, display_number, vehicle_type, vehicle_color,
                    involved_in_case, offence_type, fir_number, police_station,
                    io_number, case_summary, lost_location, lost_details,
                    manual_location, district_name, created_by_officer,
                    owner_name, owner_father_name, owner_mobile, owner_address,
                    photo_path, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            """, (
                norm_num,
                disp_num,
                vehicle_type or "Unknown",
                vehicle_color or "Unknown",
                1 if involved_in_case else 0,
                offence_type if involved_in_case else None,
                fir_number if involved_in_case else None,
                police_station if involved_in_case else None,
                io_number if involved_in_case else None,
                case_summary if involved_in_case else None,
                lost_location if not involved_in_case else None,
                lost_details if not involved_in_case else None,
                manual_location or "",
                district_name or "All Haryana",
                created_by_officer or "Duty Officer",
                owner_name or "",
                owner_father_name or "",
                owner_mobile or "",
                owner_address or "",
                saved_photo_path,
                now_str
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_all(
        self,
        search_query: Optional[str] = None,
        filter_type: Optional[str] = None, # 'all', 'case', 'lost'
        district: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            sql = "SELECT * FROM vehicles WHERE 1=1"
            params = []

            if filter_type == "case":
                sql += " AND involved_in_case = 1"
            elif filter_type == "lost":
                sql += " AND involved_in_case = 0"

            if district and district.lower() not in ["all", "all haryana", "state hq"]:
                sql += " AND district_name LIKE ?"
                params.append(f"%{district}%")

            if search_query:
                term = f"%{search_query.strip().upper()}%"
                sql += """ AND (
                    UPPER(vehicle_number) LIKE ? OR
                    UPPER(display_number) LIKE ? OR
                    UPPER(fir_number) LIKE ? OR
                    UPPER(police_station) LIKE ? OR
                    UPPER(vehicle_color) LIKE ? OR
                    UPPER(lost_location) LIKE ? OR
                    UPPER(district_name) LIKE ? OR
                    UPPER(COALESCE(owner_name, '')) LIKE ? OR
                    UPPER(COALESCE(owner_mobile, '')) LIKE ? OR
                    UPPER(COALESCE(owner_address, '')) LIKE ?
                )"""
                params.extend([term, term, term, term, term, term, term, term, term, term])

            sql += " ORDER BY id DESC"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_id(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def match_plate_with_type(self, plate: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Cross-checks a detected plate against the database.
        Returns:
            (record, "EXACT") if exact 100% normalized match
            (record, "NEAR_MATCH") if 1-character difference or high similarity (>= 0.85)
            (None, "NONE") if no match
        """
        if not plate:
            return None, "NONE"
        cleaned = self.normalizer.clean_raw_text(plate)
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vehicles WHERE vehicle_number = ? AND status = 'ACTIVE'", (cleaned,))
            row = cursor.fetchone()
            if row:
                res = dict(row)
                res["match_type"] = "EXACT"
                return res, "EXACT"

            # Check for 1-character difference or near-match (similarity >= 0.85)
            cursor.execute("SELECT * FROM vehicles WHERE status = 'ACTIVE'")
            rows = cursor.fetchall()
            best_match = None
            best_sim = 0.0
            for r in rows:
                db_num = r["vehicle_number"]
                sim = self.normalizer.calculate_levenshtein(cleaned, db_num)
                if sim >= 0.85 and sim > best_sim:
                    best_sim = sim
                    best_match = dict(r)

            if best_match:
                best_match["match_type"] = "NEAR_MATCH"
                best_match["similarity"] = round(best_sim, 2)
                return best_match, "NEAR_MATCH"

            return None, "NONE"
        finally:
            conn.close()

    def match_plate(self, plate: str) -> Optional[Dict[str, Any]]:
        """
        Cross-checks a detected plate against the database.
        Returns the vehicle record if matched (exact or >= 0.95 fuzzy), else None.
        Maintains 100% backward compatibility for all app.py routes.
        """
        rec, m_type = self.match_plate_with_type(plate)
        if rec and (m_type == "EXACT" or rec.get("similarity", 0.0) >= 0.95):
            return rec
        return None

    def delete(self, vehicle_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Find photo to remove
            cursor.execute("SELECT photo_path FROM vehicles WHERE id = ?", (vehicle_id,))
            row = cursor.fetchone()
            if row and row["photo_path"]:
                fname = os.path.basename(row["photo_path"])
                fpath = os.path.join(self.photos_dir, fname)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

            cursor.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
