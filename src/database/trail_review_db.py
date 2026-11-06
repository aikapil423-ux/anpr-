"""Persistent exact matches, human-reviewed near matches and ordinary vehicle trails."""
import datetime
import json
import shutil
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo
from src.camera.registry import resolve_camera
from src.database.vehicle_db import VehicleDB

IST = ZoneInfo("Asia/Kolkata")

class TrailReviewDB:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.path = self.directory / "vehicle_trail_review.sqlite"
        self.photos = self.directory / "trail_review_photos"
        self.photos.mkdir(parents=True, exist_ok=True)
        self.watchlist = VehicleDB(str(self.directory / "vehicle_db.sqlite"))
        with closing(self.connect()) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, capture_id INTEGER UNIQUE NOT NULL,
                detected_plate TEXT NOT NULL, route_plate TEXT NOT NULL,
                candidate_id INTEGER, candidate_plate TEXT, candidate_photo TEXT,
                status TEXT NOT NULL, similarity REAL DEFAULT 0, confidence REAL DEFAULT 0,
                camera_id TEXT, location TEXT, lat REAL, lng REAL, captured_at TEXT, epoch REAL,
                district TEXT, operator_username TEXT, plate_photo TEXT, vehicle_photo TEXT,
                reviewed_by TEXT, reviewed_at TEXT, case_info TEXT
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS observation_scope ON observations(district,operator_username,epoch)")
            conn.execute("CREATE INDEX IF NOT EXISTS observation_route ON observations(route_plate,status)")
            conn.execute("CREATE TABLE IF NOT EXISTS cleared_captures (capture_id INTEGER PRIMARY KEY)")
            conn.commit()

    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _photo(self, source, capture_id, kind):
        if not source:
            return None
        src = self.directory / "captured_crops" / Path(source).name
        dest = self.photos / f"capture_{int(capture_id)}_{kind}{src.suffix}"
        if src.is_file():
            shutil.copyfile(src, dest)
        if not dest.is_file():
            return None
        prefix = "/data/demo" if self.directory.name == "demo" else "/data"
        return f"{prefix}/trail_review_photos/{dest.name}"

    def observe(self, record):
        if (record.get("quality_reason") or "").startswith("OCR consensus review:"):
            return None
        plate = self.watchlist.normalizer.clean_raw_text(record.get("plate_number") or "")
        if not plate or plate in ("UNREADABLE", "UNKNOWN") or not (8 <= len(plate) <= 11):
            return None
        capture_id = int(record["id"])
        with closing(self.connect()) as conn:
            if conn.execute("SELECT 1 FROM cleared_captures WHERE capture_id=?", (capture_id,)).fetchone():
                return None
        camera = resolve_camera(location=record.get("location"))
        stamp = record.get("captured_at")
        try:
            at = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            at = datetime.datetime.fromtimestamp(record.get("created_epoch") or 0, IST)
        if at.tzinfo is None:
            at = at.replace(tzinfo=IST)
        candidate, match_type = self.watchlist.match_plate_with_type(plate)
        status = "EXACT" if match_type == "EXACT" else "PENDING" if match_type == "NEAR_MATCH" else "NORMAL"
        route_plate = candidate["vehicle_number"] if status == "EXACT" else plate
        plate_photo = self._photo(record.get("plate_pic_path"), capture_id, "plate")
        vehicle_photo = self._photo(record.get("vehicle_pic_path"), capture_id, "vehicle")
        with closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT * FROM observations WHERE capture_id=?", (capture_id,)).fetchone()
            if old and old["detected_plate"] == plate and old["status"] in ("SAME", "NOT_SAME"):
                status, route_plate = old["status"], old["route_plate"]
                candidate_id, candidate_plate, candidate_photo = old["candidate_id"], old["candidate_plate"], old["candidate_photo"]
            else:
                candidate_id = candidate.get("id") if candidate else None
                candidate_plate = candidate.get("vehicle_number") if candidate else None
                candidate_photo = candidate.get("photo_path") if candidate else None
            values = dict(capture_id=capture_id, detected_plate=plate, route_plate=route_plate,
                candidate_id=candidate_id, candidate_plate=candidate_plate, candidate_photo=candidate_photo,
                reviewed_by=old["reviewed_by"] if old and old["detected_plate"]==plate else None,
                reviewed_at=old["reviewed_at"] if old and old["detected_plate"]==plate else None,
                status=status, similarity=candidate.get("similarity", 1 if status=="EXACT" else 0) if candidate else 0,
                confidence=record.get("confidence") or 0,
                camera_id=camera["id"] if camera else None, location=camera["name"] if camera else record.get("location"),
                lat=camera["lat"] if camera else None, lng=camera["lng"] if camera else None,
                captured_at=at.isoformat(), epoch=at.timestamp(),
                district=record.get("district"), operator_username=record.get("operator_username"),
                plate_photo=plate_photo or (old["plate_photo"] if old else None),
                vehicle_photo=vehicle_photo or (old["vehicle_photo"] if old else None),
                case_info=json.dumps({k:candidate.get(k) for k in ("offence_type","fir_number","police_station")} if candidate else {}))
            columns=list(values)
            updates=", ".join(f"{k}=excluded.{k}" for k in columns if k!="capture_id")
            conn.execute(f"INSERT INTO observations ({','.join(columns)}) VALUES ({','.join('?' for k in columns)}) ON CONFLICT(capture_id) DO UPDATE SET {updates}",list(values.values()))
            conn.commit()
            return dict(conn.execute("SELECT * FROM observations WHERE capture_id=?",(capture_id,)).fetchone())

    @staticmethod
    def scope(district=None, operator=None):
        clauses=[];params=[]
        if district:
            clauses.append("LOWER(district)=LOWER(?)");params.append(district)
        if operator:
            clauses.append("LOWER(operator_username)=LOWER(?)");params.append(operator)
        return (" AND ".join(clauses) or "1=1"),params

    def list(self,district=None,operator=None):
        where,params=self.scope(district,operator)
        with closing(self.connect()) as conn:
            return [dict(r) for r in conn.execute(f"SELECT * FROM observations WHERE {where} AND LENGTH(detected_plate) BETWEEN 8 AND 11 ORDER BY epoch DESC,id DESC",params)]

    def clear(self, district=None, operator=None):
        """Clear scoped review entries and prevent old captures being imported again."""
        where, params = self.scope(district, operator)
        with closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(f"SELECT capture_id,plate_photo,vehicle_photo FROM observations WHERE {where}", params).fetchall()
            conn.executemany("INSERT OR IGNORE INTO cleared_captures(capture_id) VALUES (?)", [(r['capture_id'],) for r in rows])
            conn.execute(f"DELETE FROM observations WHERE {where}", params)
            conn.commit()
        for row in rows:
            for key in ('plate_photo', 'vehicle_photo'):
                if row[key]:
                    photo = (self.photos / Path(row[key]).name).resolve()
                    if photo.parent == self.photos.resolve():
                        photo.unlink(missing_ok=True)
        return len(rows)

    def decide(self, observation_id, decision, reviewer, district=None, operator=None, expected_plate=None, expected_candidate=None):
        if decision not in ("SAME","NOT_SAME"):
            raise ValueError("Choose Same or Not Same")
        where,params=self.scope(district,operator)
        with closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute(f"SELECT * FROM observations WHERE id=? AND {where}",[observation_id]+params).fetchone()
            if not row:
                raise LookupError("Sighting not found in your scope")
            if expected_plate is not None and (row["detected_plate"] != expected_plate or row["candidate_plate"] != expected_candidate):
                raise ValueError("The evidence changed. Refresh and review the current photos.")
            if row["status"] != "PENDING":
                if row["status"]==decision:
                    return dict(row)
                raise ValueError("This sighting has already been resolved")
            if decision=="SAME":
                candidate=self.watchlist.get_by_id(row["candidate_id"])
                if not candidate or candidate.get("status")!="ACTIVE" or candidate["vehicle_number"]!=row["candidate_plate"]:
                    raise ValueError("The registered vehicle changed. Refresh before confirming.")
            route_plate=row["candidate_plate"] if decision=="SAME" else row["detected_plate"]
            if not route_plate:
                raise ValueError("Matched vehicle is unavailable")
            conn.execute("UPDATE observations SET status=?,route_plate=?,reviewed_by=?,reviewed_at=? WHERE id=?",(decision,route_plate,reviewer,datetime.datetime.now(IST).isoformat(),observation_id))
            conn.commit()
            return dict(conn.execute("SELECT * FROM observations WHERE id=?",(observation_id,)).fetchone())

@lru_cache(maxsize=16)
def review_store(directory):
    return TrailReviewDB(directory)
