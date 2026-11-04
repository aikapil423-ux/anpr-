"""
Test Vehicle DB REST API Endpoints and Hotlist Cross-Matching
"""
import io
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app import app, vehicle_db

def test_vehicle_db_api_crud_and_matching():
    client = TestClient(app)

    # 1. Register a vehicle involved in a police case (YES)
    res1 = client.post(
        "/api/vehicles",
        data={
            "vehicle_number": "KA 05 MN 9999",
            "vehicle_type": "SUV",
            "vehicle_color": "Silver",
            "involved_in_case": "yes",
            "manual_location": "MG Road, Bengaluru",
            "offence_type": "Vehicle Theft",
            "fir_number": "FIR-2026/BLR-782",
            "police_station": "Cubbon Park PS",
            "io_number": "+91-9123456780",
            "case_summary": "Stolen from parking lot overnight."
        }
    )
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert data1["status"] == "success"
    v1 = data1["vehicle"]
    assert v1["vehicle_number"] == "KA05MN9999"
    assert v1["involved_in_case"] == 1
    assert v1["fir_number"] == "FIR-2026/BLR-782"
    v1_id = v1["id"]

    # 2. Register a vehicle reported lost (NO)
    res2 = client.post(
        "/api/vehicles",
        data={
            "vehicle_number": "UP 16 AB 5555",
            "vehicle_type": "Motorcycle",
            "vehicle_color": "Blue",
            "involved_in_case": "no",
            "manual_location": "Noida Sector 18",
            "lost_location": "Mall of India Metro Parking",
            "lost_details": "Keys missing, vehicle unaccounted for since Friday"
        }
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2["status"] == "success"
    v2 = data2["vehicle"]
    assert v2["vehicle_number"] == "UP16AB5555"
    assert v2["involved_in_case"] == 0
    assert v2["lost_location"] == "Mall of India Metro Parking"
    v2_id = v2["id"]

    # 3. GET /api/vehicles list
    list_res = client.get("/api/vehicles")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["status"] == "success"
    assert list_data["total"] >= 2

    # 4. Filter by case
    case_res = client.get("/api/vehicles?filter=case")
    assert case_res.status_code == 200
    case_items = case_res.json()["vehicles"]
    assert any(x["id"] == v1_id for x in case_items)
    assert not any(x["id"] == v2_id for x in case_items)

    # 5. Filter by lost
    lost_res = client.get("/api/vehicles?filter=lost")
    assert lost_res.status_code == 200
    lost_items = lost_res.json()["vehicles"]
    assert any(x["id"] == v2_id for x in lost_items)
    assert not any(x["id"] == v1_id for x in lost_items)

    # 6. Search query
    search_res = client.get("/api/vehicles?search=BLR-782")
    assert search_res.status_code == 200
    search_items = search_res.json()["vehicles"]
    assert any(x["id"] == v1_id for x in search_items)

    # 7. GET /api/vehicles/{id}
    detail_res = client.get(f"/api/vehicles/{v1_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["vehicle"]["fir_number"] == "FIR-2026/BLR-782"

    # 8. GET /api/vehicles/match/{plate}
    match_res = client.get("/api/vehicles/match/KA05MN9999")
    assert match_res.status_code == 200
    assert match_res.json()["matched"] is True
    assert match_res.json()["vehicle"]["id"] == v1_id

    # Matching with spaces / punctuation
    match_res2 = client.get("/api/vehicles/match/UP-16-AB-5555")
    assert match_res2.status_code == 200
    assert match_res2.json()["matched"] is True
    assert match_res2.json()["vehicle"]["id"] == v2_id

    # Non-matched
    nomatch_res = client.get("/api/vehicles/match/DL00XX0000")
    assert nomatch_res.status_code == 200
    assert nomatch_res.json()["matched"] is False

    # 9. Clean up test records
    client.delete(f"/api/vehicles/{v1_id}")
    client.delete(f"/api/vehicles/{v2_id}")

    print("test_vehicle_db_api_crud_and_matching passed successfully!")

if __name__ == "__main__":
    test_vehicle_db_api_crud_and_matching()
