"""
End-to-End ANPR Pipeline Module
Orchestrates vehicle detection, ByteTrack tracking, plate crop quality gating,
multi-pass OCR, vehicle identity track merging, temporal voting,
result promotion, and plate deduplication.
"""
from typing import List, Dict, Tuple, Optional, Any, Callable
import os
import time
import queue
import threading
from dataclasses import dataclass
import cv2
import numpy as np

from config import ANPRConfig
from src.detection.vehicle_detector import VehicleDetector
from src.detection.plate_detector import PlateDetector
from src.detection.triple_riding_detector import TripleRidingDetector
import src.database.violation_db as violation_db
import json
from src.quality.crop_filter import CropQualityFilter
from src.ocr.ocr_engine import OCREngine
from src.ocr.normalizer import IndianPlateNormalizer
from src.ocr.enhancer import PlateEnhancer
from src.identity.vehicle_identity import VehicleRecord, CandidateReading
from src.identity.track_merger import TrackMerger
from src.identity.temporal_voting import TemporalVotingEngine

@dataclass
class AsyncOCRTask:
    cleaned_crop: np.ndarray
    frame: np.ndarray
    tid: int
    vehicle_id: str
    frame_idx: int
    timestamp: float
    plate_conf: float
    blur_score: float
    vbox: List[int]
    pbox: List[int]
    cls_name: str
    frame_shape: Tuple[int, int]

