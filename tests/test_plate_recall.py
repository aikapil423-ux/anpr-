"""Regression checks for complete OCR numbers and bike/bus plate localization."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import numpy as np
from src.ocr.ocr_engine import OCREngine
from src.ocr.normalizer import IndianPlateNormalizer
from src.detection.plate_candidates import detect_plate_candidates
from src.quality.crop_filter import CropQualityFilter
from src.database.captured_db import CapturedDB

class PlateRecallTests(unittest.TestCase):
    def test_single_and_batch_ocr_enforce_8_to_11_characters(self):
        engine=OCREngine(use_awiros=False)
        crop=np.zeros((48,200,3),np.uint8)
        for text in ['MRC71','1234567','DL01ABC12345']:
            with patch.object(engine,'_run_ocr_single',return_value=(text,.99)):
                self.assertEqual(engine.read_text(crop),('',0.0))
                self.assertEqual(engine.read_batch([crop]),[('',0.0)])
        for text in ['DL1C1234','HR54G2404','HR63GV5303','DL01ABC1234']:
            with patch.object(engine,'_run_ocr_single',return_value=(text,.95)):
                self.assertEqual(engine.read_text(crop)[0],text)
                self.assertEqual(engine.read_batch([crop])[0][0],text)
    def test_eight_character_plate_is_not_padded_with_guessed_digits(self):
        normalizer=IndianPlateNormalizer()
        valid,_,plate=normalizer.validate('DL 1 C 1234')
        self.assertTrue(valid);self.assertEqual(plate,'DL1C1234')
    def test_crop_retry_covers_bus_and_bike_and_restores_frame_coordinates(self):
        frame=np.zeros((140,300,3),np.uint8)
        vehicles=[{'bbox':(20,10,140,110),'cls_name':'bus'}, {'bbox':(180,20,270,130),'cls_name':'motorcycle'}]
        class Detector:
            def __init__(self):self.calls=[]
            def detect_in_frame(self,image,vehicle_boxes=None,conf_thresh=None):
                self.calls.append((image.shape,vehicle_boxes,conf_thresh))
                if image.shape==frame.shape:return []
                return [{'bbox':(15,50,60,80),'conf':.42}]
        detector=Detector();result=detect_plate_candidates(detector,frame,vehicles,.35)
        self.assertEqual(len(result),2)
        self.assertEqual({r['vehicle_bbox'] for r in result},{v['bbox'] for v in vehicles})
        for row in result:
            self.assertGreaterEqual(row['bbox'][0],row['vehicle_bbox'][0])
        self.assertTrue(all(call[2]==.35 for call in detector.calls))
    def test_scene_plate_detection_runs_when_vehicle_detector_misses(self):
        class Detector:
            def detect_in_frame(self,image,vehicle_boxes=None,conf_thresh=None):
                assert vehicle_boxes is None
                return [{'bbox':(20,20,100,50),'conf':.8,'vehicle_bbox':None}]
        self.assertEqual(len(detect_plate_candidates(Detector(),np.zeros((140,300,3),np.uint8),[],.35)),1)
    def test_moderate_detector_confidence_still_requires_a_clear_crop(self):
        crop=np.indices((50,120)).sum(axis=0)%2*255
        crop=np.repeat(crop.astype('uint8')[:,:,None],3,axis=2)
        gate=CropQualityFilter()
        ok,_,_,_=gate.validate(crop,.42,(50,50,170,100),(300,400))
        self.assertTrue(ok)
        self.assertFalse(gate.validate(crop,.2,(50,50,170,100),(300,400))[0])
    def test_partial_capture_is_presented_as_unreadable_with_evidence_retained(self):
        with tempfile.TemporaryDirectory() as d:
            db=CapturedDB(str(Path(d)/'captures.sqlite'))
            cid=db.add_capture('MRC71',confidence=95,vehicle_img=np.zeros((100,100,3),np.uint8))
            record=db.get_by_id(cid)
            self.assertEqual(record['plate_number'],'UNREADABLE')
            self.assertFalse(record['is_hotlist_hit'])
            self.assertIsNotNone(record['vehicle_pic_path'])

    def test_overlapping_vehicle_tracks_do_not_duplicate_the_same_plate(self):
        frame=np.zeros((140,300,3),np.uint8)
        vehicles=[{'bbox':(20,10,140,110),'cls_name':'motorcycle'},{'bbox':(18,8,142,112),'cls_name':'bicycle'}]
        class Detector:
            def detect_in_frame(self,image,vehicle_boxes=None,conf_thresh=None):
                if image.shape==frame.shape:
                    return [{'bbox':(50,70,100,95),'conf':.8,'vehicle_bbox':vehicles[0]['bbox']}]
                return [{'bbox':(36,67,86,92),'conf':.6}]
        self.assertEqual(len(detect_plate_candidates(Detector(),frame,vehicles,.35)),1)

if __name__=='__main__':unittest.main()
