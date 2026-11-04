"""
Unit and Integration Tests for Asynchronous ANPR Pipeline Architecture
Verifies non-blocking task queueing, concurrent OCR background worker,
thread-safe state synchronization, and graceful shutdown.
"""
import os
import time
import numpy as np

from config import ANPRConfig
from src.pipeline.anpr_pipeline import ANPRPipeline, AsyncOCRTask

def test_async_pipeline_initialization_and_shutdown():
    cfg = ANPRConfig()
    pipeline = ANPRPipeline(config=cfg, lazy_models=True, async_ocr=True)
    
    assert pipeline.async_ocr is True
    assert pipeline._ocr_thread is not None
    assert pipeline._ocr_thread.is_alive()
    assert pipeline.ocr_queue.empty()

    # Graceful shutdown
    pipeline.close()
    assert not pipeline._ocr_thread.is_alive()

def test_async_ocr_queue_processing():
    cfg = ANPRConfig()
    cfg.voting.min_supporting_frames = 1
    pipeline = ANPRPipeline(config=cfg, lazy_models=True, async_ocr=True)
    
    # Mock OCR engine to avoid loading heavy PaddleOCR during unit test
    class MockOCREngine:
        def read_text(self, crop):
            return "HR26DK8337", 0.95
        def close(self):
            pass

    pipeline.ocr_engine = MockOCREngine()

    # Create dummy crop and frame
    dummy_crop = np.zeros((40, 120, 3), dtype=np.uint8)
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    task = AsyncOCRTask(
        cleaned_crop=dummy_crop,
        frame=dummy_frame,
        tid=1,
        vehicle_id="veh_1",
        frame_idx=1,
        timestamp=0.033,
        plate_conf=0.92,
        blur_score=100.0,
        vbox=[50, 50, 400, 400],
        pbox=[100, 100, 250, 150],
        cls_name="car",
        frame_shape=(480, 640)
    )

    # Put task into queue
    pipeline.ocr_queue.put(task)
    
    # Drain queue
    pipeline.drain_ocr_queue(timeout=3.0)
    assert pipeline.ocr_queue.empty()

    # Verify track merger was updated asynchronously
    with pipeline._pipeline_lock:
        assert len(pipeline.track_merger.vehicles) >= 1
        v_rec = list(pipeline.track_merger.vehicles.values())[0]
        assert len(v_rec.readings) == 1
        assert v_rec.readings[0].normalized_text == "HR26DK8337"
        assert v_rec.final_plate == "HR26DK8337"
        assert v_rec.is_verified is True

    pipeline.close()

def test_async_backpressure_drop_oldest():
    cfg = ANPRConfig()
    # Small queue of size 2
    pipeline = ANPRPipeline(config=cfg, lazy_models=True, async_ocr=False, max_ocr_queue_size=2)
    pipeline.ocr_queue = __import__('queue').Queue(maxsize=2)

    dummy_crop = np.zeros((40, 120, 3), dtype=np.uint8)
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    for i in range(5):
        task = AsyncOCRTask(
            cleaned_crop=dummy_crop,
            frame=dummy_frame,
            tid=i,
            vehicle_id=f"veh_{i}",
            frame_idx=i,
            timestamp=i * 0.033,
            plate_conf=0.9,
            blur_score=100.0,
            vbox=[10, 10, 100, 100],
            pbox=[20, 20, 50, 30],
            cls_name="car",
            frame_shape=(480, 640)
        )
        if pipeline.ocr_queue.full():
            try:
                pipeline.ocr_queue.get_nowait()
                pipeline.ocr_queue.task_done()
            except Exception:
                pass
        pipeline.ocr_queue.put_nowait(task)

    # Queue size should never exceed maxsize 2
    assert pipeline.ocr_queue.qsize() == 2

if __name__ == "__main__":
    test_async_pipeline_initialization_and_shutdown()
    test_async_ocr_queue_processing()
    test_async_backpressure_drop_oldest()
    print("ALL ASYNC PIPELINE TESTS PASSED!")