class ANPRPipeline:
    def __init__(
        self,
        config: Optional[ANPRConfig] = None,
        lazy_models: bool = False,
        async_ocr: bool = False,
        max_ocr_queue_size: int = 128
    ):
        self.config = config or ANPRConfig()
        self.async_ocr = async_ocr
        self.max_ocr_queue_size = max_ocr_queue_size
        self._pipeline_lock = threading.Lock()
        
        # Modules
        self.quality_filter = CropQualityFilter(self.config.quality)
        self.normalizer = IndianPlateNormalizer(self.config.normalizer)
        self.track_merger = TrackMerger(self.config.identity)
        self.voting_engine = TemporalVotingEngine(self.config.voting)
        
        # Detectors and OCR (can be initialized lazily or eagerly)
        self.vehicle_detector: Optional[VehicleDetector] = None
        self.plate_detector: Optional[PlateDetector] = None
        self.ocr_engine: Optional[OCREngine] = None
        self.triple_riding_detector: Optional[TripleRidingDetector] = None
        self._violation_cache: Dict[int, Any] = {}

        # Asynchronous OCR Queue & Worker
        self.ocr_queue: queue.Queue = queue.Queue(maxsize=self.max_ocr_queue_size)
        self._ocr_thread: Optional[threading.Thread] = None
        self._ocr_stop_event = threading.Event()
        self.on_verified_sighting: Optional[Callable] = None

        if not lazy_models:
            self.init_models()

        if self.async_ocr:
            self._start_ocr_worker()

        # Statistics
        self.stats = {
            "total_frames_processed": 0,
            "total_tracks_detected": 0,
            "total_crops_evaluated": 0,
            "crops_rejected_quality": 0,
            "valid_ocr_readings": 0,
            "merged_tracks_count": 0
        }

    def init_models(self):
        """Initializes heavy deep learning models."""
        if self.vehicle_detector is None:
            self.vehicle_detector = VehicleDetector(
                model_name=self.config.vehicle_model_name,
                classes=self.config.vehicle_classes,
                conf_thresh=self.config.vehicle_conf
            )
        if self.plate_detector is None:
            self.plate_detector = PlateDetector(
                model_path=self.config.plate_model_path,
                conf_thresh=self.config.plate_conf
            )
        if self.ocr_engine is None:
            self.ocr_engine = OCREngine(
                use_awiros=True,
                awiros_python=self.config.awiros_python,
                awiros_weights=self.config.awiros_weights,
                awiros_dict=self.config.awiros_dict,
                awiros_paddleocr_dir=self.config.awiros_paddleocr_dir,
                ocr_model=getattr(self.config, "ocr_model", "paddleocr_v4_server")
            )
        if self.triple_riding_detector is None:
            try:
                self.triple_riding_detector = TripleRidingDetector()
            except Exception as e:
                print(f"[ANPR Pipeline] TripleRidingDetector notice: {e}")

    def switch_vehicle_model(self, model_key_or_name: str) -> bool:
        """Dynamically hot-swaps active vehicle YOLO model without interrupting pipeline."""
        with self._pipeline_lock:
            if self.vehicle_detector is not None:
                success = self.vehicle_detector.switch_model(model_key_or_name)
                if success:
                    self.config.vehicle_model_name = self.vehicle_detector.model_name
                return success
            else:
                self.config.vehicle_model_name = model_key_or_name
                self.init_models()
                return True

    def switch_plate_model(self, model_key_or_name: str) -> bool:
        """Dynamically hot-swaps active Indian license plate YOLO model without interrupting pipeline."""
        with self._pipeline_lock:
            if self.plate_detector is not None:
                success = self.plate_detector.switch_model(model_key_or_name)
                if success:
                    self.config.plate_model_path = self.plate_detector.model_path
                return success
            else:
                self.config.plate_model_path = model_key_or_name
                self.init_models()
                return True

    def switch_ocr_model(self, model_key_or_name: str) -> bool:
        """Dynamically hot-swaps active OCR model without interrupting pipeline."""
        with self._pipeline_lock:
            self.config.ocr_model = model_key_or_name
            if self.ocr_engine is not None:
                return self.ocr_engine.switch_ocr_model(model_key_or_name)
            return True

    def _start_ocr_worker(self):
        """Starts the dedicated background OCR worker thread."""
        if self._ocr_thread is None or not self._ocr_thread.is_alive():
            self._ocr_stop_event.clear()
            self._ocr_thread = threading.Thread(
                target=self._ocr_worker_loop,
                daemon=True,
                name="ANPR-AsyncOCRWorker"
            )
            self._ocr_thread.start()

    def _ocr_worker_loop(self):
        """Background worker thread continuously pulling and evaluating crops from OCR queue in async batches."""
        while not self._ocr_stop_event.is_set():
            try:
                task: AsyncOCRTask = self.ocr_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Batch collection: pull up to 16 pending tasks from queue without waiting
            tasks_batch = [task]
            while len(tasks_batch) < 16:
                try:
                    next_task = self.ocr_queue.get_nowait()
                    tasks_batch.append(next_task)
                except queue.Empty:
                    break

            try:
                if len(tasks_batch) == 1:
                    self._execute_single_ocr(tasks_batch[0])
                else:
                    self._execute_batch_ocr(tasks_batch)
            except Exception as e:
                print(f"[ANPR Async OCR Worker Error]: {e}")
            finally:
                for _ in tasks_batch:
                    self.ocr_queue.task_done()

    def _execute_single_ocr(self, task: AsyncOCRTask):
        """Executes deep OCR inference on a single queued crop and updates track identity asynchronously."""
        if self.ocr_engine is None:
            return
        raw_text, ocr_conf = self.ocr_engine.read_text(task.cleaned_crop)
        self._apply_ocr_result(task, raw_text, ocr_conf)

    def _execute_batch_ocr(self, tasks: List[AsyncOCRTask]):
        """Executes vectorized deep OCR batch inference across multiple crops."""
        if not tasks or self.ocr_engine is None:
            return
        crops = [t.cleaned_crop for t in tasks]
        if hasattr(self.ocr_engine, "read_batch"):
            results = self.ocr_engine.read_batch(crops)
        else:
            results = [self.ocr_engine.read_text(c) for c in crops]
        for task, (raw_text, ocr_conf) in zip(tasks, results):
            self._apply_ocr_result(task, raw_text, ocr_conf)

    def _apply_ocr_result(self, task: AsyncOCRTask, raw_text: str, ocr_conf: float):
        """Applies OCR recognition result to candidate reading and updates track identity."""
        vx1, vy1, vx2, vy2 = task.vbox
        frame_h, frame_w = task.frame_shape
        v_crop = task.frame[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)].copy()

        # Build annotated scene frame
        annotated_scene = task.frame.copy()
        cls_name = task.cls_name.capitalize()
        veh_color = (255, 140, 0)  # Always Blue
        cv2.rectangle(annotated_scene, (vx1, vy1), (vx2, vy2), veh_color, 1)
        veh_tag = f"{cls_name}"
        (tw, th), _ = cv2.getTextSize(veh_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
        cv2.rectangle(annotated_scene, (vx1, max(0, vy1 - th - 4)), (vx1 + tw + 4, vy1), veh_color, -1)
        cv2.putText(annotated_scene, veh_tag, (vx1 + 2, max(th + 1, vy1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

        if raw_text and ocr_conf >= 0.20:
            cleaned_len = len(self.normalizer.clean_raw_text(raw_text))
            if cleaned_len < self.config.normalizer.min_length or cleaned_len > self.config.normalizer.max_length:
                is_valid_fmt = False
                fmt_type = "invalid_length"
                norm_text = self.normalizer.clean_raw_text(raw_text)
            else:
                is_valid_fmt, fmt_type, norm_text = self.normalizer.validate(raw_text)

            # Strict OCR validation for adaptive detector detections (< 0.30):
            # Must be a valid Indian registration plate format and have confidence >= 40%
            if task.plate_conf < 0.30 and not (is_valid_fmt and ocr_conf >= 0.40):
                return

            if task.pbox is not None:
                px1, py1, px2, py2 = task.pbox
                plate_color = (16, 185, 129) if (is_valid_fmt and ocr_conf > 0.50) else (245, 158, 11)
                cv2.rectangle(annotated_scene, (px1, py1), (px2, py2), plate_color, 1)
                disp_tag = f"{self.normalizer.format_display(norm_text)}"
                (ptw, pth), _ = cv2.getTextSize(disp_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                cv2.rectangle(annotated_scene, (px1, max(0, py1 - pth - 4)), (px1 + ptw + 4, py1), plate_color, -1)
                cv2.putText(annotated_scene, disp_tag, (px1 + 2, max(pth + 1, py1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1)

            ocr_diag = getattr(self.ocr_engine, "last_ocr_diagnostics", {})
            prep_diag = PlateEnhancer.get_preprocessing_diagnostics(task.cleaned_crop, ocr_diag=ocr_diag)
            enh_image = prep_diag.pop("enhanced_image", None)

            candidate_reading = CandidateReading(
                frame_idx=task.frame_idx,
                timestamp=task.timestamp,
                track_id=task.tid,
                raw_text=raw_text,
                normalized_text=norm_text,
                is_valid_format=is_valid_fmt,
                format_type=fmt_type,
                ocr_confidence=ocr_conf,
                detection_confidence=task.plate_conf,
                blur_score=task.blur_score,
                crop_image=task.cleaned_crop,
                vehicle_bbox=task.vbox,
                plate_bbox=task.pbox,
                vehicle_crop=v_crop,
                annotated_frame=annotated_scene,
                enhanced_crop=enh_image,
                preprocessing_meta=prep_diag
            )
            with self._pipeline_lock:
                self.stats["valid_ocr_readings"] += 1
        else:
            # Crop yielded no legible OCR text (< 20%): silently ignore so temporal voting is not polluted
            return

        with self._pipeline_lock:
            vehicle_id = self.track_merger.register_or_update_track(
                track_id=task.tid,
                frame_idx=task.frame_idx,
                timestamp=task.timestamp,
                veh_bbox=task.vbox,
                plate_bbox=task.pbox,
                veh_crop=v_crop,
                candidate_reading=candidate_reading,
                frame_shape=task.frame_shape,
                cls_name=task.cls_name
            )
            v_rec = self.track_merger.vehicles[vehicle_id]
            self.voting_engine.vote_on_vehicle(v_rec)

            # Trigger real-time sighting callback if verified OR if candidate has readable plate text (>= 40% confidence)
            has_readable_candidate = bool(v_rec.final_plate and v_rec.final_plate != 'UNREADABLE' and getattr(v_rec, 'final_confidence', 0.0) >= 0.40)
            if self.on_verified_sighting and (v_rec.is_verified or has_readable_candidate):
                try:
                    self.on_verified_sighting(v_rec, task.frame, task.pbox, task.vbox)
                except Exception as cb_err:
                    print(f'[ANPR Pipeline] Sighting callback error: {cb_err}')


    def drain_ocr_queue(self, timeout: float = 5.0):
        """Waits for pending async OCR tasks to complete (used during finalization or stream stop)."""
        if not self.async_ocr:
            return
        t0 = time.time()
        while getattr(self.ocr_queue, "unfinished_tasks", 0) > 0 and (time.time() - t0) < timeout:
            time.sleep(0.02)

    def process_frame(
        self,
        frame: np.ndarray,
        frame_idx: int,
        timestamp: float,
        sync: bool = False,
        is_photo: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Processes a single video frame.
        Returns active tracked vehicles for visualization/display.
        """
        self.init_models()
        self.stats["total_frames_processed"] += 1
        frame_h, frame_w = frame.shape[:2]

        # 1. Vehicle Detection + ByteTrack
        tracked_vehicles = self.vehicle_detector.track(frame)
        active_track_ids = [v["track_id"] for v in tracked_vehicles]
        self.stats["total_tracks_detected"] = len(self.track_merger.track_to_vehicle)

        # 2. Plate Detection (Execute across full vehicle trajectory: First frame to Last frame)
        vehicles_needing_plate = list(tracked_vehicles)

        # Plate proposals are localized first; crop quality and 8–11-character OCR validation follow.
        effective_plate_conf = 0.20 if is_photo else self.config.plate_conf
        from src.detection.plate_candidates import detect_plate_candidates
        plate_detections = detect_plate_candidates(
            self.plate_detector, frame, vehicles_needing_plate, effective_plate_conf,
            retry_offset=(self.stats["total_frames_processed"] - 1) * 4
        )

        # Match plates to vehicles
        vehicle_to_plate = {}
        for pd in plate_detections:
            matched_vbox = pd.get("vehicle_bbox")
            if matched_vbox:
                for tv in tracked_vehicles:
                    if tv["bbox"] == matched_vbox:
                        existing = vehicle_to_plate.get(tv["track_id"])
                        if existing is None or pd.get("conf", 0) > existing.get("conf", 0):
                            vehicle_to_plate[tv["track_id"]] = pd
                        break

        # Standalone Plate Handling:
        # If plate was detected but no vehicle was detected, do NOT falsely link to another vehicle.
        # Instead, preserve the detection as a standalone scene capture with the plate marked on the full frame.
        matched_plate_bboxes = set(v["bbox"] for v in vehicle_to_plate.values())
        standalone_counter = 1
        req_standalone_conf = 0.35 if is_photo else max(0.50, self.config.plate_conf)
        for pd in plate_detections:
            if pd["bbox"] not in matched_plate_bboxes and pd.get("conf", 0.0) >= req_standalone_conf:
                px1, py1, px2, py2 = pd["bbox"]
                pw, ph = px2 - px1, py2 - py1
                # Enclose surrounding scene context around the plate
                sv_x1 = max(0, px1 - int(pw * 1.5))
                sv_y1 = max(0, py1 - int(ph * 2.5))
                sv_x2 = min(frame_w, px2 + int(pw * 1.5))
                sv_y2 = min(frame_h, py2 + int(ph * 1.2))
                standalone_tid = 900000 + (frame_idx % 1000) * 100 + standalone_counter
                standalone_counter += 1
                standalone_tv = {
                    "track_id": standalone_tid,
                    "bbox": (sv_x1, sv_y1, sv_x2, sv_y2),
                    "cls_id": -1,
                    "cls_name": "vehicle",
                    "conf": pd.get("conf", 0.60),
                    "is_standalone_plate": True
                }
                tracked_vehicles.append(standalone_tv)
                vehicle_to_plate[standalone_tv["track_id"]] = pd

        # 3. Process each tracked vehicle
        active_display_list = []

        for tv in tracked_vehicles:
            tid = tv["track_id"]
            vbox = tv["bbox"]
            vx1, vy1, vx2, vy2 = vbox
            v_crop = frame[vy1:vy2, vx1:vx2]

            candidate_reading = None
            crop_quality_valid = False
            plate_info = vehicle_to_plate.get(tid)
            pbox = plate_info["bbox"] if plate_info else None
            if pbox is None:
                existing_vid = self.track_merger.track_to_vehicle.get(tid)
                if existing_vid is not None:
                    v_rec = self.track_merger.vehicles.get(existing_vid)
                    if v_rec and v_rec.last_plate_bbox is not None:
                        pbox = v_rec.last_plate_bbox

            if plate_info is not None:
                p_conf = plate_info.get("conf", 0.0)
                # Use the same proposal floor as detection; do not reintroduce the old hard-coded 60% cutoff.
                min_plate_floor = effective_plate_conf
                if p_conf < min_plate_floor:
                    plate_info = None
                    pbox = None

            if plate_info is not None and pbox is not None:
                px1, py1, px2, py2 = pbox
                pw, ph = px2 - px1, py2 - py1
                pad_x = int(pw * 0.06)
                pad_y = int(ph * 0.06)
                x1c = max(0, px1 - pad_x)
                y1c = max(0, py1 - pad_y)
                x2c = min(frame_w, px2 + pad_x)
                y2c = min(frame_h, py2 + pad_y)
                p_crop = frame[y1c:y2c, x1c:x2c]
                self.stats["total_crops_evaluated"] += 1

                # Continuous Full-Trajectory OCR:
                # Every analysed frame where plate is localized and passes quality filter
                # is dispatched to OCR throughout the entire vehicle trajectory (first frame to last frame).
                should_run_ocr = True

                if should_run_ocr:
                    # 4. Crop Quality Gate
                    is_valid, reason, blur_score, cleaned_crop = self.quality_filter.validate(
                        crop=p_crop,
                        det_conf=plate_info["conf"],
                        bbox=pbox,
                        frame_shape=(frame_h, frame_w),
                        is_photo=is_photo,
                        min_conf=effective_plate_conf
                    )

                    crop_quality_valid = is_valid
                    if not is_valid:
                        self.stats["crops_rejected_quality"] += 1
                        # Strictly drop invalid / truncated / blurred crops.
                        # Do NOT register a false UNREADABLE reading; wait for vehicle to enter clear zone.
                        candidate_reading = None
                    else:
                        if self.async_ocr and not sync and not is_photo:
                            # 5A. Asynchronous Mode: Non-blocking Queue Dispatch
                            existing_vid = self.track_merger.track_to_vehicle.get(tid, f"veh_{tid}")
                            task = AsyncOCRTask(
                                cleaned_crop=cleaned_crop,
                                frame=frame.copy(),
                                tid=tid,
                                vehicle_id=existing_vid,
                                frame_idx=frame_idx,
                                timestamp=timestamp,
                                plate_conf=plate_info["conf"],
                                blur_score=blur_score,
                                vbox=vbox,
                                pbox=pbox,
                                cls_name=tv.get("cls_name", "vehicle"),
                                frame_shape=(frame_h, frame_w)
                            )
                            # Backpressure safety: if queue full, drop oldest
                            if self.ocr_queue.full():
                                try:
                                    self.ocr_queue.get_nowait()
                                    self.ocr_queue.task_done()
                                except Exception:
                                    pass
                            try:
                                self.ocr_queue.put_nowait(task)
                            except Exception:
                                pass
                        else:
                            # 5B. Synchronous Mode: Direct Execution
                            raw_text, ocr_conf = self.ocr_engine.read_text(cleaned_crop)
                            if raw_text and ocr_conf >= 0.20:
                                cleaned_len = len(self.normalizer.clean_raw_text(raw_text))
                                if cleaned_len < self.config.normalizer.min_length or cleaned_len > self.config.normalizer.max_length:
                                    is_valid_fmt = False
                                    fmt_type = "invalid_length"
                                    norm_text = self.normalizer.clean_raw_text(raw_text)
                                else:
                                    is_valid_fmt, fmt_type, norm_text = self.normalizer.validate(raw_text)

                                # Strict OCR validation for adaptive detector detections (< 0.30):
                                # Must be a valid Indian registration plate format and have confidence >= 40%
                                conf_floor = 0.20 if is_photo else 0.30
                                if plate_info["conf"] < conf_floor and not (is_valid_fmt and ocr_conf >= 0.30):
                                    candidate_reading = None
                                else:
                                    vx1, vy1, vx2, vy2 = vbox
                                    v_crop = frame[max(0, vy1):min(frame_h, vy2), max(0, vx1):min(frame_w, vx2)].copy()

                                annotated_scene = frame.copy()
                                cls_name = tv.get("cls_name", "vehicle").capitalize()
                                veh_color = (255, 140, 0)  # Always Blue
                                cv2.rectangle(annotated_scene, (vx1, vy1), (vx2, vy2), veh_color, 1)
                                veh_tag = f"{cls_name}"
                                (tw, th), _ = cv2.getTextSize(veh_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                                cv2.rectangle(annotated_scene, (vx1, max(0, vy1 - th - 4)), (vx1 + tw + 4, vy1), veh_color, -1)
                                cv2.putText(annotated_scene, veh_tag, (vx1 + 2, max(th + 1, vy1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

                                if pbox is not None:
                                    px1, py1, px2, py2 = pbox
                                    plate_color = (16, 185, 129) if (is_valid_fmt and ocr_conf > 0.50) else (245, 158, 11)
                                    cv2.rectangle(annotated_scene, (px1, py1), (px2, py2), plate_color, 1)
                                    disp_tag = f"{self.normalizer.format_display(norm_text)}"
                                    (ptw, pth), _ = cv2.getTextSize(disp_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                                    cv2.rectangle(annotated_scene, (px1, max(0, py1 - pth - 4)), (px1 + ptw + 4, py1), plate_color, -1)
                                    cv2.putText(annotated_scene, disp_tag, (px1 + 2, max(pth + 1, py1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1)

                                ocr_diag = getattr(self.ocr_engine, "last_ocr_diagnostics", {})
                                prep_diag = PlateEnhancer.get_preprocessing_diagnostics(cleaned_crop, ocr_diag=ocr_diag)
                                enh_image = prep_diag.pop("enhanced_image", None)

                                candidate_reading = CandidateReading(
                                    frame_idx=frame_idx,
                                    timestamp=timestamp,
                                    track_id=tid,
                                    raw_text=raw_text,
                                    normalized_text=norm_text,
                                    is_valid_format=is_valid_fmt,
                                    format_type=fmt_type,
                                    ocr_confidence=ocr_conf,
                                    detection_confidence=plate_info["conf"],
                                    blur_score=blur_score,
                                    crop_image=cleaned_crop,
                                    vehicle_bbox=vbox,
                                    plate_bbox=pbox,
                                    vehicle_crop=v_crop,
                                    annotated_frame=annotated_scene,
                                    enhanced_crop=enh_image,
                                    preprocessing_meta=prep_diag
                                )
                                self.stats["valid_ocr_readings"] += 1
                            else:
                                # Illegible text (< 20%): silently drop candidate reading
                                candidate_reading = None

            # 6. Vehicle-Level Identity Layer
            with self._pipeline_lock:
                vehicle_id = self.track_merger.register_or_update_track(
                    track_id=tid,
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    veh_bbox=vbox,
                    plate_bbox=pbox,
                    veh_crop=v_crop,
                    candidate_reading=candidate_reading,
                    frame_shape=(frame_h, frame_w),
                    cls_name=tv.get("cls_name", "vehicle")
                )

                # Get vehicle record state
                v_rec = self.track_merger.vehicles[vehicle_id]
                # Keep a real detector crop even if OCR returns no usable text.
                # Unreadable captures must not lose the plate evidence.
                if crop_quality_valid and pbox is not None and candidate_reading is None:
                    area = (pbox[2] - pbox[0]) * (pbox[3] - pbox[1])
                    if v_rec.best_crop is None or area > v_rec.max_plate_area:
                        v_rec.best_crop = p_crop.copy()
                        v_rec.best_vehicle_crop = v_crop.copy()
                        v_rec.best_annotated_frame = frame.copy()
                        v_rec.max_plate_area = area
                if candidate_reading is not None and v_rec.readings:
                    self.voting_engine.vote_on_vehicle(v_rec, is_single_image=is_photo)
                    # Check saturation: requires at least 2 readings evaluated, >= 95% conf, valid format
                    if len(v_rec.readings) >= 2 and v_rec.final_confidence >= 0.95 and v_rec.is_valid_format:
                        v_rec.is_saturated = True
                    # Update candidate slots
                    if candidate_reading.ocr_confidence > 0:
                        v_rec.update_candidate_slots(candidate_reading)

                    # Trigger real-time sighting callback directly
                    has_readable_candidate = bool(v_rec.final_plate and v_rec.final_plate != 'UNREADABLE' and getattr(v_rec, 'final_confidence', 0.0) >= 0.40)
                    if self.on_verified_sighting and (v_rec.is_verified or has_readable_candidate):
                        try:
                            self.on_verified_sighting(v_rec, frame, pbox, vbox)
                        except Exception as cb_err:
                            print(f'[ANPR Pipeline] Sighting callback error: {cb_err}')

                cls_str = (tv.get("cls_name") or "").lower()
                is_two_wheeler = cls_str in ["motorcycle", "bicycle", "two_wheeler"] or tv.get("cls_id") in [1, 3]
                if is_two_wheeler and self.triple_riding_detector is not None:
                    if tid not in self._violation_cache or (frame_idx % 8 == 0):
                        curr_p_text = v_rec.final_plate or (candidate_reading.normalized_text if candidate_reading else "")
                        curr_p_conf = getattr(v_rec, "final_confidence", 0.0)
                        v_res = self.triple_riding_detector.evaluate_motorcycle(
                            frame=frame,
                            bike_bbox=vbox,
                            plate_text=curr_p_text,
                            plate_conf=curr_p_conf
                        )
                        self._violation_cache[tid] = v_res
                    else:
                        v_res = self._violation_cache[tid]

                    if v_res.get("is_violation"):
                        v_rec.is_traffic_violation = True
                        v_rec.violation_type = v_res.get("violation_type")
                        v_rec.violation_fine = v_res.get("total_fine", 1000)
                        v_rec.violation_details = json.dumps(v_res)
                        rec_viol = violation_db.record_violation(
                            plate_number=v_rec.final_plate or "UNKNOWN",
                            violation_type=v_res.get("violation_type"),
                            rider_count=v_res.get("rider_count", 1),
                            unhelmeted_count=v_res.get("unhelmeted_count", 1),
                            camera_id="CAM_LIVE_01",
                            camera_location="Sector 14 Checkpost",
                            helmet_fine=v_res.get("helmet_fine", 1000),
                            triple_fine=v_res.get("triple_fine", 0),
                            applied_sections=v_res.get("applied_sections", []),
                            raw_ocr_conf=getattr(v_rec, "final_confidence", 0.0)
                        )
                        if rec_viol:
                            v_rec.violation_id = rec_viol.get("id")

                is_analyzing = bool(pbox is not None and (not v_rec.final_plate))
                active_display_list.append({
                    "vehicle_id": vehicle_id,
                    "track_id": tid,
                    "linked_tracks": list(v_rec.linked_track_ids),
                    "bbox": vbox,
                    "plate_bbox": pbox,
                    "cls_name": tv["cls_name"],
                    "candidate_plate": v_rec.final_plate or (candidate_reading.normalized_text if candidate_reading else ""),
                    "final_plate": v_rec.final_plate,
                    "display_plate": v_rec.display_plate or (self.normalizer.format_display(v_rec.final_plate) if v_rec.final_plate else None),
                    "is_verified": v_rec.is_verified,
                    "is_saturated": v_rec.is_saturated,
                    "alert_state": v_rec.alert_state,
                    "alert_reason": v_rec.alert_reason,
                    "confidence": v_rec.final_confidence,
                    "is_analyzing": is_analyzing,
                    "is_traffic_violation": getattr(v_rec, "is_traffic_violation", False),
                    "violation_type": getattr(v_rec, "violation_type", None),
                    "violation_fine": getattr(v_rec, "violation_fine", 0),
                    "violation_id": getattr(v_rec, "violation_id", None),
                    "violation_details": getattr(v_rec, "violation_details", None)
                })

        # Mark any missing tracks
        with self._pipeline_lock:
            self.track_merger.mark_tracks_lost(active_track_ids, timestamp)

        return active_display_list

    def finalize(self, is_single_image: bool = False) -> Dict[str, Any]:
        """
        Finalizes video processing.
        Runs temporal voting across all vehicle identities, performs promotion
        to Verified Results vs Needs Review, and deduplicates verified results.
        """
        if self.async_ocr:
            self.drain_ocr_queue(timeout=5.0)

        with self._pipeline_lock:
            all_vehicles = list(self.track_merger.vehicles.values())
            
            # Count merged tracks
            merged_count = sum(len(v.linked_track_ids) - 1 for v in all_vehicles if len(v.linked_track_ids) > 1)
            self.stats["merged_tracks_count"] = merged_count

            verified_candidates: List[VehicleRecord] = []
            needs_review_list: List[VehicleRecord] = []
            unreadable_list: List[VehicleRecord] = []
            rejected_count = 0

            # Run temporal voting on each vehicle
            for v in all_vehicles:
                v_updated = self.voting_engine.vote_on_vehicle(v, is_single_image=is_single_image)
                if v_updated.status == "VERIFIED":
                    verified_candidates.append(v_updated)
                elif v_updated.status == "NEEDS_REVIEW":
                    needs_review_list.append(v_updated)
                elif v_updated.status == "UNREADABLE":
                    unreadable_list.append(v_updated)
                else:
                    rejected_count += 1

            # Deduplicate verified results by normalized final plate number
            deduplicated_verified = self.voting_engine.deduplicate_verified_results(verified_candidates)

            return {
                "verified_vehicles": deduplicated_verified,
                "needs_review": needs_review_list,
                "unreadable_vehicles": unreadable_list,
                "stats": {
                    "verified_total": len(deduplicated_verified),
                    "needs_review_total": len(needs_review_list),
                    "unreadable_total": len(unreadable_list),
                    "rejected_count": rejected_count,
                    "total_vehicles_created": len(all_vehicles),
                    "total_bytetrack_ids": len(self.track_merger.track_to_vehicle),
                    "tracks_merged_into_vehicles": merged_count,
                    "frames_processed": self.stats["total_frames_processed"],
                    "crops_evaluated": self.stats["total_crops_evaluated"],
                    "crops_rejected_quality": self.stats["crops_rejected_quality"],
                    "valid_ocr_readings": self.stats["valid_ocr_readings"]
                }
            }

    def reset_state(self):
        """Resets tracking state and statistics while keeping heavy deep learning models in memory."""
        with self._pipeline_lock:
            if self.async_ocr:
                while not self.ocr_queue.empty():
                    try:
                        self.ocr_queue.get_nowait()
                        self.ocr_queue.task_done()
                    except Exception:
                        break
            if hasattr(self.vehicle_detector, "reset"):
                self.vehicle_detector.reset()
            self.track_merger.reset()
            self.stats = {
                "total_frames_processed": 0,
                "total_tracks_detected": 0,
                "total_crops_evaluated": 0,
                "crops_rejected_quality": 0,
                "valid_ocr_readings": 0,
                "merged_tracks_count": 0
            }

    def close(self):
        """Releases underlying workers, threads, and processes."""
        if self.async_ocr and self._ocr_thread and self._ocr_thread.is_alive():
            self._ocr_stop_event.set()
            self._ocr_thread.join(timeout=2.0)
        if self.ocr_engine is not None:
            self.ocr_engine.close()
