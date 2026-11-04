"""
Haryana Police Surveillance System - Authentication & User Management DB
Handles RBAC (Role-Based Access Control) with PBKDF2 cryptographic hashing.
Roles:
- STATE_ADMIN: Complete statewide access, creates District Admins, resets any password.
- DISTRICT_ADMIN: District-locked access, creates Operators for own district, resets operator passwords.
- OPERATOR: Data entry & live surveillance only, cannot delete/edit entries, no user management.
"""

from typing import List, Dict, Any, Optional
import os
import sqlite3
import datetime
import hashlib
import binascii

class AuthDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "auth_users.sqlite")

        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """Hashes password with PBKDF2-HMAC-SHA256 and salt."""
        if not salt:
            salt = binascii.hexlify(os.urandom(16)).decode('utf-8')
        iterations = 100000
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations
        )
        hash_str = binascii.hexlify(key).decode('utf-8')
        return hash_str, salt

    @staticmethod
    def verify_password(password: str, stored_hash: str, salt: str) -> bool:
        """Verifies if input password matches the stored cryptographic hash."""
        computed_hash, _ = AuthDB.hash_password(password, salt)
        return computed_hash == stored_hash

    def _init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    belt_number TEXT,
                    role TEXT NOT NULL,
                    district TEXT NOT NULL,
                    station TEXT DEFAULT 'PHQ',
                    created_by_user TEXT DEFAULT 'SYSTEM',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_role ON users(role)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_district ON users(district)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_token ON user_sessions(session_token)")
            conn.commit()

            # Ensure standard test & quick-login accounts always exist and are active
            seed_accounts = [
                (
                    "admin_karnal", "KarnalAdmin@2026", "Karnal Demo District Admin", "DEMO-KNL-ADMIN",
                    "DISTRICT_ADMIN", "Karnal", "ICCC Karnal", "stateadmin"
                ),
                (
                    "op_karnal", "KarnalOperator@123", "Karnal Demo Operator", "DEMO-KNL-OP",
                    "OPERATOR", "Karnal", "ICCC Karnal", "admin_karnal"
                ),
                (
                    "stateadmin", "HaryanaPolice@HQ2026", "State Police HQ Admin", "HP-HQ-001",
                    "STATE_ADMIN", "All Haryana (State HQ)", "DGP Headquarters Panchkula", "SYSTEM"
                ),
                (
                    "admin_panipat", "PanipatAdmin@2026", "DSP Rakesh Sharma", "HR-PPT-01",
                    "DISTRICT_ADMIN", "Panipat", "SP Office Panipat", "stateadmin"
                ),
                (
                    "op_5421", "Operator@123", "Constable Amit Kumar", "5421/PPT",
                    "OPERATOR", "Panipat", "North Toll Gate Checkpoint", "admin_panipat"
                ),
                (
                    "op_kaithal", "KaithalOperator@123", "Constable Vikas Singh", "8921/KTL",
                    "OPERATOR", "Kaithal", "Kaithal Border Checkpost", "stateadmin"
                ),
                (
                    "developer_admin", "8221029402", "Developer Admin (Demo Sandbox)", "DEV-001",
                    "DEVELOPER_ADMIN", "All Haryana (State HQ)", "State Cyber & Forensics HQ", "SYSTEM"
                )
            ]

            now = datetime.datetime.now().astimezone().isoformat()
            for username, pwd, name, belt, role, dist, station, creator in seed_accounts:
                cursor.execute("SELECT user_id, is_active FROM users WHERE username = ?", (username,))
                row = cursor.fetchone()
                if not row:
                    p_hash, salt = self.hash_password(pwd)
                    cursor.execute("""
                        INSERT INTO users (
                            username, password_hash, salt, full_name, belt_number,
                            role, district, station, created_by_user, is_active, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (username, p_hash, salt, name, belt, role, dist, station, creator, now))
                elif row[1] == 0:
                    cursor.execute("UPDATE users SET is_active = 1 WHERE user_id = ?", (row[0],))
            conn.commit()
        finally:
            conn.close()

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verifies credentials and updates last login timestamp."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username.strip().lower(),))
            row = cursor.fetchone()
            if not row:
                return None

            user_dict = dict(row)
            if self.verify_password(password, user_dict["password_hash"], user_dict["salt"]):
                now = datetime.datetime.now().astimezone().isoformat()
                cursor.execute("UPDATE users SET last_login = ? WHERE user_id = ?", (now, user_dict["user_id"]))
                conn.commit()
                # Remove sensitive hash/salt before returning
                del user_dict["password_hash"]
                del user_dict["salt"]
                user_dict["last_login"] = now
                return user_dict
            return None
        finally:
            conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            user_dict = dict(row)
            user_dict.pop("password_hash", None)
            user_dict.pop("salt", None)
            return user_dict
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
            row = cursor.fetchone()
            if not row:
                return None
            user_dict = dict(row)
            user_dict.pop("password_hash", None)
            user_dict.pop("salt", None)
            return user_dict
        finally:
            conn.close()

    def create_user(
        self,
        username: str,
        password: str,
        full_name: str,
        belt_number: str,
        role: str,
        district: str,
        station: str,
        created_by_user: str
    ) -> Dict[str, Any]:
        """Creates a new user with PBKDF2 hash. Raises ValueError on duplicate or invalid data."""
        clean_username = username.strip().lower()
        if not clean_username or len(clean_username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not password or len(password) < 4:
            raise ValueError("Password must be at least 4 characters")

        valid_roles = ["STATE_ADMIN", "DISTRICT_ADMIN", "OPERATOR"]
        if role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of {valid_roles}")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (clean_username,))
            if cursor.fetchone():
                raise ValueError(f"Username '{clean_username}' already exists. Please choose a different username.")

            p_hash, salt = self.hash_password(password)
            now = datetime.datetime.now().astimezone().isoformat()

            cursor.execute("""
                INSERT INTO users (
                    username, password_hash, salt, full_name, belt_number,
                    role, district, station, created_by_user, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                clean_username, p_hash, salt, full_name.strip(), belt_number.strip(),
                role, district.strip(), station.strip() or "General Duty", created_by_user, now
            ))
            conn.commit()
            new_id = cursor.lastrowid
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (new_id,))
            row = cursor.fetchone()
            if row:
                u_dict = dict(row)
                u_dict.pop("password_hash", None)
                u_dict.pop("salt", None)
                return u_dict
            return {}
        finally:
            conn.close()

    def list_users(self, requesting_role: str, requesting_district: str) -> List[Dict[str, Any]]:
        """
        Lists users based on hierarchy:
        - STATE_ADMIN: Can view all District Admins and Operators.
        - DISTRICT_ADMIN: Can view ONLY Operators of their own district.
        - OPERATOR: Cannot list users (returns empty).
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if requesting_role == "STATE_ADMIN":
                cursor.execute("""
                    SELECT user_id, username, full_name, belt_number, role, district,
                           station, created_by_user, is_active, created_at, last_login
                    FROM users
                    ORDER BY role ASC, district ASC, created_at DESC
                """)
            elif requesting_role == "DISTRICT_ADMIN":
                cursor.execute("""
                    SELECT user_id, username, full_name, belt_number, role, district,
                           station, created_by_user, is_active, created_at, last_login
                    FROM users
                    WHERE district = ? AND role IN ('DISTRICT_ADMIN', 'OPERATOR')
                    ORDER BY role ASC, created_at DESC
                """, (requesting_district,))
            else:
                return []
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def reset_password(self, target_user_id: int, new_password: str, requesting_user: Dict[str, Any]) -> bool:
        """
        Reset password hierarchy enforcement:
        - State Admin can reset password for District Admins and Operators.
        - District Admin can reset password ONLY for Operators in their district.
        - Operator cannot reset any password.
        """
        if not new_password or len(new_password) < 4:
            raise ValueError("New password must be at least 4 characters")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            target = cursor.fetchone()
            if not target:
                raise ValueError("Target user not found")

            target_dict = dict(target)
            req_role = requesting_user.get("role")
            req_district = requesting_user.get("district")

            if req_role == "STATE_ADMIN":
                # State admin can reset anyone except if trying to lock out
                pass
            elif req_role == "DISTRICT_ADMIN":
                # District admin can ONLY reset OPERATOR in their own district
                if target_dict["role"] != "OPERATOR":
                    raise PermissionError("District Admin can only reset passwords for Duty Operators.")
                if target_dict["district"] != req_district:
                    raise PermissionError("Cannot reset password for an operator from another district.")
            else:
                raise PermissionError("Operators are not authorized to reset passwords.")

            p_hash, salt = self.hash_password(new_password)
            cursor.execute("UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?", (p_hash, salt, target_user_id))
            conn.commit()
            return True
        finally:
            conn.close()

    def save_session(self, session_token: str, user_dict: Dict[str, Any]):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.datetime.now().astimezone().isoformat()
            cursor.execute(
                "INSERT OR REPLACE INTO user_sessions (session_token, user_id, created_at) VALUES (?, ?, ?)",
                (session_token, user_dict["user_id"], now)
            )
            conn.commit()
        except Exception as e:
            print(f"[AuthDB] Failed to save session: {e}")
        finally:
            conn.close()

    def get_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT u.* FROM users u
                INNER JOIN user_sessions s ON u.user_id = s.user_id
                WHERE s.session_token = ? AND u.is_active = 1
                """,
                (session_token,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            user_dict = dict(row)
            user_dict.pop("password_hash", None)
            user_dict.pop("salt", None)
            return user_dict
        except Exception as e:
            print(f"[AuthDB] Failed to get session: {e}")
            return None
        finally:
            conn.close()

    def delete_session(self, session_token: str):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_sessions WHERE session_token = ?", (session_token,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

