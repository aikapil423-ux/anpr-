"""
Unit tests for Vehicle DB (Hotlist / Case Registry)
"""
import os
import sys
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.vehicle_db import VehicleDB

def test_vehicle_db_operations():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_vehicles.sqlite")
        vdb = VehicleDB(db_path=db_path)

        # 1. Add Vehicle Involved in Case (YES)
        v1_id = vdb.add_vehicle(
            vehicle_number="MH 12 DE 1433",
            vehicle_type="Car",
            vehicle_color="White",
            involved_in_case=True,
            manual_location="Pune City",
            offence_type="Hit & Run",
            fir_number="FIR-2026/099",
            police_station="Kothrud PS",
            io_number="+91-9876543210",
            case_summary="Suspect vehicle fled from scene"
        )
        assert v1_id > 0
        v1 = vdb.get_by_id(v1_id)
        assert v1["vehicle_number"] == "MH12DE1433"
        assert v1["display_number"] == "MH 12 DE 1433"
        assert v1["involved_in_case"] == 1
        assert v1["fir_number"] == "FIR-2026/099"
        assert v1["created_at"] != ""
        assert v1["lost_location"] is None

        # 2. Add Vehicle Not Involved in Case (NO -> Lost Vehicle)
        v2_id = vdb.add_vehicle(
            vehicle_number="DL01AB1234",
            vehicle_type="Motorcycle",
            vehicle_color="Black",
            involved_in_case=False,
            manual_location="Connaught Place, Delhi",
            lost_location="Metro Station Gate 2 Parking",
            lost_details="Parked at 9 AM, missing by 6 PM"
        )
        assert v2_id > 0
        v2 = vdb.get_by_id(v2_id)
        assert v2["involved_in_case"] == 0
        assert v2["lost_location"] == "Metro Station Gate 2 Parking"
        assert v2["fir_number"] is None

        # 3. Match Plate (Direct and with spacing variation)
        match1 = vdb.match_plate("MH12DE1433")
        assert match1 is not None
        assert match1["id"] == v1_id
        assert match1["fir_number"] == "FIR-2026/099"

        match2 = vdb.match_plate("DL-01-AB-1234")
        assert match2 is not None
        assert match2["id"] == v2_id
        assert match2["lost_location"] == "Metro Station Gate 2 Parking"

        # 4. Search and Filters
        all_list = vdb.get_all()
        assert len(all_list) == 2

        case_only = vdb.get_all(filter_type="case")
        assert len(case_only) == 1
        assert case_only[0]["vehicle_number"] == "MH12DE1433"

        lost_only = vdb.get_all(filter_type="lost")
        assert len(lost_only) == 1
        assert lost_only[0]["vehicle_number"] == "DL01AB1234"

        search_fir = vdb.get_all(search_query="FIR-2026")
        assert len(search_fir) == 1

        # 5. Delete
        assert vdb.delete(v1_id) is True
        assert vdb.get_by_id(v1_id) is None
        assert len(vdb.get_all()) == 1

        print("test_vehicle_db_operations passed successfully!")

if __name__ == "__main__":
    test_vehicle_db_operations()
