import os
import re
import sqlite3
import datetime
import json
from collections import defaultdict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEMO_DIR = os.path.join(DATA_DIR, "demo")
CROPS_DIR = os.path.join(DATA_DIR, "captured_crops")
TRAIL_DIR = os.path.join(DATA_DIR, "trail_photos")

# Indian plate formatter helper
def format_display_plate(raw):
    raw = re.sub(r'[^A-Z0-9]', '', raw.upper())
    m = re.match(r'^([A-Z]{2})(\d{1,2})([A-Z]{1,3})?(\d{1,4})$', raw)
    if m:
        parts = [m.group(1), m.group(2)]
        if m.group(3): parts.append(m.group(3))
        if m.group(4): parts.append(m.group(4))
        return " ".join(parts)
    return raw

print("--- Step 1: Populating data/demo/captured_db.sqlite from existing crops ---")
cap_db_path = os.path.join(DEMO_DIR, "captured_db.sqlite")
conn_cap = sqlite3.connect(cap_db_path)
c_cap = conn_cap.cursor()

# Clear existing rows in demo captured_vehicles
c_cap.execute("DELETE FROM captured_vehicles")

# Group files in CROPS_DIR
crops_files = os.listdir(CROPS_DIR) if os.path.exists(CROPS_DIR) else []
plates_map = defaultdict(dict)

for f in sorted(crops_files):
    m = re.match(r'(annotated|plate|vehicle|enhanced)_(.+)_(\d+)_([a-f0-9]+)\.jpg', f)
    if m:
        prefix, plate, epoch, h = m.groups()
        # Keep latest or first
        plates_map[plate][prefix] = f
        plates_map[plate]['epoch'] = int(epoch)

hotlist_plates = {"HR08AH3647", "HR26DK8392", "HR06BQ1304", "HR70S9999", "DL10CV1530"}

inserted_count = 0
now_base = datetime.datetime.now().astimezone()

