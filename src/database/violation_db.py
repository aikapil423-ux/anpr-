import sqlite3
import os
import json
import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "data/violations.db"

def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_violations (
                id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                camera_id TEXT,
                camera_location TEXT,
                plate_number TEXT,
                violation_type TEXT,
                rider_count INTEGER DEFAULT 1,
                unhelmeted_count INTEGER DEFAULT 1,
                helmet_fine INTEGER DEFAULT 1000,
                triple_fine INTEGER DEFAULT 0,
                applied_sections TEXT DEFAULT '[]',
                total_fine INTEGER DEFAULT 1000,
                evidence_image TEXT,
                raw_ocr_conf REAL DEFAULT 0.0,
                status TEXT DEFAULT 'PENDING'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_viol_plate ON traffic_violations(plate_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_viol_timestamp ON traffic_violations(timestamp)")
        conn.commit()

# Cooldown tracking buffer: {(camera_id, plate_number): (last_seen_datetime, viol_id)}
_COOLDOWN_CACHE: Dict[tuple, tuple] = {}
COOLDOWN_MINUTES = 5

def record_violation(
    plate_number: str,
    violation_type: str,
    rider_count: int,
    unhelmeted_count: int,
    camera_id: str = "CAM_01",
    camera_location: str = "Surveillance Checkpost",
    helmet_fine: int = 1000,
    triple_fine: int = 0,
    applied_sections: Optional[List[Dict[str, Any]]] = None,
    evidence_image: str = "",
    raw_ocr_conf: float = 0.0,
    cooldown_window_min: int = COOLDOWN_MINUTES
) -> Optional[Dict[str, Any]]:
    """
    Records a new traffic violation with deduplication cooldown.
    Returns the created record dict, or existing record if skipped due to cooldown.
    """
    now = datetime.datetime.now()
    norm_plate = (plate_number or "UNKNOWN").upper().strip()
    cache_key = (camera_id, norm_plate)

    # Deduplication check
    if norm_plate != "UNKNOWN" and cache_key in _COOLDOWN_CACHE:
        last_seen, cached_viol_id = _COOLDOWN_CACHE[cache_key]
        if (now - last_seen).total_seconds() < (cooldown_window_min * 60):
            # Duplicate within cooldown window -> Return existing violation ID without creating duplicate
            return {"id": cached_viol_id, "status": "COOLDOWN_SKIPPED", "plate_number": norm_plate}

    # Calculate Total Fine
    sections_list = applied_sections or []
    sections_fine = sum(s.get("fine", 0) for s in sections_list)
    total_fine = (unhelmeted_count * helmet_fine) + triple_fine + sections_fine

    # Generate unique ID
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    viol_id = f"VIOL_{norm_plate[:6]}_{ts_str}"

    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO traffic_violations (
                id, timestamp, camera_id, camera_location, plate_number,
                violation_type, rider_count, unhelmeted_count, helmet_fine,
                triple_fine, applied_sections, total_fine, evidence_image,
                raw_ocr_conf, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """, (
            viol_id, now.isoformat(), camera_id, camera_location, norm_plate,
            violation_type, rider_count, unhelmeted_count, helmet_fine,
            triple_fine, json.dumps(sections_list), total_fine, evidence_image,
            raw_ocr_conf
        ))
        conn.commit()

    if norm_plate != "UNKNOWN":
        _COOLDOWN_CACHE[cache_key] = (now, viol_id)

    return get_violation_by_id(viol_id)

def get_violation_by_id(viol_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM traffic_violations WHERE id = ?", (viol_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["applied_sections"] = json.loads(d.get("applied_sections") or "[]")
        except:
            d["applied_sections"] = []
        return d

def get_violations(
    plate_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Fetches violations with optional plate and type filters."""
    query = "SELECT * FROM traffic_violations WHERE 1=1"
    params = []

    if plate_filter:
        query += " AND plate_number LIKE ?"
        params.append(f"%{plate_filter.strip().upper()}%")

    if type_filter and type_filter != "ALL":
        if type_filter == "TRIPLE":
            query += " AND (violation_type LIKE '%TRIPLE%' OR triple_fine > 0)"
        elif type_filter == "NO_HELMET":
            query += " AND (violation_type LIKE '%HELMET%' OR unhelmeted_count > 0)"

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    results = []
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        for r in rows:
            d = dict(r)
            try:
                d["applied_sections"] = json.loads(d.get("applied_sections") or "[]")
            except:
                d["applied_sections"] = []
            results.append(d)
    return results

def update_violation_penalty(
    viol_id: str,
    unhelmeted_count: int,
    applied_sections: List[Dict[str, Any]],
    total_fine: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Allows operator to adjust unhelmeted multiplier and add/remove MV Act sections."""
    current = get_violation_by_id(viol_id)
    if not current:
        return None

    if total_fine is not None and total_fine > 0:
        new_total = total_fine
    else:
        helmet_unit_fine = current.get("helmet_fine", 1000)
        triple_fine = current.get("triple_fine", 0)
        sections_fine = sum(s.get("fine", 0) for s in applied_sections)
        new_total = (unhelmeted_count * helmet_unit_fine) + triple_fine + sections_fine

    with get_db_connection() as conn:
        conn.execute("""
            UPDATE traffic_violations
            SET unhelmeted_count = ?, applied_sections = ?, total_fine = ?
            WHERE id = ?
        """, (unhelmeted_count, json.dumps(applied_sections), new_total, viol_id))
        conn.commit()

    return get_violation_by_id(viol_id)

def get_violation_stats() -> Dict[str, Any]:
    with get_db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM traffic_violations").fetchone()[0]
        triple = conn.execute("SELECT COUNT(*) FROM traffic_violations WHERE violation_type LIKE '%TRIPLE%' OR triple_fine > 0").fetchone()[0]
        no_helmet = conn.execute("SELECT COUNT(*) FROM traffic_violations WHERE violation_type LIKE '%HELMET%' OR unhelmeted_count > 0").fetchone()[0]
        fines = conn.execute("SELECT COALESCE(SUM(total_fine), 0) FROM traffic_violations").fetchone()[0]

    return {
        "total_violations": total,
        "triple_riding_count": triple,
        "without_helmet_count": no_helmet,
        "total_penalty_assessed": fines
    }

# Auto-initialize DB on import
init_db()
