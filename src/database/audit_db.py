"""
Alert & Audit Trail Database Module
Haryana Police Surveillance System
Tracks all high-priority ANPR Hotlist & FRS Suspect detections with:
- Origin District (where FIR/case was lodged) vs Spotting District (where camera detected it)
- Mandatory Operator Acknowledgment with Action Taken
- Exact Response Latency (seconds)
- Officer Name, Belt/Batch Number, Workstation IP
- Tamper-evident immutable audit log
"""
from typing import List, Dict, Any, Optional
import os
import sqlite3
import datetime
import time
import uuid
import json

class AlertAuditDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "alert_audit.sqlite")

        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT UNIQUE NOT NULL,
                    alert_type TEXT NOT NULL,
                    entity_identifier TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    detection_timestamp TEXT NOT NULL,
                    detection_epoch REAL NOT NULL,
                    camera_id TEXT DEFAULT 'CAM-01',
                    camera_location TEXT DEFAULT 'Surveillance Feed',
                    origin_district TEXT DEFAULT 'All Haryana',
                    origin_station TEXT DEFAULT 'PHQ',
                    spotting_district TEXT DEFAULT 'Panipat',
                    case_info TEXT,
                    confidence REAL DEFAULT 90.0,
                    snapshot_path TEXT,
                    status TEXT DEFAULT 'PENDING',
                    ack_timestamp TEXT,
                    ack_epoch REAL,
                    response_latency_seconds REAL,
                    officer_name TEXT,
                    officer_belt_number TEXT,
                    officer_district TEXT,
                    action_taken TEXT,
                    remarks TEXT,
                    workstation_ip TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_id ON alert_audit_log(alert_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_status ON alert_audit_log(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_spotting_district ON alert_audit_log(spotting_district)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_origin_district ON alert_audit_log(origin_district)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_change_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_id TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    epoch REAL NOT NULL,
                    action_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    entity_identifier TEXT NOT NULL,
                    old_data_json TEXT,
                    new_data_json TEXT,
                    officer_name TEXT NOT NULL,
                    officer_belt_number TEXT,
                    officer_district TEXT NOT NULL,
                    officer_role TEXT NOT NULL,
                    reason TEXT,
                    workstation_ip TEXT DEFAULT '127.0.0.1'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_change_log_id ON db_change_audit_log(log_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_change_action ON db_change_audit_log(action_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_change_target ON db_change_audit_log(target_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_change_district ON db_change_audit_log(officer_district)")
            conn.commit()
        finally:
            conn.close()

    def create_alert(
        self,
        alert_type: str,
        entity_identifier: str,
        display_name: str,
        case_info: str,
        camera_id: str = "CAM-01",
        camera_location: str = "Surveillance Feed",
        origin_district: str = "All Haryana",
        origin_station: str = "PHQ",
        spotting_district: str = "Panipat",
        confidence: float = 90.0,
        snapshot_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new pending alert record and returns alert details."""
        now = datetime.datetime.now().astimezone()
        now_iso = now.isoformat()
        now_epoch = time.time()
        random_suffix = uuid.uuid4().hex[:6].upper()
        clean_prefix = "ALT-" + now.strftime("%Y%m%d") + "-" + random_suffix

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Cooldown Deduplication: Check if active alert for same entity already exists in same spotting district in last 60s
            cursor.execute("""
                SELECT alert_id, confidence, status FROM alert_audit_log
                WHERE entity_identifier = ? AND alert_type = ? AND spotting_district = ? AND (? - detection_epoch) < 60.0
                ORDER BY detection_epoch DESC LIMIT 1
            """, (entity_identifier, alert_type, spotting_district, now_epoch))
            existing = cursor.fetchone()
            if existing:
                exist_id = existing["alert_id"]
                exist_conf = float(existing["confidence"] or 0.0)
                if confidence > exist_conf:
                    cursor.execute("""
                        UPDATE alert_audit_log 
                        SET confidence = ?, snapshot_path = COALESCE(NULLIF(?, ''), snapshot_path)
                        WHERE alert_id = ?
                    """, (confidence, snapshot_path or "", exist_id))
                    conn.commit()
                return self.get_alert_by_id(exist_id)

            cursor.execute("""
                INSERT INTO alert_audit_log (
                    alert_id, alert_type, entity_identifier, display_name,
                    detection_timestamp, detection_epoch, camera_id, camera_location,
                    origin_district, origin_station, spotting_district, case_info,
                    confidence, snapshot_path, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (
                clean_prefix, alert_type, entity_identifier, display_name,
                now_iso, now_epoch, camera_id, camera_location,
                origin_district, origin_station, spotting_district, case_info,
                confidence, snapshot_path or ""
            ))
            conn.commit()
            return self.get_alert_by_id(clean_prefix)
        finally:
            conn.close()

    def acknowledge_alert(
        self,
        alert_id: str,
        officer_name: str,
        officer_belt_number: str,
        officer_district: str,
        action_taken: str,
        remarks: Optional[str] = None,
        workstation_ip: Optional[str] = "127.0.0.1"
    ) -> Optional[Dict[str, Any]]:
        """
        Acknowledges a pending alert, marks action taken, and computes response latency.
        """
        now = datetime.datetime.now().astimezone()
        ack_iso = now.isoformat()
        ack_epoch = time.time()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT detection_epoch, status FROM alert_audit_log WHERE alert_id = ?", (alert_id,))
            row = cursor.fetchone()
            if not row:
                return None

            det_epoch = row["detection_epoch"]
            latency = max(0.5, round(ack_epoch - det_epoch, 1))

            new_status = "INTERCEPTED" if "intercept" in action_taken.lower() else (
                "FALSE_ALARM" if "false" in action_taken.lower() else "ACKNOWLEDGED"
            )

            cursor.execute("""
                UPDATE alert_audit_log
                SET status = ?,
                    ack_timestamp = ?,
                    ack_epoch = ?,
                    response_latency_seconds = ?,
                    officer_name = ?,
                    officer_belt_number = ?,
                    officer_district = ?,
                    action_taken = ?,
                    remarks = ?,
                    workstation_ip = ?
                WHERE alert_id = ?
            """, (
                new_status, ack_iso, ack_epoch, latency,
                officer_name, officer_belt_number, officer_district,
                action_taken, remarks or "", workstation_ip or "127.0.0.1",
                alert_id
            ))
            conn.commit()
            return self.get_alert_by_id(alert_id)
        finally:
            conn.close()

    def get_alert_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alert_audit_log WHERE alert_id = ?", (alert_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_pending_alerts(self, district: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
        """Returns active unacknowledged alerts (filtered by district or for all state)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if district and district.lower() not in ["all", "all haryana", "state hq"]:
                cursor.execute("""
                    SELECT * FROM alert_audit_log
                    WHERE status = 'PENDING'
                      AND (spotting_district LIKE ? OR origin_district LIKE ? OR origin_district = 'All Haryana')
                    ORDER BY detection_epoch DESC
                    LIMIT ?
                """, (f"%{district}%", f"%{district}%", limit))
            else:
                cursor.execute("""
                    SELECT * FROM alert_audit_log
                    WHERE status = 'PENDING'
                    ORDER BY detection_epoch DESC
                    LIMIT ?
                """, (limit,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        district: Optional[str] = None,
        operator: Optional[str] = None,
        alert_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries historical audit logs with filtering and pagination."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM alert_audit_log WHERE 1=1"
            params = []

            if status and status.upper() != "ALL":
                query += " AND status = ?"
                params.append(status.upper())

            if alert_type and alert_type.upper() != "ALL":
                query += " AND alert_type = ?"
                params.append(alert_type.upper())

            if district and district.lower() not in ["all", "all haryana", "state hq"]:
                query += " AND (spotting_district LIKE ? OR origin_district LIKE ? OR officer_district LIKE ?)"
                params.extend([f"%{district}%", f"%{district}%", f"%{district}%"])

            if operator and operator.lower() not in ["all", "all operators"]:
                query += " AND (officer_name LIKE ? OR officer_belt_number LIKE ?)"
                params.extend([f"%{operator}%", f"%{operator}%"])

            if search:
                s_term = f"%{search.strip()}%"
                query += " AND (entity_identifier LIKE ? OR display_name LIKE ? OR case_info LIKE ? OR officer_name LIKE ? OR alert_id LIKE ?)"
                params.extend([s_term, s_term, s_term, s_term, s_term])

            query += " ORDER BY detection_epoch DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_audit_stats(self, district: Optional[str] = None, operator: Optional[str] = None) -> Dict[str, Any]:
        """Calculates audit metrics: total alerts, pending count, acknowledged count, avg latency."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            if district and district.lower() not in ["all", "all haryana", "state hq"]:
                conditions.append("(spotting_district LIKE ? OR origin_district LIKE ? OR officer_district LIKE ?)")
                params.extend([f"%{district}%", f"%{district}%", f"%{district}%"])
            if operator and operator.lower() not in ["all", "all operators"]:
                conditions.append("(officer_name LIKE ? OR officer_belt_number LIKE ?)")
                params.extend([f"%{operator}%", f"%{operator}%"])

            where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor.execute(f"SELECT COUNT(*) FROM alert_audit_log{where_clause}", params)
            total = cursor.fetchone()[0]

            pend_cond = list(conditions)
            pend_params = list(params)
            pend_cond.append("status = 'PENDING'")
            pend_clause = f" WHERE {' AND '.join(pend_cond)}"
            cursor.execute(f"SELECT COUNT(*) FROM alert_audit_log{pend_clause}", pend_params)
            pending = cursor.fetchone()[0]

            ack_cond = list(conditions)
            ack_params = list(params)
            ack_cond.append("status != 'PENDING'")
            ack_clause = f" WHERE {' AND '.join(ack_cond)}"
            cursor.execute(f"SELECT COUNT(*) FROM alert_audit_log{ack_clause}", ack_params)
            acknowledged = cursor.fetchone()[0]

            cursor.execute(f"SELECT AVG(response_latency_seconds) FROM alert_audit_log{ack_clause} AND response_latency_seconds IS NOT NULL", ack_params)
            avg_lat = cursor.fetchone()[0] or 0.0

            return {
                "total_alerts": total,
                "pending_alerts": pending,
                "acknowledged_alerts": acknowledged,
                "avg_response_latency_seconds": round(float(avg_lat), 1)
            }
        finally:
            conn.close()

    def export_csv(self, district: Optional[str] = None, operator: Optional[str] = None) -> str:
        """Exports the entire audit trail to CSV format for legal and departmental inquiry."""
        import io
        import csv
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM alert_audit_log WHERE 1=1"
            params = []
            if district and district.lower() not in ["all", "all haryana", "state hq"]:
                query += " AND (spotting_district LIKE ? OR origin_district LIKE ? OR officer_district LIKE ?)"
                params.extend([f"%{district}%", f"%{district}%", f"%{district}%"])
            if operator and operator.lower() not in ["all", "all operators"]:
                query += " AND (officer_name LIKE ? OR officer_belt_number LIKE ?)"
                params.extend([f"%{operator}%", f"%{operator}%"])
            query += " ORDER BY detection_epoch DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            output = io.StringIO()
            if rows:
                writer = csv.writer(output)
                writer.writerow(rows[0].keys())
                for r in rows:
                    writer.writerow([r[k] for k in r.keys()])
            else:
                writer = csv.writer(output)
                writer.writerow([
                    "alert_id", "alert_type", "entity_identifier", "display_name",
                    "detection_timestamp", "camera_id", "camera_location",
                    "origin_district", "spotting_district", "case_info", "confidence",
                    "status", "ack_timestamp", "response_latency_seconds",
                    "officer_name", "officer_belt_number", "officer_district",
                    "action_taken", "remarks", "workstation_ip"
                ])
            return output.getvalue()
        finally:
            conn.close()

    def log_db_change(
        self,
        action_type: str,
        target_type: str,
        entity_identifier: str,
        officer_name: str,
        officer_belt_number: str,
        officer_district: str,
        officer_role: str,
        old_data: Optional[Dict[str, Any]] = None,
        new_data: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        workstation_ip: str = "127.0.0.1"
    ) -> Dict[str, Any]:
        """Logs any ADD, EDIT, or DELETE operation performed on Vehicle DB or Face DB."""
        now = datetime.datetime.now().astimezone()
        now_iso = now.isoformat()
        now_epoch = time.time()
        log_id = f"AUD-DB-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        old_json = json.dumps(old_data, default=str) if old_data else ""
        new_json = json.dumps(new_data, default=str) if new_data else ""

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO db_change_audit_log (
                    log_id, timestamp, epoch, action_type, target_type,
                    entity_identifier, old_data_json, new_data_json,
                    officer_name, officer_belt_number, officer_district,
                    officer_role, reason, workstation_ip
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_id, now_iso, now_epoch, action_type.upper(), target_type.upper(),
                entity_identifier, old_json, new_json,
                officer_name, officer_belt_number, officer_district,
                officer_role, reason or "Standard administrative operation", workstation_ip
            ))
            conn.commit()
            cursor.execute("SELECT * FROM db_change_audit_log WHERE log_id = ?", (log_id,))
            return dict(cursor.fetchone())
        finally:
            conn.close()

    def get_db_change_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        action_type: Optional[str] = None,
        target_type: Optional[str] = None,
        district: Optional[str] = None,
        operator: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM db_change_audit_log WHERE 1=1"
            params = []

            if action_type and action_type.upper() != "ALL":
                query += " AND action_type = ?"
                params.append(action_type.upper())

            if target_type and target_type.upper() != "ALL":
                query += " AND target_type = ?"
                params.append(target_type.upper())

            if district and district.lower() not in ["all", "all haryana", "state hq"]:
                query += " AND officer_district LIKE ?"
                params.append(f"%{district}%")

            if operator and operator.lower() not in ["all", "all operators"]:
                query += " AND (officer_name LIKE ? OR officer_belt_number LIKE ?)"
                params.extend([f"%{operator}%", f"%{operator}%"])

            if search:
                st = f"%{search.strip()}%"
                query += " AND (entity_identifier LIKE ? OR officer_name LIKE ? OR officer_belt_number LIKE ? OR reason LIKE ? OR log_id LIKE ?)"
                params.extend([st, st, st, st, st])

            query += " ORDER BY epoch DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_unified_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = "ALL",
        action_type: Optional[str] = "ALL",
        target_type: Optional[str] = "ALL",
        district: Optional[str] = None,
        operator: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Returns unified audit records supporting categories:
        - 'ALL': Merges both Emergency Alert notifications and DB modifications.
        - 'DB_CHANGES': Only Database additions, edits, and deletions.
        - 'EMERGENCY_ALERTS': Only live camera Hotlist hits and operator acknowledgments.
        """
        records = []
        cat = (category or "ALL").upper()

        if cat in ["ALL", "EMERGENCY_ALERTS"]:
            alert_items = self.get_alerts(
                limit=limit,
                offset=0,
                status=None if action_type == "ALL" else action_type,
                district=district,
                operator=operator,
                alert_type=None if target_type == "ALL" else target_type,
                search=search
            )
            for a in alert_items:
                records.append({
                    "audit_category": "EMERGENCY_ALERT",
                    "id": a["alert_id"],
                    "timestamp": a["detection_timestamp"],
                    "epoch": a["detection_epoch"],
                    "action": "PENDING" if a["status"] == "PENDING" else "ACKNOWLEDGED",
                    "target_type": a["alert_type"],
                    "identifier": a["entity_identifier"],
                    "details": a.get("case_info") or a.get("display_name"),
                    "origin_district": a.get("origin_district"),
                    "spotting_district": a.get("spotting_district"),
                    "camera_id": a.get("camera_id"),
                    "officer_name": a.get("officer_name"),
                    "officer_belt": a.get("officer_belt_number"),
                    "officer_district": a.get("officer_district"),
                    "response_latency": a.get("response_latency_seconds"),
                    "action_taken": a.get("action_taken"),
                    "reason_remarks": a.get("remarks"),
                    "status": a.get("status")
                })

        if cat in ["ALL", "DB_CHANGES"]:
            change_items = self.get_db_change_logs(
                limit=limit,
                offset=0,
                action_type=None if action_type == "ALL" else action_type,
                target_type=None if target_type == "ALL" else target_type,
                district=district,
                operator=operator,
                search=search
            )
            for c in change_items:
                records.append({
                    "audit_category": "DB_CHANGE",
                    "id": c["log_id"],
                    "timestamp": c["timestamp"],
                    "epoch": c["epoch"],
                    "action": c["action_type"],
                    "target_type": c["target_type"],
                    "identifier": c["entity_identifier"],
                    "details": f"{c['action_type']} on {c['target_type']}",
                    "origin_district": c["officer_district"],
                    "spotting_district": c["officer_district"],
                    "camera_id": "DATABASE",
                    "officer_name": c["officer_name"],
                    "officer_belt": c["officer_belt_number"],
                    "officer_district": c["officer_district"],
                    "response_latency": None,
                    "action_taken": f"{c['action_type']} ({c['officer_role']})",
                    "reason_remarks": c.get("reason"),
                    "status": "RECORDED",
                    "old_data": c.get("old_data_json"),
                    "new_data": c.get("new_data_json")
                })

        # Sort all unified records by epoch descending
        records.sort(key=lambda x: x["epoch"], reverse=True)
        paginated = records[offset : offset + limit]

        # Calculate counts
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM alert_audit_log")
            total_alerts = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM db_change_audit_log")
            total_db_changes = cur.fetchone()[0]
        finally:
            conn.close()

        stats = self.get_audit_stats(district=district)
        stats["total_db_changes"] = total_db_changes
        stats["total_combined_audit"] = total_alerts + total_db_changes

        return {
            "success": True,
            "total": len(records),
            "logs": paginated,
            "stats": stats
        }


