"""
Haryana Police Surveillance & Forensic Engine - QA Automation Test Suite
Comprehensive endpoint, security, concurrency, and validation audit.
"""
import requests
import json
import time
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"
session = requests.Session()

def run_qa_suite():
    print("=" * 70)
    print("🚀 STARTING AUTOMATED QA & INTEGRITY TEST SUITE")
    print("=" * 70)
    
    findings = []
    
    # --- TEST 1: Unauthenticated Endpoint Access ---
    print("\n[TEST 1] Testing Auth Protection & Session Security...")
    # Public vs Protected endpoints
    protected_urls = [
        ("GET", "/api/camera/status"),
        ("GET", "/api/vehicles"),
        ("GET", "/api/captured/vehicles"),
        ("GET", "/api/captured/faces"),
        ("GET", "/api/frs/suspects"),
        ("GET", "/api/alerts/audit"),
        ("GET", "/api/users")
    ]
    
    for method, path in protected_urls:
        try:
            r = requests.get(f"{BASE_URL}{path}", allow_redirects=False, timeout=3)
            # If status is 200 without session cookie, check if it's protected or open
            if r.status_code == 200:
                findings.append({
                    "severity": "P1 - HIGH",
                    "category": "Security / Auth",
                    "title": f"Unauthenticated access permitted on {path}",
                    "detail": f"{method} {path} returned HTTP 200 without any authentication cookie or Bearer token."
                })
                print(f"  ⚠️  Unauthenticated 200 OK on: {path}")
            elif r.status_code in [302, 307, 401, 403]:
                print(f"  ✅ Properly guarded ({r.status_code}): {path}")
            else:
                print(f"  ℹ️ Status {r.status_code}: {path}")
        except Exception as e:
            print(f"  ❌ Error testing {path}: {e}")

    # --- TEST 2: Login Flow & Session Cookie ---
    print("\n[TEST 2] Testing Login Authentication & Token Issuance...")
    login_data = {
        "username": "stateadmin",
        "password": "HaryanaPolice@HQ2026"
    }
    r_login = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True, timeout=5)
    print(f"  Login POST status: {r_login.status_code}")
    if "session_token" in session.cookies:
        print(f"  ✅ Session token received: {session.cookies.get('session_token')[:12]}...")
    else:
        findings.append({
            "severity": "P0 - BLOCKER",
            "category": "Authentication",
            "title": "No session_token cookie set after successful login",
            "detail": "POST /login did not set a session_token cookie on the client session."
        })

    # --- TEST 3: Authenticated API Endpoints Response & Performance ---
    print("\n[TEST 3] Testing Authenticated API Endpoints & Response Integrity...")
    test_endpoints = [
        ("GET", "/api/auth/me", {}),
        ("GET", "/api/camera/status?camera_id=CAM-01", {}),
        ("GET", "/api/camera/status", {}),
        ("GET", "/api/vehicles?limit=5", {}),
        ("GET", "/api/captured/vehicles?limit=5", {}),
        ("GET", "/api/captured/faces?limit=5", {}),
        ("GET", "/api/frs/suspects", {}),
        ("GET", "/api/alerts/active?district=Panipat", {}),
        ("GET", "/api/alerts/audit?limit=5", {}),
        ("GET", "/api/benchmark/models", {}),
        ("GET", "/api/unified/live-feed?limit=5", {}),
        ("GET", "/api/trails?limit=5", {})
    ]

    for method, path, params in test_endpoints:
        t0 = time.time()
        try:
            r = session.get(f"{BASE_URL}{path}", timeout=5)
            elapsed = (time.time() - t0) * 1000
            if r.status_code == 200:
                print(f"  ✅ {path} -> 200 OK ({elapsed:.1f}ms)")
                try:
                    data = r.json()
                    # Validate empty vs structured data
                except Exception:
                    findings.append({
                        "severity": "P2 - MEDIUM",
                        "category": "API Contract",
                        "title": f"Non-JSON response returned by {path}",
                        "detail": f"Status 200 but content is not valid JSON (Content-Type: {r.headers.get('content-type')})."
                    })
            else:
                findings.append({
                    "severity": "P1 - HIGH",
                    "category": "API Failure",
                    "title": f"Endpoint {path} failed with HTTP {r.status_code}",
                    "detail": f"Response: {r.text[:200]}"
                })
                print(f"  ❌ {path} -> HTTP {r.status_code}")
        except Exception as e:
            findings.append({
                "severity": "P1 - HIGH",
                "category": "API Timeout/Crash",
                "title": f"Endpoint {path} crashed or timed out",
                "detail": str(e)
            })
            print(f"  ❌ {path} -> Exception: {e}")

    # --- TEST 4: Fuzzing / SQL Injection / Bad Inputs ---
    print("\n[TEST 4] Testing Malformed Input Handling & Security Injection...")
    malformed_tests = [
        ("GET", "/api/vehicles?search=' OR '1'='1"),
        ("GET", "/api/captured/vehicles?plate=<script>alert(1)</script>"),
        ("GET", "/api/camera/status?camera_id=../../etc/passwd"),
        ("POST", "/api/camera/start", {"camera_id": "INVALID_CAM_9999", "source": "rtsp://invalid:8554/live"})
    ]

    for item in malformed_tests:
        method = item[0]
        path = item[1]
        try:
            if method == "GET":
                r = session.get(f"{BASE_URL}{path}", timeout=4)
            else:
                data = item[2]
                r = session.post(f"{BASE_URL}{path}", data=data, timeout=4)
            
            if r.status_code >= 500:
                findings.append({
                    "severity": "P1 - HIGH",
                    "category": "Unhandle Server Error (500)",
                    "title": f"Internal Server Error (HTTP {r.status_code}) on input fuzzing: {path}",
                    "detail": f"Server raised unhandled exception: {r.text[:300]}"
                })
                print(f"  💥 Server 500 Error on: {path}")
            else:
                print(f"  🛡️ Handled gracefully ({r.status_code}): {path[:45]}...")
        except Exception as e:
            print(f"  ⚠️ Error fuzzing {path}: {e}")

    # --- TEST 5: SQLite Database Integrity Check ---
    print("\n[TEST 5] Checking SQLite Database File Locks & WAL Modes...")
    import sqlite3
    db_files = [
        "data/vehicles.sqlite",
        "data/captured.sqlite",
        "data/auth_users.sqlite",
        "data/audit.sqlite",
        "data/trails.sqlite"
    ]
    for db_path in db_files:
        if not os.path.exists(db_path):
            findings.append({
                "severity": "P2 - MEDIUM",
                "category": "Database Missing",
                "title": f"Database file not found: {db_path}",
                "detail": f"The database {db_path} does not exist on disk."
            })
            continue
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            c = conn.cursor()
            c.execute("PRAGMA integrity_check")
            res = c.fetchone()[0]
            c.execute("PRAGMA journal_mode")
            jmode = c.fetchone()[0]
            conn.close()
            if res == "ok":
                print(f"  ✅ {db_path}: Integrity OK (Journal: {jmode})")
            else:
                findings.append({
                    "severity": "P0 - BLOCKER",
                    "category": "Database Corruption",
                    "title": f"Integrity check failed for {db_path}",
                    "detail": f"PRAGMA integrity_check returned: {res}"
                })
        except Exception as e:
            findings.append({
                "severity": "P1 - HIGH",
                "category": "Database Lock Error",
                "title": f"Database error accessing {db_path}",
                "detail": str(e)
            })

    # Summary
    print("\n" + "=" * 70)
    print(f"🏁 QA AUDIT COMPLETE: {len(findings)} Potential Issues Identified")
    print("=" * 70)
    
    with open("outputs/qa_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)
    print("Results saved to outputs/qa_audit_results.json")

if __name__ == "__main__":
    run_qa_suite()
