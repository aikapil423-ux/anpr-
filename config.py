"""
ANPR Configuration Module
Centralized hyperparameters and settings for detection, quality filtering,
vehicle identity merging, temporal voting, and UI presentation.
"""
import os
import sys
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"

def find_model_path(*relative_candidates: str) -> str:
    """Finds first existing candidate path under models directory, defaulting to primary."""
    for rel in relative_candidates:
        p = MODELS_DIR / rel
        if p.is_dir() and ((p / "model.xml").is_file() or (p / "ppocr").is_dir() or any(p.iterdir())):
            return str(p)
        if p.is_file() and p.stat().st_size > 50:
            return str(p)
    return str(MODELS_DIR / relative_candidates[0])

# Primary model paths with automatic flat/nested directory structure adaptation (Strictly pure YOLO, no OpenVINO)
VEHICLE_MODEL_PATH = find_model_path("yolo/uvh26_yolo11x.pt", "yolo/yolo26n.pt", "yolo26n.pt", "yolo/yolo11n.pt", "yolo11n.pt", "yolo/yolo11s.pt", "yolo11s.pt")
PLATE_MODEL_PATH = find_model_path("yolo/plate_yolo_l.pt", "plate_yolo_l.pt", "yolo/tanish_yolo11s_plate.pt", "tanish_yolo11s_plate.pt", "yolo/yolov8_plate.pt", "yolov8_plate.pt")
AWIROS_WEIGHTS_PATH = find_model_path("awiros_anpr/model.safetensors", "model.safetensors")
AWIROS_DICT_PATH = find_model_path("awiros_anpr/en_dict.txt", "awiros_anpr/PaddleOCR/ppocr/utils/dict/en_dict.txt")
AWIROS_PADDLEOCR_DIR = find_model_path("awiros_anpr/PaddleOCR", "PaddleOCR")

