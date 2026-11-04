"""
Behavior Intelligence Lab - Integrated Pipeline Test Harness
Tests the End-to-End Two-Tier Architecture on video files without touching the main project.
- Native Stream Quality & Resolution Preserved
- Stage 1 Local Pose Continuous Tracking (YOLO-Pose)
- Stage 2 Cloud Verifier on Triggered Events
"""
import os
import sys
import time
import argparse
from collections import deque
import cv2
import numpy as np

# Ensure tests/behavior_lab is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from detector import PoseBehaviorDetector
from verifier import CloudBehaviorVerifier

def run_pipeline_test(
    video_source: str,
    model_name: str = "yolo11m-pose.pt",
    api_key: str = None,
    max_frames: int = 300,
    stride: int = 1,
    save_output: bool = True
):
    print("=" * 70)
    print("  🚨 STATE POLICE HQ - BEHAVIOR INTELLIGENCE TEST LAB (2-TIER PIPELINE)")
    print("=" * 70)
    print(f"[*] Input Video Source: {video_source}")
    print(f"[*] Stage 1 Local Pose Model: {model_name}")
    print(f"[*] Analysis Stride: Every {stride} frame(s)")

    output_dir = os.path.join(CURRENT_DIR, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Open Video Capture (Native Resolution)
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print(f"[Error] Could not open video: {video_source}")
        return

    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"[*] Native Stream Specs: {orig_w}x{orig_h} @ {orig_fps:.1f} FPS (Total frames: {total_frames})")

    # 2. Initialize Stage 1 and Stage 2
    stage1 = PoseBehaviorDetector(model_path=model_name, conf_thresh=0.35)
    stage2 = CloudBehaviorVerifier(api_key=api_key)

    # In-memory Rolling Ring Buffer (stores last 60 raw frames for retrospective incident replay)
    ring_buffer = deque(maxlen=60)

    # Video Writer for evidentiary annotated output
    writer = None
    out_video_path = os.path.join(output_dir, "test_annotated_run.mp4")
    if save_output:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_video_path, fourcc, orig_fps / stride, (orig_w, orig_h))

    frame_idx = 0
    processed_count = 0
    t_start = time.time()
    events_triggered = 0

    print("\n[+] Starting real-time streaming & analysis loop...")
    print("-" * 70)

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or (max_frames > 0 and frame_idx >= max_frames):
                break

            frame_idx += 1
            timestamp = frame_idx / orig_fps

            # Keep 100% native resolution frame in rolling memory buffer
            ring_buffer.append((frame.copy(), timestamp))

            # Apply user cadence / stride
            if frame_idx % stride != 0:
                continue

            processed_count += 1
            loop_t0 = time.time()

            # --- STAGE 1: Real-Time Local Pose & Kinetic Analysis ---
            analysis_result = stage1.analyze_frame(frame, frame_idx=frame_idx, timestamp=timestamp)
            annotated_frame = analysis_result["annotated_frame"]

            # Save annotated frame
            if writer:
                writer.write(annotated_frame)

            # Check if Stage 1 triggered a Candidate Event
            if analysis_result["is_fight_candidate"]:
                events_triggered += 1
                meta = analysis_result["candidate_metadata"]
                print(f"\n[!] 🚨 STAGE 1 TRIGGER HIT at Frame #{frame_idx} (Time: {timestamp:.1f}s)!")
                print(f"    - Overlap IoU: {meta.get('overlap_iou')}")
                print(f"    - Wrist Velocity: {meta.get('wrist_velocity_px_s')} px/s")
                print(f"    - Kinetic Score: {meta.get('kinetic_score')}")

                # Extract 4 Chronological Keyframes from Ring Buffer (t-2s, t-1.3s, t-0.6s, t=0s)
                buf_len = len(ring_buffer)
                sample_indices = [
                    0,
                    buf_len // 3,
                    (buf_len * 2) // 3,
                    buf_len - 1
                ]
                extracted_keyframes = [ring_buffer[i][0] for i in sample_indices if i < buf_len]

                # Save keyframe collage for verification inspection
                collage_path = os.path.join(output_dir, f"trigger_event_{events_triggered}_keyframes.jpg")
                if len(extracted_keyframes) == 4:
                    top_row = np.hstack([cv2.resize(extracted_keyframes[0], (320, 240)), cv2.resize(extracted_keyframes[1], (320, 240))])
                    bot_row = np.hstack([cv2.resize(extracted_keyframes[2], (320, 240)), cv2.resize(extracted_keyframes[3], (320, 240))])
                    collage = np.vstack([top_row, bot_row])
                    cv2.imwrite(collage_path, collage)
                    print(f"    - Evidentiary Keyframe Collage Saved: {collage_path}")

                # --- STAGE 2: Send Candidate to Cloud AI Verifier ---
                print("    - Dispatching to Stage 2 Cloud AI Verifier...")
                verdict = stage2.verify_candidate(
                    event_type="PHYSICAL_FIGHT",
                    keyframes=extracted_keyframes,
                    stage1_meta=meta
                )

                print("    - ⚖️ STAGE 2 VERDICT RECEIVED:")
                print(f"      * Is Confirmed Violation: {verdict.get('is_violation')}")
                print(f"      * Confidence: {verdict.get('confidence') * 100:.1f}%")
                print(f"      * Threat Level: {verdict.get('threat_level')}")
                print(f"      * Forensic Reason: {verdict.get('reason')}")
                print(f"      * Dispatch Action: {verdict.get('action_recommended')}")
                print(f"      * Latency: {verdict.get('latency_seconds')} seconds via {verdict.get('provider')}")

                # Reset trigger so we don't spam on the next immediate frame
                stage1.reset_trigger()

            # Progress ticker every 30 frames
            if frame_idx % 30 == 0:
                elapsed_now = time.time() - t_start
                curr_fps = processed_count / max(elapsed_now, 0.001)
                sys.stdout.write(f"\r--> Stream Running: Frame {frame_idx}/{total_frames} | Effective AI FPS: {curr_fps:.1f} | People Tracked: {analysis_result['detected_count']}   ")
                sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n[!] User aborted stream test.")
    finally:
        cap.release()
        if writer:
            writer.release()

    total_time = time.time() - t_start
    avg_fps = processed_count / max(total_time, 0.001)
    print("\n" + "=" * 70)
    print("  🏁 TEST HARNESS EXECUTION SUMMARY")
    print("=" * 70)
    print(f"[*] Frames Processed: {processed_count} / {frame_idx}")
    print(f"[*] Total Wall Clock Time: {total_time:.2f} seconds")
    print(f"[*] Average Ingestion & Analysis Throughput: {avg_fps:.1f} FPS")
    print(f"[*] Total Incidents Screened & Dispatched to AI Judge: {events_triggered}")
    if save_output:
        print(f"[*] Annotated Evidentiary Video Saved at: {out_video_path}")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Behavior Lab Runner")
    parser.add_argument("--video", type=str, default="data/demo_videos/demo_1.mp4", help="Path to input video")
    parser.add_argument("--model", type=str, default="yolo11m-pose.pt", help="Pose model path")
    parser.add_argument("--api-key", type=str, default=None, help="Gemini API Key (optional)")
    parser.add_argument("--max-frames", type=int, default=150, help="Max frames to process")
    parser.add_argument("--stride", type=int, default=2, help="Frame analysis stride (1=every frame, 2=alternate)")
    args = parser.parse_args()

    run_pipeline_test(
        video_source=args.video,
        model_name=args.model,
        api_key=args.api_key,
        max_frames=args.max_frames,
        stride=args.stride
    )
