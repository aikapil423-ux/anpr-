from typing import List, Dict, Any, Tuple, Optional, Union
import os
import time
import base64
import cv2
import numpy as np
from config import ANPRConfig
from src.pipeline.anpr_pipeline import ANPRPipeline
from src.ocr.enhancer import PlateEnhancer

def encode_img_base64(img: Optional[np.ndarray], quality: int=90, *, lossless: bool=False) -> str:
    if img is None or img.size == 0:
        return ''
    extension = '.png' if lossless else '.jpg'
    options = [] if lossless else [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buffer = cv2.imencode(extension, img, options)
    if not success:
        return ''
    return base64.b64encode(buffer).decode('utf-8')

class UnifiedPipeline:

    def __init__(self, anpr_pipeline: Optional[ANPRPipeline]=None):
        self.anpr = anpr_pipeline

    def set_pipelines(self, anpr_pipeline: ANPRPipeline):
        self.anpr = anpr_pipeline

    def annotate_frame(self, frame: np.ndarray, active_vehicles: List[Dict[str, Any]], people_detections: Optional[List[Dict[str, Any]]]=None, people_count: int=0, layers: Optional[Dict[str, bool]]=None) -> np.ndarray:
        annotated = frame.copy()
        h, w = frame.shape[:2]
        cfg_layers = layers or {'vehicle_box': True, 'plate_box': True, 'ocr_text': True, 'person_box': True, 'people_counter': True}
        if cfg_layers.get('person_box', True) and people_detections:
            for p in people_detections:
                px1, py1, px2, py2 = p['bbox']
                p_color = (34, 197, 94)
                cv2.rectangle(annotated, (px1, py1), (px2, py2), p_color, 1)
                p_lbl = 'Person'
                (tw, th), _ = cv2.getTextSize(p_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                cv2.rectangle(annotated, (px1, max(0, py1 - th - 4)), (px1 + tw + 4, py1), p_color, -1)
                cv2.putText(annotated, p_lbl, (px1 + 2, max(th + 1, py1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        for v in active_vehicles:
            vx1, vy1, vx2, vy2 = v['bbox']
            vtid = v.get('track_id', 1)
            cls_name = v.get('cls_name', 'Vehicle').capitalize()
            veh_color = (255, 140, 0)
            if cfg_layers.get('vehicle_box', True):
                cv2.rectangle(annotated, (vx1, vy1), (vx2, vy2), veh_color, 1)
                v_lbl = f'{cls_name}'
                (vtw, vth), _ = cv2.getTextSize(v_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                cv2.rectangle(annotated, (vx1, max(0, vy1 - vth - 4)), (vx1 + vtw + 4, vy1), veh_color, -1)
                cv2.putText(annotated, v_lbl, (vx1 + 2, max(vth + 1, vy1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
            pbox = v.get('plate_bbox')
            if pbox is not None and (cfg_layers.get('plate_box', True) or cfg_layers.get('ocr_text', True)):
                px1, py1, px2, py2 = pbox
                disp_plate = v.get('display_plate') or v.get('candidate_plate') or ''
                is_valid = v.get('is_verified', False)
                plate_color = (16, 185, 129) if is_valid else (11, 158, 245)
                if cfg_layers.get('plate_box', True):
                    cv2.rectangle(annotated, (px1, py1), (px2, py2), plate_color, 1)
                if cfg_layers.get('ocr_text', True):
                    plate_lbl = f'{disp_plate}' if disp_plate else 'Plate'
                    (ptw, pth), _ = cv2.getTextSize(plate_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                    cv2.rectangle(annotated, (px1, max(0, py1 - pth - 4)), (px1 + ptw + 4, py1), plate_color, -1)
                    cv2.putText(annotated, plate_lbl, (px1 + 2, max(pth + 1, py1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1)
        if cfg_layers.get('people_counter', True):
            badge_text = f'VEHICLES: {len(active_vehicles)}'
            (btw, bth), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            pad = 8
            bx2 = w - 16
            bx1 = bx2 - btw - pad * 2
            by1 = 16
            by2 = by1 + bth + pad * 2
            overlay = annotated.copy()
            cv2.rectangle(overlay, (bx1, by1), (bx2, by2), (15, 23, 42), -1)
            cv2.addWeighted(overlay, 0.85, annotated, 0.15, 0, annotated)
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (56, 189, 248), 1)
            cv2.putText(annotated, badge_text, (bx1 + pad, by1 + bth + pad - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        return annotated

    def process_image(self, image: np.ndarray, district: str='Panipat', operator_username: str='op_5421', operator_id: Optional[int]=None, station: str='PHQ', target: str='both') -> Dict[str, Any]:
        if target not in ('vehicle', 'both', 'anpr'):
            raise ValueError('Only vehicle analysis is supported')
        if image is None or image.size == 0:
            return {'success': False, 'error': 'Invalid image'}
        h, w = image.shape[:2]
        t = str(target or 'both').strip().lower()
        run_anpr = t in ('both', 'vehicle', 'vehicles', 'vehicle_only', 'anpr')
        vehicle_results = []
        if self.anpr:
            self.anpr.reset_state()
            active_displays = self.anpr.process_frame(image, frame_idx=1, timestamp=0.0, is_photo=True)
            self.anpr.drain_ocr_queue(timeout=30.0)
            for v in self.anpr.track_merger.vehicles.values():
                self.anpr.voting_engine.vote_on_vehicle(v, is_single_image=True)
            for ad in active_displays:
                vbox = ad['bbox']
                tid = ad.get('track_id', 1)
                cls_name = ad.get('cls_name', 'Vehicle').capitalize()
                v_rec = self.anpr.track_merger.vehicles.get(ad['vehicle_id'])
                reading = v_rec.readings[-1] if v_rec and v_rec.readings else None
                pbox = ad.get('plate_bbox') or (v_rec.last_plate_bbox if v_rec else None)
                if pbox is None and len(active_displays) > 1:
                    v_w = max(0, vbox[2] - vbox[0])
                    v_h = max(0, vbox[3] - vbox[1])
                    if v_w * v_h < w * h * 0.05:
                        continue
                p_crop = image[pbox[1]:pbox[3], pbox[0]:pbox[2]] if pbox else None
                v_crop = image[vbox[1]:vbox[3], vbox[0]:vbox[2]]
                norm_plate = v_rec.final_plate if v_rec and v_rec.final_plate and (v_rec.final_plate != 'UNREADABLE') else ad.get('final_plate') or ad.get('candidate_plate') or (reading.normalized_text if reading else '')
                disp_plate = v_rec.display_plate if v_rec and v_rec.display_plate and (v_rec.display_plate != 'UNREADABLE') else ad.get('display_plate') or (self.anpr.normalizer.format_display(norm_plate) if norm_plate else '')
                raw_ad_conf = ad.get('confidence', 0.0) or 0.0
                ad_conf_pct = round(float(raw_ad_conf) * (100 if raw_ad_conf <= 1.0 else 1), 1)
                conf_pct = round(float(v_rec.final_confidence) * 100, 1) if v_rec and v_rec.final_confidence else round(reading.ocr_confidence * 100, 1) if reading else ad_conf_pct
                enh_crop = v_rec.best_enhanced_crop if v_rec and v_rec.best_enhanced_crop is not None else getattr(reading, 'enhanced_crop', None) if reading else None
                prep_meta = v_rec.preprocessing_meta if v_rec and v_rec.preprocessing_meta else getattr(reading, 'preprocessing_meta', None) if reading else None
                if prep_meta is None and p_crop is not None and (p_crop.size > 0):
                    prep_diag = PlateEnhancer.get_preprocessing_diagnostics(p_crop, ocr_diag=getattr(self.anpr.ocr_engine, 'last_ocr_diagnostics', {}))
                    enh_crop = prep_diag.pop('enhanced_image', None)
                    prep_meta = prep_diag
                elif isinstance(prep_meta, dict):
                    prep_meta = {k: v for k, v in prep_meta.items() if not isinstance(v, np.ndarray)}
                is_valid = bool(getattr(v_rec, 'is_verified', False) if v_rec and hasattr(v_rec, 'is_verified') and (v_rec.final_plate != 'UNREADABLE') else ad.get('is_verified') or bool(norm_plate and norm_plate != 'UNREADABLE'))
                vehicle_results.append({'vehicle_id': f"VEH-{ad['vehicle_id']}", 'track_id': f'V-{tid}', 'cls_name': cls_name, 'bbox': vbox, 'plate_bbox': pbox, 'final_plate': norm_plate, 'display_plate': disp_plate or norm_plate or 'UNREADABLE', 'confidence': conf_pct, 'is_verified': is_valid, 'plate_crop_base64': encode_img_base64(p_crop, lossless=True), 'vehicle_crop_base64': encode_img_base64(v_crop), 'enhanced_crop_base64': encode_img_base64(enh_crop), 'preprocessing_meta': prep_meta, 'is_traffic_violation': bool(ad.get('is_traffic_violation') or getattr(v_rec, 'is_traffic_violation', False)), 'violation_type': ad.get('violation_type') or getattr(v_rec, 'violation_type', None), 'violation_fine': ad.get('violation_fine') or getattr(v_rec, 'violation_fine', 0), 'violation_id': ad.get('violation_id') or getattr(v_rec, 'violation_id', None), 'violation_details': ad.get('violation_details') or getattr(v_rec, 'violation_details', None)})
        people_detections = []
        correlation = {'linked_pairs': [], 'spatial_overlap_threshold': 0.35, 'total_correlations': 0, 'summary': f'Single modality analysis ({target}) - spatial cross-modal linking bypassed.'}
        layers = {'vehicle_box': True, 'plate_box': True, 'ocr_text': True, 'person_box': False, 'people_counter': True}
        people_count = 0
        annotated = self.annotate_frame(frame=image, active_vehicles=vehicle_results, people_detections=[], people_count=people_count, layers=layers)
        return {'success': True, 'target': target, 'vehicles': vehicle_results, 'people_count': people_count, 'correlation': correlation, 'annotated_image_base64': encode_img_base64(annotated, quality=92)}
