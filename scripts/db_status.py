import os
import sqlite3

def inspect_db(path):
    if not os.path.exists(path):
        print(f"NOT FOUND: {path}")
        return
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(f"\n=== {path} ({os.path.getsize(path)} bytes) ===")
    for t in tables:
        if t.startswith("sqlite_"): continue
        try:
            c.execute(f"SELECT COUNT(*) FROM `{t}`")
            cnt = c.fetchone()[0]
            print(f"  Table `{t}`: {cnt} rows")
        except Exception as e:
            print(f"  Table `{t}`: error ({e})")
    conn.close()

dbs = [
    # Production Live DBs
    "data/vehicle_db.sqlite",
    "data/captured_db.sqlite",
    "data/vehicle_trail.sqlite",
    "data/alert_audit.sqlite",
    "data/investigation_history.sqlite",
    "data/auth_users.sqlite",
    # Demo Sandbox DBs
    "data/demo/vehicle_db.sqlite",
    "data/demo/captured_db.sqlite",
    "data/demo/vehicle_trail.sqlite",
    "data/demo/alert_audit.sqlite",
    "data/demo/investigation_history.sqlite",
]

for d in dbs:
    inspect_db(d)
