import requests
import json

BASE = "http://localhost:8000"

def run_deep_test():
    print("=" * 60)
    print("STEP 1: RBAC Login & Permissions Testing")
    print("=" * 60)
    
    users = [
        ("stateadmin", "HaryanaPolice@HQ2026", "STATE_ADMIN"),
        ("admin_panipat", "PanipatAdmin@2026", "DISTRICT_ADMIN"),
        ("op_5421", "Operator@123", "OPERATOR")
    ]
    
    sessions = {}
    for uname, pwd, exp_role in users:
        s = requests.Session()
        res = s.post(f"{BASE}/api/auth/login", json={"username": uname, "password": pwd})
        if res.status_code == 200:
            role = res.json().get("user", {}).get("role")
            print(f"  [LOGIN OK] {uname} -> Role: {role}")
            sessions[role] = s
        else:
            print(f"  [LOGIN FAIL] {uname} -> {res.status_code}: {res.text}")

    print("\n" + "=" * 60)
    print("STEP 2: Database Entry Creation (Add Vehicle / Suspect)")
    print("=" * 60)
    
    admin_session = sessions.get("STATE_ADMIN")
    op_session = sessions.get("OPERATOR")
    
    # Test Adding a hotlist vehicle as admin
    test_plate = "HR26QA9999"
    vehicle_payload = {
        "plate_number": test_plate,
        "owner_name": "Test QA Suspect",
        "vehicle_type": "Car",
        "color": "Black",
        "category": "STOLEN",
        "notes": "Automated QA Entry Test",
        "district": "Panipat"
    }
    
    # Try adding with Operator session (should check if role allows or denies)
    op_res = op_session.post(f"{BASE}/api/vehicles/add", json=vehicle_payload)
    print(f"  Operator adding vehicle: Status {op_res.status_code} ({op_res.text[:100]})")
    
    # Try adding with Admin session
    admin_res = admin_session.post(f"{BASE}/api/vehicles/add", json=vehicle_payload)
    print(f"  State Admin adding vehicle: Status {admin_res.status_code} ({admin_res.text[:100]})")
    
    # Verify entry is present in DB
    verify_res = admin_session.get(f"{BASE}/api/vehicles/search-full?q={test_plate}")
    print(f"  Verify vehicle in DB: Status {verify_res.status_code}, Found count: {len(verify_res.json().get('results', []))}")

    print("\n" + "=" * 60)
    print("STEP 3: Role-Based Deletion Testing")
    print("=" * 60)
    
    # Operator attempting to delete the vehicle
    op_del = op_session.delete(f"{BASE}/api/vehicles/{test_plate}")
    print(f"  Operator deleting vehicle: Status {op_del.status_code} ({op_del.text[:100]})")
    
    # Admin attempting to delete the vehicle
    admin_del = admin_session.delete(f"{BASE}/api/vehicles/{test_plate}")
    print(f"  State Admin deleting vehicle: Status {admin_del.status_code} ({admin_del.text[:100]})")

    print("\n" + "=" * 60)
    print("STEP 4: Camera Stream Management & Connect Endpoints")
    print("=" * 60)
    
    # Check connect camera endpoint
    # 1. Connect Demo Video feed
    demo_conn = admin_session.post(f"{BASE}/api/camera/connect", json={
        "camera_id": 1,
        "source": "demo_1",
        "mode": "loop",
        "fps_cap": 15
    })
    print(f"  Connect Demo Stream: Status {demo_conn.status_code} ({demo_conn.text[:100]})")
    
    # 2. Check stream status
    status_res = admin_session.get(f"{BASE}/api/camera/status")
    print(f"  Camera Status Check: Status {status_res.status_code}")

    # 3. Disconnect camera
    dis_res = admin_session.post(f"{BASE}/api/camera/disconnect", json={"camera_id": 1})
    print(f"  Disconnect Camera: Status {dis_res.status_code}")

    print("\n" + "=" * 60)
    print("STEP 5: Image & Video Analysis Pipelines")
    print("=" * 60)
    
    # Test 0-byte image upload vs Valid Image upload
    import numpy as np
    import cv2
    dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.putText(dummy_img, "HR26DK8337", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    _, encoded = cv2.imencode(".jpg", dummy_img)
    
    valid_upload = admin_session.post(f"{BASE}/api/upload_image", files={"file": ("test.jpg", encoded.tobytes(), "image/jpeg")})
    print(f"  Valid Image Upload Analysis: Status {valid_upload.status_code} ({valid_upload.text[:120]})")

    # Check video upload endpoint
    print(f"  Video upload routes check: Testing /api/upload_video...")
    
if __name__ == "__main__":
    run_deep_test()