def _detect_awiros_python() -> str:
    env_py = os.getenv("AWIROS_PYTHON")
    if env_py and (os.path.isfile(env_py) or shutil.which(env_py)):
        return env_py

    # 1. Dedicated ocr_env virtual environment (if present)
    candidates = [
        BASE_DIR / "ocr_env" / "venv" / "Scripts" / "python.exe",
        BASE_DIR / "ocr_env" / "venv" / "bin" / "python",
        BASE_DIR / "ocr_env" / "venv" / "bin" / "python3",
        BASE_DIR / "ocr_env" / "bin" / "python",
        BASE_DIR / "ocr_env" / "bin" / "python3",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    # 2. Check if current running Python already has paddle installed (prioritize active interpreter)
    try:
        import paddle  # noqa: F401
        return sys.executable
    except Exception:
        pass

    # 3. Active virtualenv interpreter
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return sys.executable

    # 4. Standard Linux / Docker paths
    system_candidates = [
        Path("/usr/local/bin/python"),
        Path("/usr/local/bin/python3"),
        Path("/usr/bin/python3"),
        Path("/usr/bin/python"),
    ]
    for c in system_candidates:
        if c.is_file():
            return str(c)

    py3 = shutil.which("python3")
    if py3 and os.path.exists(py3):
        return py3

    py = shutil.which("python")
    if py and os.path.exists(py):
        return py

    return sys.executable

LOCAL_OCR_PYTHON = str(BASE_DIR / "ocr_env" / "venv" / "Scripts" / "python.exe") if os.name == "nt" else str(BASE_DIR / "ocr_env" / "venv" / "bin" / "python")
DEFAULT_AWIROS_PYTHON = _detect_awiros_python()

@dataclass
class QualityGateConfig:
    min_confidence: float = 0.35          # Plate proposal floor; OCR format/length checks run before promotion
    min_width: int = 38                   # Minimum crop width in pixels (rejects tiny sub-crops)
    min_height: int = 14                  # Minimum crop height in pixels
    min_laplacian_var: float = 5.0        # Blur rejection threshold (Laplacian variance >= 5.0)
    min_aspect_ratio: float = 1.25        # Minimum W/H aspect ratio (rejects vertical strips and cut plates)
    max_aspect_ratio: float = 5.5         # Maximum W/H aspect ratio
    # Watermark / overlay rejection:
    mask_camera_overlay: bool = True      # Mask out standard camera timestamp / banner zones
    overlay_top_percent: float = 0.05     # If plate touches top border banner
    overlay_bottom_percent: float = 0.05  # If plate touches bottom border banner
    edge_margin_px: int = 4               # Safety crop margin around plate bounding box

@dataclass
class NormalizerConfig:
    min_length: int = 8                   # Minimum length of candidate plate (Indian plates: 8 to 11 characters only)
    max_length: int = 11                  # Maximum length of candidate plate (Indian plates: 8 to 11 characters only)
    indian_state_codes: List[str] = field(default_factory=lambda: [
        "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA",
        "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML",
        "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN",
        "TR", "TS", "UA", "UK", "UP", "WB"
    ])

@dataclass
class IdentityMergerConfig:
    max_track_gap_frames: int = 60        # Max frames before recycled ByteTrack ID is treated as a new vehicle
    max_time_gap_seconds: float = 2.0     # Max seconds between track disappear & appear
    max_spatial_distance_norm: float = 0.25 # Max normalized Euclidean distance (relative to frame diagonal)
    min_velocity_cosine_sim: float = 0.30 # Velocity cosine similarity threshold
    min_appearance_sim: float = 0.60      # Color/appearance histogram similarity threshold
    min_ocr_similarity: float = 0.70      # OCR Levenshtein / character similarity
    require_same_class: bool = True       # Enforce strict vehicle class consistency (never merge car with bike)
    # Weights for composite similarity:
    weight_appearance: float = 0.35
    weight_location: float = 0.25
    weight_direction: float = 0.20
    weight_ocr: float = 0.20
    merge_threshold: float = 0.70         # Composite threshold to merge tracks into same vehicle

@dataclass
class TemporalVotingConfig:
    require_exact_frame_consensus: bool = False
    min_supporting_frames: int = 1        # Select best reading even from 1-2 frames up to 5
    min_ocr_frames_per_vehicle: int = 2   # Minimum frames to evaluate for OCR per vehicle
    max_ocr_frames_per_vehicle: int = 5   # Maximum frames sent to OCR per vehicle (highest detector conf)
    min_promotion_confidence: float = 0.50# Promotion to verified if OCR confidence > 50%
    require_valid_plate_format: bool = True# Must match Indian plate format for main Results
    max_evidence_frames: int = 5          # Up to 5 evidence frames preserved per vehicle

@dataclass
class ANPRConfig:
    quality: QualityGateConfig = field(default_factory=QualityGateConfig)
    normalizer: NormalizerConfig = field(default_factory=NormalizerConfig)
    identity: IdentityMergerConfig = field(default_factory=IdentityMergerConfig)
    voting: TemporalVotingConfig = field(default_factory=TemporalVotingConfig)
    
    # Model parameters: Strictly new models only (no fallbacks)
    vehicle_model_name: str = VEHICLE_MODEL_PATH
    vehicle_classes: List[int] = field(default_factory=lambda: [1, 2, 3, 5, 7]) # bicycle/rickshaw, car, motorcycle, bus, truck in COCO
    person_classes: List[int] = field(default_factory=lambda: [0]) # person in COCO
    enable_people_counting: bool = True
    vehicle_conf: float = 0.22
    
    plate_model_path: str = PLATE_MODEL_PATH
    plate_conf: float = 0.35

    # OCR Recognition Models (PaddleOCR PP-OCRv4 Server, Awiros, Mobile, EasyOCR)
    ocr_model: str = "awiros_anpr"
    awiros_python: str = DEFAULT_AWIROS_PYTHON
    awiros_weights: str = AWIROS_WEIGHTS_PATH
    awiros_dict: str = AWIROS_DICT_PATH
    awiros_paddleocr_dir: str = AWIROS_PADDLEOCR_DIR

    output_dir: str = "outputs"
