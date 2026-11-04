"""Fixed upload sampling cadence, independent of detections and OCR state."""
import math


class VideoFrameSampler:
    def __init__(self, source_fps, requested_fps=5):
        self.source_fps = float(source_fps)
        if not math.isfinite(self.source_fps) or self.source_fps <= 0:
            self.source_fps = 25.0
        try:
            requested = int(requested_fps)
        except (TypeError, ValueError):
            requested = 5
        if requested not in (0, 5, 10, 20):
            requested = 5
        self.output_fps = min(self.source_fps, requested) if requested else self.source_fps

    def _slot(self, zero_based_index):
        return math.floor(zero_based_index * self.output_fps / self.source_fps + 1e-9)

    def includes(self, frame_index):
        """Accept one-based frame indices at the selected rate."""
        return frame_index == 1 or self._slot(frame_index - 1) > self._slot(frame_index - 2)

    def count(self, total_frames):
        return self._slot(total_frames - 1) + 1 if total_frames > 0 else 0
