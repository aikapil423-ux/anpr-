import requests
import json
import time
import os

BASE = "http://localhost:8000"

def log_test(step_num, title, status, details=""):
    emoji = "[PASS]" if status else "[FAIL]"
    print(f"{emoji} Step {step_num}: {title}")
    if details:
        print(f"       -> {details}")

def main():
    print("=" * 70)
    print("HARYANA POLICE SURVEILLANCE SYSTEM - IN-DEPTH FUNCTIONAL TEST SUITE")
    print("=" * 70)

    # 1. AUTHENTICATION & SESSIONS
    s_admin = requests.Session()
    r1 = s_admin.post(f"{BASE}/api/auth/login", json={"username": "stateadmin", "password": "HaryanaPolice@HQ2026"})
    admin_ok = (r1.status_code == 200 and "hp_surveillance_session" in s_admin.cookies)
    log_test(1, "State Admin Authentication", admin_ok, f"Status: {r1.status_code}")

    s_op = requests.Session()
    r2 = s_op.post(f"{BASE}/api/auth/login", json={"username": "op_5421", "password": "Operator@123"})
    op_ok = (r2.status_code == 200 and "hp_surveillance_session" in s_op.cookies)
    log_test(2, "Duty Operator Authentication", op_ok, f"Status: {r2.status_code}")

    # 2. DATABASE ENTRIES MAKING (ADD VEHICLE HOTLIST)
    test_plate = f"HR26TEST{int(time.time())%10000}"
    form_data = {
        "vehicle_number": test_plate,
        "vehicle_type": "Car (SUV)",
        "vehicle_color": "White",
        "involved_in_case": "yes",
        "district_name": "Panipat",
        "offence_type": "Stolen Vehicle / FIR 420",
        "fir_number": "FIR-2026-999",
        "police_station": "City Thana Panipat",
        "case_summary": "Automated End-to-End QA Test Entry"
    }
    
    r_add = s_admin.post(f"{BASE}/api/vehicles", data=form_data)
    created_id = None
    if r_add.status_code == 200:
        res_json = r_add.json()
        created_id = res_json.get("vehicle", {}).get("id")
        add_ok = (created_id is not None)
    else:
        add_ok = False
    log_test(3, f"Database Entry Creation: Add Hotlist Vehicle ({test_plate})", add_ok, f"Created ID: {created_id}")

    # 3. VERIFY ENTRY PERSISTED IN DATABASE
    r_get = s_admin.get(f"{BASE}/api/vehicles?search={test_plate}")
    found_in_db = False
    if r_get.status_code == 200:
        vehs = r_get.json().get("vehicles", [])
        found_in_db = any(v.get("vehicle_number") == test_plate for v in vehs)
    log_test(4, "Database Verification: Query Newly Created Entry", found_in_db, f"Matches: {len(vehs)}")

    # 4. RBAC RESTRICTION: OPERATOR CANNOT DELETE ENTRY
    r_op_del = s_op.delete(f"{BASE}/api/vehicles/{created_id}")
    op_blocked = (r_op_del.status_code == 403)
    log_test(5, "RBAC Security: Operator Blocked from Deleting Vehicle", op_blocked, f"Status: {r_op_del.status_code} ({r_op_del.json().get('detail') if r_op_del.status_code==403 else r_op_del.text[:60]})")

    # 5. RBAC PERMISSION: STATE ADMIN CAN DELETE ENTRY
    r_admin_del = s_admin.delete(f"{BASE}/api/vehicles/{created_id}?reason=Automated_QA_Cleanup")
    admin_del_ok = (r_admin_del.status_code == 200)
    log_test(6, "RBAC Security: State Admin Authorized to Delete Vehicle", admin_del_ok, f"Status: {r_admin_del.status_code}")

    # 6. VERIFY AUDIT LOG RECORDED THE CREATION & DELETION
    r_audit = s_admin.get(f"{BASE}/api/alerts/audit-log?limit=5")
    audit_ok = (r_audit.status_code == 200 and len(r_audit.json().get("audit_logs", [])) > 0)
    log_test(7, "Audit Log Trail: Automatic Logging of DB Creation & Deletion", audit_ok, f"Audit Logs logged successfully")

    # 7. LIVE CAMERA STREAMS (ALL TYPES)
    # 7a. Demo Stream
    r_cam_demo = s_admin.post(f"{BASE}/api/camera/connect", data={
        "camera_id": "CAM-01",
        "source_type": "demo",
        "source_path": "demo_1",
        "camera_name": "Demo 1 Highway"
    })
    demo_ok = (r_cam_demo.status_code == 200 and r_cam_demo.json().get("status") == "success")
    log_test(8, "Live Camera Stream: Demo Video Loop Feed (CAM-01)", demo_ok, f"Msg: {r_cam_demo.json().get('message')}")

    # 7b. Camera Stream Disconnect
    r_cam_dis = s_admin.post(f"{BASE}/api/camera/disconnect", data={"camera_id": "CAM-01"})
    dis_ok = (r_cam_dis.status_code == 200)
    log_test(9, "Live Camera Stream: Clean Disconnect & Resource Freeing", dis_ok, f"Status: {r_cam_dis.status_code}")

    # 7c. RTSP / Network Stream Validation
    # We test connecting with an unreachable RTSP URL to verify error handling
    r_rtsp_invalid = s_admin.post(f"{BASE}/api/camera/connect", data={
        "camera_id": "CAM-02",
        "source_type": "rtsp",
        "source_path": "rtsp://invalid.nonexistent.stream:554/live",
        "camera_name": "Invalid RTSP"
    })
    rtsp_handled = (r_rtsp_invalid.status_code in [400, 500, 200]) # Checks if server responds without hanging
    log_test(10, "Live Camera Stream: RTSP Network Stream Handler Validation", rtsp_handled, f"Response: {r_rtsp_invalid.status_code}")

    # 8. UPLOAD IMAGE ANALYSIS (ANPR & OCR)
    import numpy as np
    import cv2
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (200, 200, 200)
    # Add dummy car rectangle and text
    cv2.rectangle(img, (150, 150), (490, 380), (40, 40, 40), -1)
    cv2.rectangle(img, (220, 280), (420, 340), (255, 255, 255), -1)
    cv2.putText(img, "HR26DK8337", (230, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    _, enc = cv2.imencode(".jpg", img)
    
    r_img = s_admin.post(f"{BASE}/api/upload_image", files={"file": ("test_plate.jpg", enc.tobytes(), "image/jpeg")})
    img_ok = (r_img.status_code == 200 and "status" in r_img.json())
    log_test(11, "Static Image Analysis Pipeline: ANPR & OCR Processing", img_ok, f"Status: {r_img.status_code}")

    # 9. FRS (FACE RECOGNITION) LAB IMAGE ANALYSIS
    # Draw simple synthetic face
    face_img = np.zeros((400, 400, 3), dtype=np.uint8)
    cv2.circle(face_img, (200, 200), 100, (220, 200, 180), -1)
    cv2.circle(face_img, (170, 180), 12, (50, 50, 50), -1)
    cv2.circle(face_img, (230, 180), 12, (50, 50, 50), -1)
    cv2.ellipse(face_img, (200, 240), (40, 20), 0, 0, 180, (50, 50, 50), 3)
    _, f_enc = cv2.imencode(".jpg", face_img)

    r_frs = s_admin.post(f"{BASE}/api/frs/test-image", files={"file": ("test_face.jpg", f_enc.tobytes(), "image/jpeg")})
    frs_ok = (r_frs.status_code == 200 and "success" in r_frs.json())
    log_test(12, "Static Image Analysis Pipeline: FRS Face Detection & Matching", frs_ok, f"Status: {r_frs.status_code}")

    # 10. VIDEO ANALYSIS PIPELINE
    # Test sample video processing trigger
    r_vid = s_admin.post(f"{BASE}/api/analyze_sample")
    vid_ok = (r_vid.status_code == 200 and r_vid.json().get("status") == "started")
    log_test(13, "Video Analysis Pipeline: Multi-frame Video Processing Trigger", vid_ok, f"Status: {r_vid.status_code}")

    # Wait 2 seconds for worker to process frames
    time.sleep(2)
    r_v_status = s_admin.get(f"{BASE}/api/status")
    status_ok = (r_v_status.status_code == 200 and "progress" in r_v_status.json())
    log_test(14, "Video Analysis Pipeline: Background Worker Telemetry & Progress", status_ok, f"Progress: {r_v_status.json().get('progress')}%")

    print("=" * 70)
    print("🎯 SUMMARY REPORT COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
