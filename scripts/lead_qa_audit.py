"""
Comprehensive Lead QA Test Suite - Haryana Police Unified FRS & ANPR System
Tests Authentication, Role-based Access, Route Validation, File Ingestion, Database Locks, and Streaming.
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import time
import os
import sqlite3

BASE_URL = "http://127.0.0.1:8000"

def run_deep_qa():
    print("=" * 80)
    print("📋 HARYANA POLICE SURVEILLANCE SYSTEM - COMPREHENSIVE QA AUDIT EXECUTION")
    print("=" * 80)
    
    findings = []
    
    # -------------------------------------------------------------
    # SECTION 1: AUTHENTICATION & ACCESS CONTROL (RBAC)
    # -------------------------------------------------------------
    print("\n[SECTION 1] Authentication, Session Security & RBAC Integrity")
    unauth_session = requests.Session()
    
    # 1.1 Unauthenticated access to sensitive administrative endpoints
    sensitive_endpoints = [
        ("GET", "/api/users/list", "Officer User Database"),
        ("GET", "/api/vehicles", "Master Hotlist Registry"),
        ("GET", "/api/captured", "Live Captured Vehicle Plates"),
        ("GET", "/api/frs/captured", "Live Captured Suspect Faces"),
        ("GET", "/api/alerts/audit-log", "Emergency Hotlist Audit Logs"),
        ("GET", "/api/camera/status", "Live Surveillance Stream Status")
    ]
    
    for method, path, desc in sensitive_endpoints:
        r = unauth_session.get(f"{BASE_URL}{path}", allow_redirects=False, timeout=4)
        if r.status_code == 200:
            findings.append({
                "id": "SEC-01",
                "severity": "P1 - HIGH (SECURITY)",
                "category": "Authorization & Privacy",
                "title": f"Unauthenticated access allowed on {desc} ({path})",
                "impact": f"Any person on the local network (Wi-Fi/LAN) can query {path} without logging in and dump police surveillance data.",
                "reproduction": f"curl -X GET http://<server_ip>:8000{path}",
                "recommendation": "Apply @require_auth or check_session dependency to ensure non-logged-in requests receive HTTP 401 Unauthorized."
            })
            print(f"  ❌ Security Leak: Unauthenticated 200 OK on {path} ({desc})")
        else:
            print(f"  ✅ Protected ({r.status_code}): {path}")

    # 1.2 Brute-force & Invalid Login Testing
    bad_login = unauth_session.post(f"{BASE_URL}/api/auth/login", data={"username": "invalid_user", "password": "WrongPassword!99"}, timeout=4)
    print(f"  Invalid login status: {bad_login.status_code} (Expected 401)")
    if bad_login.status_code != 401:
        findings.append({
            "id": "AUTH-01",
            "severity": "P2 - MEDIUM",
            "category": "Authentication",
            "title": "Invalid credentials did not return HTTP 401",
            "impact": f"Returned HTTP {bad_login.status_code} instead of 401 Unauthorized.",
            "reproduction": "POST /api/auth/login with wrong password",
            "recommendation": "Return HTTP 401 for invalid login attempts."
        })

    # 1.3 State Admin Login
    admin_session = requests.Session()
    login_resp = admin_session.post(f"{BASE_URL}/api/auth/login", data={"username": "stateadmin", "password": "HaryanaPolice@HQ2026"}, timeout=5)
    print(f"  Admin login status: {login_resp.status_code}")
    if login_resp.status_code != 200 or "session_token" not in admin_session.cookies:
        findings.append({
            "id": "AUTH-02",
            "severity": "P0 - BLOCKER",
            "category": "Authentication",
            "title": "State Admin login failed or session cookie was not set",
            "impact": "Administrators cannot authenticate to access surveillance features.",
            "reproduction": "POST /api/auth/login with stateadmin credentials",
            "recommendation": "Ensure login endpoint sets session_token cookie with SameSite and HttpOnly flags."
        })

    # 1.4 Operator Privilege Escalation Test (RBAC Boundary)
    op_session = requests.Session()
    op_login = op_session.post(f"{BASE_URL}/api/auth/login", data={"username": "op_5421", "password": "HaryanaPolice@HQ2026"}, timeout=5)
    if op_login.status_code == 200:
        # Operator tries to create user or view all users
        op_user_list = op_session.get(f"{BASE_URL}/api/users/list", timeout=4)
        print(f"  Operator accessing /api/users/list status: {op_user_list.status_code}")
        if op_user_list.status_code == 200:
            findings.append({
                "id": "SEC-02",
                "severity": "P1 - HIGH (RBAC)",
                "category": "Privilege Escalation",
                "title": "Constable/Operator can view administrative user management list",
                "impact": "Field operators with low clearance can inspect District Admin and State Admin user accounts.",
                "reproduction": "Login as op_5421, then GET /api/users/list",
                "recommendation": "Enforce strict role check (require_role('STATE_ADMIN', 'DISTRICT_ADMIN'))."
            })

    # -------------------------------------------------------------
    # SECTION 2: FUNCTIONAL API ENDPOINT VALIDATION & LATENCY
    # -------------------------------------------------------------
    print("\n[SECTION 2] Functional API Endpoints & Response Latency")
    api_tests = [
        ("GET", "/api/auth/me", "Current Officer Profile"),
        ("GET", "/api/camera/status", "All Camera Status"),
        ("GET", "/api/camera/demo-videos", "Demo Video Manifest"),
        ("GET", "/api/camera/layers", "HUD Layers Config"),
        ("GET", "/api/models/catalog", "AI Models Catalog"),
        ("GET", "/api/vehicles?limit=10", "Master Hotlist Query"),
        ("GET", "/api/vehicles/search-full?q=HR26", "Vehicle Plate Search"),
        ("GET", "/api/captured?limit=10", "Captured ANPR Plates"),
        ("GET", "/api/frs/gallery", "FRS Suspects Gallery"),
        ("GET", "/api/frs/captured?limit=10", "Captured Face Gallery"),
        ("GET", "/api/frs/stats", "FRS Biometric Telemetry"),
        ("GET", "/api/trails?limit=10", "Vehicle Geolocation Trails"),
        ("GET", "/api/alerts/active?district=Panipat", "Live Emergency Alerts"),
        ("GET", "/api/alerts/audit-log?limit=10", "Alert Audit Trail"),
        ("GET", "/api/alerts/stats", "District Crime & Hotlist Stats"),
        ("GET", "/api/unified/live-feed?limit=10", "Unified Multimodal Feed"),
        ("GET", "/api/districts", "Haryana 22 Districts List")
    ]

    for method, path, desc in api_tests:
        t0 = time.time()
        try:
            r = admin_session.get(f"{BASE_URL}{path}", timeout=6)
            lat = (time.time() - t0) * 1000
            if r.status_code == 200:
                print(f"  ✅ 200 OK ({lat:5.1f}ms) | {desc:<28} | {path}")
                if lat > 2000:
                    findings.append({
                        "id": "PERF-01",
                        "severity": "P2 - MEDIUM (LATENCY)",
                        "category": "Performance",
                        "title": f"Slow API endpoint: {path} ({lat:.0f}ms)",
                        "impact": "Exceeds 2000ms latency budget; causes UI freeze in live surveillance.",
                        "reproduction": f"GET {path}",
                        "recommendation": "Add database index or cache responses."
                    })
            else:
                findings.append({
                    "id": "FUNC-01",
                    "severity": "P1 - HIGH",
                    "category": "API Failure",
                    "title": f"Endpoint {path} failed with HTTP {r.status_code}",
                    "impact": f"Feature '{desc}' is broken for users.",
                    "reproduction": f"GET {path}",
                    "recommendation": f"Inspect backend logs for error: {r.text[:200]}"
                })
                print(f"  ❌ HTTP {r.status_code} ({lat:5.1f}ms) | {desc:<28} | {path}")
        except Exception as e:
            findings.append({
                "id": "FUNC-02",
                "severity": "P0 - BLOCKER",
                "category": "Endpoint Crash/Timeout",
                "title": f"Endpoint {path} timed out or threw exception",
                "impact": f"Fatal error on {desc}: {e}",
                "reproduction": f"GET {path}",
                "recommendation": "Check backend exception handling and timeout limits."
            })
            print(f"  💥 EXCEPTION | {desc:<28} | {e}")

    # -------------------------------------------------------------
    # SECTION 3: FILE UPLOAD & MALFORMED PAYLOAD RESILIENCE
    # -------------------------------------------------------------
    print("\n[SECTION 3] Media Ingestion & Upload Edge Cases")
    
    # 3.1 Upload empty/corrupt file
    empty_file = {"file": ("empty.jpg", b"", "image/jpeg")}
    r_empty = admin_session.post(f"{BASE_URL}/api/upload_image", files=empty_file, timeout=5)
    print(f"  Empty file upload status: {r_empty.status_code}")
    if r_empty.status_code >= 500:
        findings.append({
            "id": "INGEST-01",
            "severity": "P1 - HIGH",
            "category": "Upload Resilience",
            "title": "Server raised HTTP 500 on 0-byte file upload",
            "impact": "Corrupted or 0-byte network upload crashes endpoint instead of returning 400 Bad Request.",
            "reproduction": "POST /api/upload_image with empty file payload",
            "recommendation": "Validate file size > 0 before calling cv2.imdecode."
        })

    # 3.2 Non-existent camera stream start
    r_cam_fake = admin_session.post(f"{BASE_URL}/api/camera/connect", data={"camera_id": "CAM-99", "source": "non_existent.mp4"}, timeout=5)
    print(f"  Fake camera stream connect status: {r_cam_fake.status_code}")
    if r_cam_fake.status_code >= 500:
        findings.append({
            "id": "STREAM-01",
            "severity": "P1 - HIGH",
            "category": "Stream Fault-Tolerance",
            "title": "Server raised HTTP 500 on invalid camera source connect",
            "impact": "Connecting an unreachable RTSP IP camera crashes the camera manager thread.",
            "reproduction": "POST /api/camera/connect with unreachable RTSP URL",
            "recommendation": "Wrap stream connection in try-except with a 3-second network timeout."
        })

    # -------------------------------------------------------------
    # SECTION 4: DATABASE & CONCURRENCY AUDIT
    # -------------------------------------------------------------
    print("\n[SECTION 4] Database Integrity, Concurrency & Table Sizes")
    dbs = [
        ("data/auth_users.sqlite", "users"),
        ("data/vehicles.sqlite", "vehicles"),
        ("data/captured.sqlite", "captured_vehicles"),
        ("data/audit.sqlite", "alert_audit"),
        ("data/trails.sqlite", "vehicle_trails")
    ]
    for db_path, sample_table in dbs:
        if not os.path.exists(db_path):
            findings.append({
                "id": "DB-01",
                "severity": "P1 - HIGH",
                "category": "Database Missing",
                "title": f"Database file missing on disk: {db_path}",
                "impact": f"Operations requiring {sample_table} will fail.",
                "reproduction": f"Inspect disk for {db_path}",
                "recommendation": "Initialize database schema on application startup if file is missing."
            })
            print(f"  ❌ Missing DB: {db_path}")
            continue
            
        try:
            conn = sqlite3.connect(db_path, timeout=3.0)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            check_res = cur.fetchone()[0]
            cur.execute("PRAGMA journal_mode")
            journal = cur.fetchone()[0]
            
            # Count records
            try:
                cur.execute(f"SELECT COUNT(*) FROM {sample_table}")
                cnt = cur.fetchone()[0]
            except Exception:
                cnt = "N/A"
            conn.close()
            
            print(f"  ✅ {db_path} (Table: {sample_table}, Rows: {cnt}, Journal: {journal}, Integrity: {check_res})")
            if journal.lower() != "wal":
                findings.append({
                    "id": "DB-02",
                    "severity": "P2 - MEDIUM (CONCURRENCY)",
                    "category": "Database Locking",
                    "title": f"{db_path} is using '{journal}' mode instead of WAL",
                    "impact": "Under high camera FPS concurrent writes, SQLite will throw 'database is locked' errors during live surveillance.",
                    "reproduction": f"Inspect PRAGMA journal_mode on {db_path}",
                    "recommendation": "Execute PRAGMA journal_mode=WAL on connection initialization."
                })
        except Exception as e:
            findings.append({
                "id": "DB-03",
                "severity": "P1 - HIGH",
                "category": "Database Error",
                "title": f"Cannot connect to database: {db_path}",
                "impact": str(e),
                "reproduction": f"Connect to {db_path}",
                "recommendation": "Verify file permissions and unlock stale locks."
            })
            print(f"  ❌ Error opening {db_path}: {e}")

    # -------------------------------------------------------------
    # SECTION 5: FRONTEND EXPORT ARTIFACT
    # -------------------------------------------------------------
    output_path = "outputs/lead_tester_audit_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)
    print(f"\n📊 Total Audit Findings: {len(findings)}")
    print(f"Report saved to: {output_path}")
    return findings

if __name__ == "__main__":
    run_deep_qa()