for idx, (plate, data) in enumerate(sorted(plates_map.items(), key=lambda x: x[1].get('epoch', 0), reverse=True)):
    disp = format_display_plate(plate)
    epoch = data.get('epoch', int(now_base.timestamp()) - (idx * 180))
    time_iso = datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")

    # Photo paths relative to /data
    plate_path = f"/data/captured_crops/{data['plate']}" if 'plate' in data else None
    veh_path = f"/data/captured_crops/{data['vehicle']}" if 'vehicle' in data else None
    ann_path = f"/data/captured_crops/{data['annotated']}" if 'annotated' in data else None

    is_hit = 1 if plate in hotlist_plates else 0
    hit_info = f"⚠️ STOLEN VEHICLE / WANTED FIR #{100+idx}/2026" if is_hit else None

    locations = [
        "GT Road Panipat Toll Checkpoint (Lane 02)",
        "Sector 18 City Junction (North Camera)",
        "East Bypass Checkpost (Surveillance Hub)",
        "Highway Naka Barrier #4 (Inbound Lane)"
    ]
    loc = locations[idx % len(locations)]
    district = "Panipat" if idx % 2 == 0 else "Karnal"

    c_cap.execute("""
        INSERT INTO captured_vehicles (
            plate_number, display_plate, confidence,
            plate_pic_path, vehicle_pic_path, annotated_pic_path,
            captured_at, location, source_type,
            is_hotlist_hit, hotlist_info, created_epoch,
            blur_score, aspect_ratio, det_confidence, ocr_confidence,
            format_type, quality_gate_passed, quality_reason,
            track_id, linked_tracks, vehicle_id,
            district, operator_id, operator_username, station
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        plate, disp, 92.5 + (idx % 7),
        plate_path, veh_path, ann_path,
        time_iso, loc, f"CAM-{(idx%4)+1:02d}",
        is_hit, hit_info, float(epoch),
        110.0 + (idx % 40), 3.2, 95.0 + (idx % 5), 93.0 + (idx % 6),
        "STANDARD_IND", 1, "Passed All Quality Gates",
        idx + 1, str(idx + 1), idx + 1,
        district, 1, "developer_admin", "PHQ"
    ))
    inserted_count += 1

conn_cap.commit()
print(f"Populated {inserted_count} captured vehicles into data/demo/captured_db.sqlite")
conn_cap.close()

print("\n--- Step 2: Populating data/demo/vehicle_db.sqlite (Demo Hotlist Registry) ---")
veh_db_path = os.path.join(DEMO_DIR, "vehicle_db.sqlite")
conn_veh = sqlite3.connect(veh_db_path)
c_veh = conn_veh.cursor()
c_veh.execute("DELETE FROM vehicles")

demo_hotlist_vehicles = [
    {
        "vehicle_number": "HR08AH3647",
        "display_number": "HR 08 AH 3647",
        "vehicle_type": "White Sedan",
        "vehicle_color": "White",
        "involved_in_case": 1,
        "offence_type": "Vehicle Theft",
        "fir_number": "FIR-442/2026",
        "police_station": "City Police Station, Panipat",
        "io_number": "SI-7749/PPT",
        "case_summary": "Stolen from Sector 11 Market parking on 12-Oct-2026. High alert naka spotted.",
        "district_name": "Panipat",
        "owner_name": "Vikas Choudhary",
        "owner_mobile": "9812044551"
    },
    {
        "vehicle_number": "HR26DK8392",
        "display_number": "HR 26 DK 8392",
        "vehicle_type": "SUV",
        "vehicle_color": "Silver",
        "involved_in_case": 1,
        "offence_type": "Hit & Run Forensics",
        "fir_number": "FIR-118/2026",
        "police_station": "Sadar Thana, Gurugram",
        "io_number": "ASI-1092/GGN",
        "case_summary": "Involved in pedestrian collision on Sohna Road. Inter-district alert active.",
        "district_name": "Gurugram",
        "owner_name": "Rajesh Verma",
        "owner_mobile": "9876543210"
    },
    {
        "vehicle_number": "HR06BQ1304",
        "display_number": "HR 06 BQ 1304",
        "vehicle_type": "Hatchback",
        "vehicle_color": "Grey",
        "involved_in_case": 1,
        "offence_type": "Commercial Robbery Escort",
        "fir_number": "FIR-89/2026",
        "police_station": "Model Town PS, Panipat",
        "io_number": "Insp-331/PPT",
        "case_summary": "Used as getaway escort in warehouse theft incident.",
        "district_name": "Panipat",
        "owner_name": "Suresh Malik",
        "owner_mobile": "9416098877"
    },
    {
        "vehicle_number": "HR70S9999",
        "display_number": "HR 70 S 9999",
        "vehicle_type": "Luxury Sedan",
        "vehicle_color": "Black",
        "involved_in_case": 1,
        "offence_type": "Smuggling & Contraband Transit",
        "fir_number": "FIR-604/2026",
        "police_station": "GT Road Checkpost PS, Karnal",
        "io_number": "DSP-KRL-01",
        "case_summary": "Flagged by State Intelligence for illegal liquor inter-state conduit.",
        "district_name": "Karnal",
        "owner_name": "Deepak Batra",
        "owner_mobile": "9896011223"
    }
]

for v in demo_hotlist_vehicles:
    now_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c_veh.execute("""
        INSERT INTO vehicles (
            vehicle_number, display_number, vehicle_type, vehicle_color,
            involved_in_case, offence_type, fir_number, police_station,
            io_number, case_summary, created_at, status, district_name,
            created_by_officer, owner_name, owner_mobile
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, 'State Police HQ Admin', ?, ?)
    """, (
        v["vehicle_number"], v["display_number"], v["vehicle_type"], v["vehicle_color"],
        v["involved_in_case"], v["offence_type"], v["fir_number"], v["police_station"],
        v["io_number"], v["case_summary"], now_dt, v["district_name"],
        v["owner_name"], v["owner_mobile"]
    ))

conn_veh.commit()
print(f"Populated {len(demo_hotlist_vehicles)} hotlist vehicles into data/demo/vehicle_db.sqlite")
conn_veh.close()

print("\n--- Step 3: Populating data/demo/vehicle_trail.sqlite (Master Corridor Trail) ---")
trail_db_path = os.path.join(DEMO_DIR, "vehicle_trail.sqlite")
conn_trail = sqlite3.connect(trail_db_path)
c_trail = conn_trail.cursor()
c_trail.execute("DELETE FROM vehicle_sightings")

trail_files = os.listdir(TRAIL_DIR) if os.path.exists(TRAIL_DIR) else []
plate_trail_files = [f for f in trail_files if f.startswith("plate_HR08AH3647_")]
trail_count = 0

for idx, pf in enumerate(sorted(plate_trail_files)):
    vf = pf.replace("plate_", "vehicle_")
    m = re.search(r'_(\d+)_', pf)
    epoch = int(m.group(1)) if m else int(now_base.timestamp()) - (idx * 600)
    time_iso = datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")

    t_locs = [
        ("Toll Plaza Gate 01 (Inbound)", "Panipat"),
        ("GT Road Sector 18 Junction", "Panipat"),
        ("Model Town Chowk Surveillance", "Panipat"),
        ("Karnal Highway Checkpost #2", "Karnal"),
        ("Madhuban Border Naka Post", "Karnal"),
        ("Ambala Expressway Toll North", "Ambala"),
        ("State Capital Toll Linkway", "Panchkula"),
        ("Border Barrier Checkpoint", "Chandigarh Border")
    ]
    t_loc, t_dist = t_locs[idx % len(t_locs)]

    c_trail.execute("""
        INSERT INTO vehicle_sightings (
            vehicle_id, registration_number, display_number,
            camera_id, location, captured_at, captured_epoch,
            confidence, plate_photo_path, vehicle_photo_path,
            passage_id, created_at, district, operator_username, station
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        1, "HR08AH3647", "HR 08 AH 3647",
        f"CAM-TOLL-0{idx+1}", t_loc, time_iso, float(epoch),
        96.5 + (idx % 3),
        f"/data/trail_photos/{pf}",
        f"/data/trail_photos/{vf}" if vf in trail_files else None,
        f"PASS-20261019-00{idx+1}", time_iso, t_dist, "developer_admin", "PHQ"
    ))
    trail_count += 1

conn_trail.commit()
print(f"Populated {trail_count} corridor sightings into data/demo/vehicle_trail.sqlite")
conn_trail.close()

print("\n--- Summary Verification ---")
for d, tbl in [
    (cap_db_path, "captured_vehicles"),
    (veh_db_path, "vehicles"),
    (trail_db_path, "vehicle_sightings"),
]:
    conn = sqlite3.connect(d)
    cnt = conn.execute(f"SELECT COUNT(*) FROM `{tbl}`").fetchone()[0]
    print(f"  {os.path.basename(d)} `{tbl}`: {cnt} rows")
    conn.close()

print("\nAll demo vehicle databases successfully populated!")
