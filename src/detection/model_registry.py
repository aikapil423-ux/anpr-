"""
Model Registry & Dynamic Model Switcher Module
Manages available YOLO vehicle and license plate detection models.
Provides model catalogs, dynamic loading, path resolution, and weight verification.
"""
from typing import Dict, List, Any, Optional
import os
import json
import threading
from pathlib import Path
from ultralytics import YOLO
BASE_DIR = Path(__file__).resolve().parent.parent.parent
YOLO_MODELS_DIR = BASE_DIR / 'models' / 'yolo'
ACTIVE_MODELS_FILE = BASE_DIR / 'data' / 'active_models.json'
CUSTOM_NAMES_FILE = BASE_DIR / 'data' / 'custom_model_names.json'
VEHICLE_MODELS: Dict[str, Dict[str, Any]] = {
    'uvh26_yolo11x': {
        'id': 'uvh26_yolo11x',
        'name': 'IISc-AIM UVH-26 (YOLOv11x 🇮🇳 326MB)',
        'family': 'IISc-AIM Indian Traffic Benchmark',
        'filename': 'uvh26_yolo11x.pt',
        'size_mb': 326.6,
        'description': 'State-of-the-art 14-class Indian vehicle benchmark model (Hatchback, Auto, Tempo, Bus, etc.) from IISc Bangalore.',
        'recommended': True,
        'supports_person': True
    }
}
PLATE_MODELS: Dict[str, Dict[str, Any]] = {
    'plate_yolo_l': {
        'id': 'plate_yolo_l',
        'name': 'YOLO11l Plate (CCTV Large 🇮🇳 48.8MB)',
        'family': 'CCTV & Traffic Fine-Tuned',
        'filename': 'plate_yolo_l.pt',
        'size_mb': 48.8,
        'description': '25.3M parameter YOLO11l Large plate detector fine-tuned for Indian traffic & CCTV footage.',
        'recommended': True
    }
}
OCR_MODELS: Dict[str, Dict[str, Any]] = {
    'awiros_anpr': {
        'id': 'awiros_anpr',
        'name': 'Awiros ANPR-OCR (SVTR PP-OCRv5 🇮🇳 142MB)',
        'family': 'Awiros ANPR Series',
        'filename': 'awiros_anpr/model.safetensors',
        'size_mb': 142.5,
        'description': '37.3M parameter PP-OCRv5 SVTR_HGNet neural encoder fine-tuned exclusively for Indian HSRP license plates.',
        'recommended': True,
        'type': 'awiros'
    }
}
FACTORY_DEFAULTS: Dict[str, Dict[str, str]] = {
    'live': {
        'vehicle': 'uvh26_yolo11x',
        'plate': 'plate_yolo_l',
        'person': 'uvh26_yolo11x',
        'ocr': 'awiros_anpr'
    },
    'upload': {
        'vehicle': 'uvh26_yolo11x',
        'plate': 'plate_yolo_l',
        'person': 'uvh26_yolo11x',
        'ocr': 'awiros_anpr'
    }
}

