import os
import shutil
import sqlite3

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEMO_DIR = os.path.join(DATA_DIR, "demo")
DEMO_FRS_DIR = os.path.join(DEMO_DIR, "frs")

os.makedirs(DEMO_DIR, exist_ok=True)
os.makedirs(DEMO_FRS_DIR, exist_ok=True)

files_to_copy = [
    ("alert_audit.sqlite", os.path.join(DEMO_DIR, "alert_audit.sqlite")),
    ("investigation_history.sqlite", os.path.join(DEMO_DIR, "investigation_history.sqlite")),
    ("vehicle_db.sqlite", os.path.join(DEMO_DIR, "vehicle_db.sqlite")),
    ("captured_db.sqlite", os.path.join(DEMO_DIR, "captured_db.sqlite")),
    ("vehicle_trail.sqlite", os.path.join(DEMO_DIR, "vehicle_trail.sqlite")),
    (os.path.join("frs", "face_db.sqlite"), os.path.join(DEMO_FRS_DIR, "face_db.sqlite")),
    (os.path.join("frs", "capturedface_db.sqlite"), os.path.join(DEMO_FRS_DIR, "capturedface_db.sqlite")),
    (os.path.join("frs", "face_trail.sqlite"), os.path.join(DEMO_FRS_DIR, "face_trail.sqlite")),
]

print("--- Step 1: Copying populated database files to data/demo/ ---")
for src_rel, dst in files_to_copy:
    src = os.path.join(DATA_DIR, src_rel)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"Copied {src_rel} -> {dst} ({os.path.getsize(dst)} bytes)")
    else:
        print(f"Warning: {src} does not exist!")

print("\n--- Step 2: Cleaning Production Databases in data/ ---")

def clean_tables(db_path, tables):
    if not os.path.exists(db_path):
        print(f"File not found: {db_path}")
        return
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for t in tables:
        try:
            c.execute(f"DELETE FROM `{t}`")
            print(f"  Cleaned `{t}` in {os.path.basename(db_path)}")
        except Exception as e:
            print(f"  Error cleaning `{t}`: {e}")
    conn.commit()
    c.execute("VACUUM")
    conn.close()

# Clean alert_audit
clean_tables(os.path.join(DATA_DIR, "alert_audit.sqlite"), ["alert_audit_log", "db_change_audit_log"])

# Clean investigation_history
clean_tables(os.path.join(DATA_DIR, "investigation_history.sqlite"), ["investigation_searches"])

# Clean FRS databases
clean_tables(os.path.join(DATA_DIR, "frs", "face_db.sqlite"), ["enrolled_faces", "face_detections_log"])
clean_tables(os.path.join(DATA_DIR, "frs", "capturedface_db.sqlite"), ["captured_faces"])
clean_tables(os.path.join(DATA_DIR, "frs", "face_trail.sqlite"), ["face_sightings"])

# Clean vehicle databases (already 0 rows, but ensure fresh VACUUM)
clean_tables(os.path.join(DATA_DIR, "vehicle_db.sqlite"), ["vehicles"])
clean_tables(os.path.join(DATA_DIR, "captured_db.sqlite"), ["captured_vehicles"])
clean_tables(os.path.join(DATA_DIR, "vehicle_trail.sqlite"), ["vehicle_sightings"])

# Sanitize auth_users.sqlite in production
auth_db_path = os.path.join(DATA_DIR, "auth_users.sqlite")
if os.path.exists(auth_db_path):
    conn = sqlite3.connect(auth_db_path)
    c = conn.cursor()
    
    # Keep only official admin accounts and developer_admin
    official_usernames = [
        "stateadmin",
        "admin_panipat",
        "admin_hisar",
        "admin_ambala_pw",
        "admin_faridabad",
        "developer_admin"
    ]
    placeholders = ",".join("?" for _ in official_usernames)
    c.execute(f"DELETE FROM users WHERE username NOT IN ({placeholders})", official_usernames)
    print(f"Deleted test users. Remaining users:")
    c.execute("SELECT username, role, district, full_name FROM users")
    for row in c.fetchall():
        print(f"  User: {row}")
        
    # Clear old session tokens
    c.execute("DELETE FROM user_sessions")
    print("Cleared stale user sessions.")
    conn.commit()
    c.execute("VACUUM")
    conn.close()

print("\n--- Step 3: Verifying Demo Databases retain all data ---")
demo_checks = [
    (os.path.join(DEMO_DIR, "alert_audit.sqlite"), "alert_audit_log"),
    (os.path.join(DEMO_DIR, "investigation_history.sqlite"), "investigation_searches"),
    (os.path.join(DEMO_FRS_DIR, "face_db.sqlite"), "enrolled_faces"),
    (os.path.join(DEMO_FRS_DIR, "capturedface_db.sqlite"), "captured_faces"),
    (os.path.join(DEMO_FRS_DIR, "face_trail.sqlite"), "face_sightings"),
]

for p, tbl in demo_checks:
    conn = sqlite3.connect(p)
    c = conn.cursor()
    c.execute(f"SELECT COUNT(*) FROM `{tbl}`")
    cnt = c.fetchone()[0]
    print(f"Demo `{tbl}` count: {cnt}")
    conn.close()

print("\n--- Setup and Clean complete! ---")
