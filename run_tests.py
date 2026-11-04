"""
Automated Test Runner using pure standard library
"""
import sys
import os

# Ensure current directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def run_suite():
    passed = 0
    failed = 0
    errors = []

    # Import test modules
    import tests.test_crop_filter as t_crop
    import tests.test_normalizer as t_norm
    import tests.test_track_merger as t_merger
    import tests.test_temporal_voting as t_voting
    import tests.test_end_to_end_simulation as t_sim
    import tests.test_api_and_demo as t_api
    import tests.test_vehicle_db as t_vdb
    import tests.test_vehicle_db_api as t_vdb_api
    import tests.test_captured_db as t_cap
    import tests.test_trail_db as t_trail
    import tests.test_camera_stream as t_cam
    import tests.test_two_line_plate as t_two_line
    import tests.test_async_pipeline as t_async
    import tests.test_upload_auto_delete as t_autodelete

    modules = [t_crop, t_norm, t_merger, t_voting, t_sim, t_api, t_vdb, t_vdb_api, t_cap, t_trail, t_cam, t_two_line, t_async, t_autodelete]

    for mod in modules:
        print(f"\n--- Running {mod.__name__} ---")
        for attr_name in dir(mod):
            if attr_name.startswith("test_"):
                test_fn = getattr(mod, attr_name)
                if callable(test_fn):
                    try:
                        test_fn()
                        print(f"  [PASS] {attr_name}")
                        passed += 1
                    except Exception as e:
                        import traceback
                        tb_str = traceback.format_exc()
                        print(f"  [FAIL] {attr_name}:\n{tb_str}")
                        failed += 1
                        errors.append((attr_name, str(e)))

    print("\n==========================================")
    print(f"RESULTS: {passed} PASSED, {failed} FAILED")
    print("==========================================")
    if failed > 0:
        for name, err in errors:
            print(f"ERROR in {name}: {err}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_suite()