class ModelRegistry:

    def __init__(self):
        self._lock = threading.RLock()
        self.live_models: Dict[str, str] = dict(FACTORY_DEFAULTS['live'])
        self.upload_models: Dict[str, str] = dict(FACTORY_DEFAULTS['upload'])
        self._cached_yolo_instances: Dict[str, YOLO] = {}
        self._person_support_cache: Dict[str, bool] = {}
        YOLO_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_state()

    @property
    def active_vehicle_id(self) -> str:
        return self.live_models.get('vehicle', FACTORY_DEFAULTS['live']['vehicle'])

    @active_vehicle_id.setter
    def active_vehicle_id(self, val: str):
        self.live_models['vehicle'] = val

    @property
    def active_plate_id(self) -> str:
        return self.live_models.get('plate', FACTORY_DEFAULTS['live']['plate'])

    @active_plate_id.setter
    def active_plate_id(self, val: str):
        self.live_models['plate'] = val

    @property
    def active_person_id(self) -> str:
        return self.live_models.get('person', FACTORY_DEFAULTS['live']['person'])

    @active_person_id.setter
    def active_person_id(self, val: str):
        self.live_models['person'] = val

    @property
    def active_ocr_id(self) -> str:
        return self.live_models.get('ocr', FACTORY_DEFAULTS['live']['ocr'])

    @active_ocr_id.setter
    def active_ocr_id(self, val: str):
        self.live_models['ocr'] = val

    def get_active_model_id(self, category: str, target: str='live') -> str:
        """Retrieves active model ID for specified target profile ('live' vs 'upload')."""
        t_dict = self.upload_models if target == 'upload' else self.live_models
        def_dict = FACTORY_DEFAULTS['upload'] if target == 'upload' else FACTORY_DEFAULTS['live']
        return t_dict.get(category) or def_dict.get(category, '')

    def _load_state(self):
        try:
            if CUSTOM_NAMES_FILE.is_file():
                with open(CUSTOM_NAMES_FILE, 'r', encoding='utf-8') as f:
                    custom_names = json.load(f)
                    for mid, new_name in custom_names.items():
                        if mid in VEHICLE_MODELS:
                            VEHICLE_MODELS[mid]['name'] = new_name
                        elif mid in PLATE_MODELS:
                            PLATE_MODELS[mid]['name'] = new_name
        except Exception as e:
            print(f'[WARN] Failed to load custom model names: {e}')
        try:
            if ACTIVE_MODELS_FILE.is_file():
                with open(ACTIVE_MODELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'live' in data and isinstance(data['live'], dict):
                        for k, v in data['live'].items():
                            if v and k in FACTORY_DEFAULTS['live']:
                                self.live_models[k] = v
                    else:
                        if data.get('active_vehicle') in VEHICLE_MODELS:
                            self.live_models['vehicle'] = data['active_vehicle']
                        if data.get('active_plate') in PLATE_MODELS:
                            self.live_models['plate'] = data['active_plate']
                        if data.get('active_person') in VEHICLE_MODELS:
                            self.live_models['person'] = data['active_person']
                    if 'upload' in data and isinstance(data['upload'], dict):
                        for k, v in data['upload'].items():
                            if v and k in FACTORY_DEFAULTS['live']:
                                self.upload_models[k] = v
        except Exception as e:
            print(f'[WARN] Failed to load active models state: {e}')

    def _save_state(self):
        try:
            ACTIVE_MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(ACTIVE_MODELS_FILE, 'w', encoding='utf-8') as f:
                json.dump({'live': self.live_models, 'upload': self.upload_models, 'active_vehicle': self.active_vehicle_id, 'active_plate': self.active_plate_id, 'active_person': self.active_person_id, 'active_ocr': self.active_ocr_id}, f, indent=2)
        except Exception as e:
            print(f'[WARN] Failed to save active models state: {e}')

    def update_model_names(self, name_map: Dict[str, str]) -> Dict[str, str]:
        """Dynamically renames models in memory and persists them to custom_model_names.json."""
        with self._lock:
            applied = {}
            for mid, new_name in name_map.items():
                clean_name = str(new_name).strip()
                if not clean_name:
                    continue
                if mid in VEHICLE_MODELS:
                    VEHICLE_MODELS[mid]['name'] = clean_name
                    applied[mid] = clean_name
                elif mid in PLATE_MODELS:
                    PLATE_MODELS[mid]['name'] = clean_name
                    applied[mid] = clean_name
            if applied:
                try:
                    CUSTOM_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
                    existing = {}
                    if CUSTOM_NAMES_FILE.is_file():
                        with open(CUSTOM_NAMES_FILE, 'r', encoding='utf-8') as f:
                            existing = json.load(f)
                    existing.update(applied)
                    with open(CUSTOM_NAMES_FILE, 'w', encoding='utf-8') as f:
                        json.dump(existing, f, indent=2)
                except Exception as e:
                    print(f'[WARN] Failed to persist custom model names: {e}')
            return applied

    def _get_file_path(self, filename: str) -> Path:
        p_yolo = YOLO_MODELS_DIR / filename
        if p_yolo.is_file():
            return p_yolo
        p_root = BASE_DIR / filename
        if p_root.is_file():
            return p_root
        p_models = BASE_DIR / 'models' / filename
        if p_models.is_file():
            return p_models
        return p_yolo

    def is_model_downloaded(self, filename: str) -> bool:
        p = self._get_file_path(filename)
        return p.is_file() and p.stat().st_size > 1000

    def resolve_model_path(self, model_key_or_filename: str) -> str:
        """Resolves a key or filename to an absolute file path on disk."""
        if model_key_or_filename in VEHICLE_MODELS:
            fname = VEHICLE_MODELS[model_key_or_filename]['filename']
        elif model_key_or_filename in PLATE_MODELS:
            fname = PLATE_MODELS[model_key_or_filename]['filename']
        p = self._get_file_path(fname)
        if p.is_file():
            return str(p)
        return str(YOLO_MODELS_DIR / fname)

    def model_supports_person(self, model_key_or_path: str) -> bool:
        """
        Dynamically determines whether a YOLO model can detect persons alongside vehicles.
        Future-proof: dynamically inspects checkpoint class ontology if not cached.
        """
        if not model_key_or_path:
            return False
        with self._lock:
            if model_key_or_path in self._person_support_cache:
                return self._person_support_cache[model_key_or_path]
            if model_key_or_path in VEHICLE_MODELS and 'supports_person' in VEHICLE_MODELS[model_key_or_path]:
                val = bool(VEHICLE_MODELS[model_key_or_path]['supports_person'])
                self._person_support_cache[model_key_or_path] = val
                return val
        resolved_path = self.resolve_model_path(model_key_or_path)
        try:
            if Path(resolved_path).is_file():
                inst = self.load_yolo_instance(resolved_path)
                if hasattr(inst, 'names') and inst.names:
                    names_lower = [str(v).lower() for v in inst.names.values()]
                    person_synonyms = {'person', 'pedestrian', 'people', 'human', 'crowd'}
                    has_person = any((k in names_lower for k in person_synonyms))
                    with self._lock:
                        self._person_support_cache[model_key_or_path] = has_person
                    return has_person
        except Exception as e:
            print(f'[ModelRegistry] Note: Could not dynamically inspect person classes for {model_key_or_path}: {e}')
        fallback = model_key_or_path != 'uvh26_yolo11x'
        with self._lock:
            self._person_support_cache[model_key_or_path] = fallback
        return fallback

    def get_catalog(self) -> Dict[str, Any]:
        active_veh_supports_person = self.model_supports_person(self.active_vehicle_id)
        with self._lock:
            vehicle_list = []
            for mid, m in VEHICLE_MODELS.items():
                downloaded = self.is_model_downloaded(m['filename'])
                supports_person = self.model_supports_person(mid)
                vehicle_list.append({**m, 'downloaded': downloaded, 'active': mid == self.active_vehicle_id, 'supports_person': supports_person})
            plate_list = []
            for mid, m in PLATE_MODELS.items():
                downloaded = self.is_model_downloaded(m['filename'])
                plate_list.append({**m, 'downloaded': downloaded, 'active': mid == self.active_plate_id})
            person_list = []
            for mid, m in VEHICLE_MODELS.items():
                downloaded = self.is_model_downloaded(m['filename'])
                supports_person = self.model_supports_person(mid)
                p_name = m['name'].replace('Vehicle', 'Person')
                if not supports_person:
                    p_name = f"{m['name']} (Vehicle Only - No Person Class)"
                    p_desc = 'Specialized vehicle detector (does not output person class).'
                elif 'driveindia' in mid:
                    p_name = m['name'].replace('DriveIndia TiHAN', 'DriveIndia TiHAN (Pedestrian & Person 🇮🇳)')
                    p_desc = 'IIT Hyderabad TiHAN benchmark detector for Indian pedestrians, crowd, and roadside traffic.'
                else:
                    p_desc = 'YOLO model detecting pedestrians & persons alongside vehicles.'
                person_list.append({'id': mid, 'name': p_name, 'family': m['family'], 'filename': m['filename'], 'size_mb': m['size_mb'], 'description': p_desc, 'downloaded': downloaded, 'active': mid == self.active_person_id, 'supports_person': supports_person})
            recognizer_list = []

    def get_catalog(self, target: str='live') -> Dict[str, Any]:
        active_veh_id = self.upload_models.get('vehicle') if target == 'upload' else self.live_models.get('vehicle')
        active_plt_id = self.upload_models.get('plate') if target == 'upload' else self.live_models.get('plate')
        active_per_id = self.upload_models.get('person') if target == 'upload' else self.live_models.get('person')
        active_ocr_id = self.upload_models.get('ocr') if target == 'upload' else self.live_models.get('ocr')
        active_veh_supports_person = self.model_supports_person(active_veh_id)
        with self._lock:
            vehicle_list = []
            for mid, m in VEHICLE_MODELS.items():
                downloaded = self.is_model_downloaded(m['filename'])
                supports_person = self.model_supports_person(mid)
                vehicle_list.append({**m, 'downloaded': downloaded, 'active': mid == active_veh_id, 'supports_person': supports_person})
            plate_list = []
            for mid, m in PLATE_MODELS.items():
                downloaded = self.is_model_downloaded(m['filename'])
                plate_list.append({**m, 'downloaded': downloaded, 'active': mid == active_plt_id})
            person_list = []
            for mid, m in VEHICLE_MODELS.items():
                downloaded = self.is_model_downloaded(m['filename'])
                supports_person = self.model_supports_person(mid)
                p_name = m['name'].replace('Vehicle', 'Person')
                if not supports_person:
                    p_name = f"{m['name']} (Vehicle Only - No Person Class)"
                    p_desc = 'Specialized vehicle detector (does not output person class).'
                elif 'driveindia' in mid:
                    p_name = m['name'].replace('DriveIndia TiHAN', 'DriveIndia TiHAN (Pedestrian & Person 🇮🇳)')
                    p_desc = 'IIT Hyderabad TiHAN benchmark detector for Indian pedestrians, crowd, and roadside traffic.'
                else:
                    p_desc = 'YOLO model detecting pedestrians & persons alongside vehicles.'
                person_list.append({'id': mid, 'name': p_name, 'family': m['family'], 'filename': m['filename'], 'size_mb': m['size_mb'], 'description': p_desc, 'downloaded': downloaded, 'active': mid == active_per_id, 'supports_person': supports_person})
            recognizer_list = []
            ocr_list = []
            for mid, m in OCR_MODELS.items():
                if mid == 'paddleocr_v4_server':
                    downloaded = (BASE_DIR / 'models' / 'ocr' / 'ch_PP-OCRv4_rec_server_infer' / 'inference.pdiparams').is_file()
                else:
                    downloaded = self.is_model_downloaded(m['filename'])
                ocr_list.append({**m, 'downloaded': downloaded, 'active': mid == active_ocr_id})
            return {'target': target, 'live_models': dict(self.live_models), 'upload_models': dict(self.upload_models), 'factory_defaults': FACTORY_DEFAULTS, 'active_vehicle': active_veh_id, 'active_plate': active_plt_id, 'active_person': active_per_id, 'active_ocr': active_ocr_id, 'active_vehicle_supports_person': active_veh_supports_person, 'vehicle_models': vehicle_list, 'plate_models': plate_list, 'person_models': person_list, 'ocr_models': ocr_list}

    def set_active_models(self, vehicle_id: Optional[str]=None, plate_id: Optional[str]=None, person_id: Optional[str]=None, ocr_id: Optional[str]=None, target: str='live') -> Dict[str, Any]:
        with self._lock:
            target_clean = 'upload' if str(target).strip().lower() == 'upload' else 'live'
            target_dict = self.upload_models if target_clean == 'upload' else self.live_models
            if vehicle_id and vehicle_id in VEHICLE_MODELS:
                target_dict['vehicle'] = vehicle_id
            if plate_id and plate_id in PLATE_MODELS:
                target_dict['plate'] = plate_id
            veh_supports_person = self.model_supports_person(target_dict['vehicle'])
            if veh_supports_person:
                target_dict['person'] = target_dict['vehicle']
            elif person_id and person_id in VEHICLE_MODELS and self.model_supports_person(person_id):
                target_dict['person'] = person_id
            elif not self.model_supports_person(target_dict['person']):
                target_dict['person'] = 'yolo11n' if 'yolo11n' in VEHICLE_MODELS else 'driveindia_tihan_yolov10m'
            if ocr_id and ocr_id in OCR_MODELS:
                target_dict['ocr'] = ocr_id
            self._save_state()
            return {'target': target_clean, 'active_vehicle': target_dict['vehicle'], 'active_plate': target_dict['plate'], 'active_person': target_dict['person'], 'active_ocr': target_dict.get('ocr', 'paddleocr_v4_server'), 'active_vehicle_supports_person': veh_supports_person, 'live_models': dict(self.live_models), 'upload_models': dict(self.upload_models), 'factory_defaults': FACTORY_DEFAULTS}

    def revert_to_defaults(self, target: Optional[str]=None) -> Dict[str, Any]:
        """1-Click Revert: Restores specified profile or both profiles to rock-solid factory defaults."""
        with self._lock:
            t = str(target).strip().lower() if target else None
            if t == 'live':
                self.live_models = dict(FACTORY_DEFAULTS['live'])
            elif t == 'upload':
                self.upload_models = dict(FACTORY_DEFAULTS['upload'])
            else:
                self.live_models = dict(FACTORY_DEFAULTS['live'])
                self.upload_models = dict(FACTORY_DEFAULTS['upload'])
            self._save_state()
            return {'status': 'success', 'message': 'AI models successfully reverted to default configuration.', 'reverted_target': t or 'all', 'live_models': dict(self.live_models), 'upload_models': dict(self.upload_models), 'factory_defaults': FACTORY_DEFAULTS}

    def get_active_summary(self, target: str='live') -> Dict[str, Any]:
        with self._lock:
            t_dict = self.upload_models if target == 'upload' else self.live_models
            return {'target': target, 'active_vehicle': t_dict.get('vehicle'), 'active_plate': t_dict.get('plate'), 'active_person': t_dict.get('person'), 'active_ocr': t_dict.get('ocr', 'paddleocr_v4_server'), 'active_vehicle_supports_person': self.model_supports_person(t_dict.get('vehicle')), 'live_models': dict(self.live_models), 'upload_models': dict(self.upload_models)}

    def get_person_detector(self) -> Optional[YOLO]:
        """
        Returns a dedicated person YOLO detector instance ONLY when the active vehicle model
        is vehicle-only. When active vehicle model supports persons, returns None
        (single-pass inference is used).
        """
        if self.model_supports_person(self.active_vehicle_id):
            return None
        target_id = self.active_person_id
        if not self.model_supports_person(target_id):
            target_id = 'yolo11n' if 'yolo11n' in VEHICLE_MODELS else 'driveindia_tihan_yolov10m'
        try:
            detector = self.load_yolo_instance(target_id)
            if detector is not None:
                return detector
        except Exception as e:
            print(f'[ModelRegistry Warning] Failed to load person detector {target_id}: {e}')
        if target_id != 'yolo11n' and 'yolo11n' in VEHICLE_MODELS:
            try:
                return self.load_yolo_instance('yolo11n')
            except Exception:
                pass
        return None

    def load_yolo_instance(self, path_or_key: str) -> Optional[YOLO]:
        """Cached YOLO instance loader with automatic garbage collection."""
        resolved = self.resolve_model_path(path_or_key)
        with self._lock:
            if resolved in self._cached_yolo_instances:
                return self._cached_yolo_instances[resolved]
            try:
                import gc
                gc.collect()
                model = YOLO(resolved)
                self._cached_yolo_instances[resolved] = model
                return model
            except Exception as e:
                print(f'[ModelRegistry Error] Failed to instantiate YOLO model from {resolved}: {e}')
                return None
registry = ModelRegistry()
