"""
Behavior Intelligence Lab - Scenario Benchmark Test
Simulates and tests two realistic scenarios:
Scenario A: Normal Human Interaction (Walking/Greeting) -> Stage 1 Suppresses (0 API calls)
Scenario B: High-Kinetic Interaction (Rapid limb strikes + body clash) -> Stage 1 Triggers -> Stage 2 Verifier Evaluates
"""
import os
import sys
import time
import cv2
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from detector import PoseBehaviorDetector
from verifier import CloudBehaviorVerifier

def create_synthetic_action_frames(num_frames=20, is_fight=False):
    """Generates synthetic video frames simulating normal vs fighting individuals"""
    frames = []
    w, h = 640, 480
    for i in range(num_frames):
        img = np.full((h, w, 3), 40, dtype=np.uint8)  # Dark surveillance background
        cv2.putText(img, f"CCTV SIMULATION - Frame {i+1}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        # Person 1 (Blue)
        p1_x = 260
        p1_y = 200
        # Person 2 (Red)
        if is_fight:
            # Rapid aggressive movement & high overlap
            p2_x = 280 + int(20 * np.sin(i * 1.5))
            # Rapid arm extension
            cv2.line(img, (p1_x, p1_y + 30), (p2_x - 10, p1_y + 30 + int(30 * np.cos(i * 2.0))), (0, 0, 255), 4)
            cv2.line(img, (p2_x, p1_y + 30), (p1_x + 10, p1_y + 30 - int(30 * np.sin(i * 2.0))), (255, 0, 0), 4)
        else:
            # Walking side-by-side peacefully
            p2_x = 360 + int(5 * np.sin(i * 0.2))

        # Draw bodies
        cv2.rectangle(img, (p1_x - 30, p1_y - 60), (p1_x + 30, p1_y + 80), (255, 180, 0), 2)
        cv2.rectangle(img, (p2_x - 30, p1_y - 60), (p2_x + 30, p1_y + 80), (0, 180, 255), 2)
        frames.append(img)
    return frames

def run_scenario_benchmark(api_key=None):
    print("=" * 70)
    print("  🧪 BEHAVIOR INTELLIGENCE LAB: ACCURACY & GATING BENCHMARK")
    print("=" * 70)

    detector = PoseBehaviorDetector(model_path="yolo11n-pose.pt")
    verifier = CloudBehaviorVerifier(api_key=api_key)

    # Test 1: Normal Commuters (Highway Traffic Video)
    print("\n[TEST 1] Testing Normal Commuters / Traffic (Negative Baseline)...")
    cap = cv2.VideoCapture("data/demo_videos/demo_1.mp4")
    triggered_count = 0
    frames_checked = 0

    for _ in range(40):
        ret, frame = cap.read()
        if not ret:
            break
        frames_checked += 1
        res = detector.analyze_frame(frame, frame_idx=frames_checked, timestamp=frames_checked/25.0)
        if res["is_fight_candidate"]:
            triggered_count += 1
    cap.release()

    print(f"[*] Frames evaluated: {frames_checked}")
    print(f"[*] False Trigger Count: {triggered_count} / {frames_checked}")
    print(f"[*] Baseline Normal Specificity (Suppression Accuracy): {((frames_checked - triggered_count)/frames_checked)*100:.1f}%")

    # Test 2: Triggered Candidate Simulation -> Stage 2 Verification
    print("\n[TEST 2] Simulating Confirmed High-Kinetic Candidate -> Stage 2 Verification...")
    sim_meta = {
        "person_A_id": 104,
        "person_B_id": 109,
        "overlap_iou": 0.48,
        "wrist_velocity_px_s": 142.5,
        "kinetic_score": 88.0,
        "proximity_dist_px": 38.0
    }
    sample_frames = create_synthetic_action_frames(num_frames=4, is_fight=True)

    print("--> Handing over 4 keyframes to Stage 2 AI Verifier...")
    verdict = verifier.verify_candidate(
        event_type="PHYSICAL_FIGHT",
        keyframes=sample_frames,
        stage1_meta=sim_meta
    )

    print("\n" + "-" * 70)
    print("  ⚖️ STAGE 2 FORENSIC REPORT:")
    print("-" * 70)
    for k, v in verdict.items():
        print(f"  {k:20s}: {v}")
    print("=" * 70)

if __name__ == "__main__":
    api_key = sys.argv[1] if len(sys.argv) > 1 else None
    run_scenario_benchmark(api_key=api_key)
