import requests
import time
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def wait_for_server(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{BASE_URL}/api/auth/me", timeout=2)
            if r.status_code in [200, 401]:
                print("Server is up and responding!")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("Server failed to respond within timeout.")
    return False

def test_login(username, password):
    session = requests.Session()
    res = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"}
    )
    if res.status_code != 200:
        print(f"Login FAILED for {username}: status={res.status_code}, text={res.text}")
        return None
    data = res.json()
    print(f"Login SUCCESS for {username} (Role: {data['user']['role']}, District: {data['user']['district']})")
    return session

def run_tests():
    if not wait_for_server():
        sys.exit(1)

    print("\n==========================================")
    print("TEST 1: DEVELOPER ADMIN (DEMO SANDBOX)")
    print("==========================================")
    dev_sess = test_login("developer_admin", "8221029402")
    if not dev_sess:
        print("FAIL: Could not authenticate as developer_admin")
        sys.exit(1)

    # 1. Check FRS Gallery in Demo
    r_gal = dev_sess.get(f"{BASE_URL}/api/frs/gallery")
    assert r_gal.status_code == 200, f"Gallery failed: {r_gal.text}"
    gal_data = r_gal.json()
    demo_faces = gal_data.get("gallery", [])
    print(f"Developer Admin Gallery Faces: {len(demo_faces)} (Expected: 8)")
    for f in demo_faces:
        print(f"  - [{f.get('category')}] {f.get('person_name')} (ID: {f.get('id')})")
    assert len(demo_faces) == 8, f"Expected 8 demo faces, got {len(demo_faces)}"

    # 2. Check Audit Logs in Demo
    r_audit = dev_sess.get(f"{BASE_URL}/api/alerts/audit-log?limit=50")
    assert r_audit.status_code == 200, f"Audit log failed: {r_audit.text}"
    audit_data = r_audit.json()
    demo_audits = audit_data.get("logs", [])
    print(f"Developer Admin Audit Logs: {len(demo_audits)} records (Expected: >0)")
    assert len(demo_audits) > 0, "Expected demo audit logs to be populated"

    # 3. Check Investigation History in Demo
    r_inv = dev_sess.get(f"{BASE_URL}/api/investigation/history?limit=20")
    assert r_inv.status_code == 200, f"Investigation failed: {r_inv.text}"
    inv_data = r_inv.json()
    demo_searches = inv_data.get("searches", [])
    print(f"Developer Admin Investigation Searches: {len(demo_searches)} records (Expected: >0)")
    assert len(demo_searches) > 0, "Expected demo investigation searches to be populated"

    print("\n==========================================")
    print("TEST 2: STATE ADMIN (LIVE CLEAN PRODUCTION)")
    print("==========================================")
    state_sess = test_login("stateadmin", "HaryanaPolice@HQ2026")
    if not state_sess:
        print("FAIL: Could not authenticate as stateadmin")
        sys.exit(1)

    # 1. Check FRS Gallery in Prod
    r_prod_gal = state_sess.get(f"{BASE_URL}/api/frs/gallery")
    assert r_prod_gal.status_code == 200, f"Prod gallery failed: {r_prod_gal.text}"
    prod_faces = r_prod_gal.json().get("gallery", [])
    print(f"State Admin (Prod) Gallery Faces: {len(prod_faces)} (Expected: 0)")
    assert len(prod_faces) == 0, f"Expected 0 prod faces, got {len(prod_faces)}"

    # 2. Check Audit Logs in Prod
    r_prod_audit = state_sess.get(f"{BASE_URL}/api/alerts/audit-log?limit=50")
    assert r_prod_audit.status_code == 200, f"Prod audit log failed: {r_prod_audit.text}"
    prod_audits = r_prod_audit.json().get("logs", [])
    print(f"State Admin (Prod) Audit Logs: {len(prod_audits)} records (Expected: 0)")
    assert len(prod_audits) == 0, f"Expected 0 prod audit logs, got {len(prod_audits)}"

    # 3. Check Investigation History in Prod
    r_prod_inv = state_sess.get(f"{BASE_URL}/api/investigation/history?limit=20")
    assert r_prod_inv.status_code == 200, f"Prod investigation failed: {r_prod_inv.text}"
    prod_searches = r_prod_inv.json().get("searches", [])
    print(f"State Admin (Prod) Investigation Searches: {len(prod_searches)} records (Expected: 0)")
    assert len(prod_searches) == 0, f"Expected 0 prod investigation searches, got {len(prod_searches)}"

    # 4. Check Vehicle DB in Prod
    r_prod_veh = state_sess.get(f"{BASE_URL}/api/vehicles")
    assert r_prod_veh.status_code == 200, f"Prod vehicle DB failed: {r_prod_veh.text}"
    prod_vehicles = r_prod_veh.json().get("vehicles", [])
    print(f"State Admin (Prod) Vehicles: {len(prod_vehicles)} records (Expected: 0)")
    assert len(prod_vehicles) == 0, f"Expected 0 prod vehicles, got {len(prod_vehicles)}"

    print("\n==========================================")
    print("TEST 3: DISTRICT ADMIN (LIVE CLEAN PRODUCTION)")
    print("==========================================")
    dist_sess = test_login("admin_ambala_pw", "Ambala@2026")
    if not dist_sess:
        print("FAIL: Could not authenticate as admin_ambala_pw")
        sys.exit(1)
    else:
        r_dist_gal = dist_sess.get(f"{BASE_URL}/api/frs/gallery")
        dist_faces = r_dist_gal.json().get("gallery", [])
        print(f"District Admin (Prod) Gallery Faces: {len(dist_faces)} (Expected: 0)")
        assert len(dist_faces) == 0, f"Expected 0 faces in prod district admin, got {len(dist_faces)}"

    print("\n==========================================")
    print("ALL INTEGRITY & ISOLATION TESTS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    run_tests()
