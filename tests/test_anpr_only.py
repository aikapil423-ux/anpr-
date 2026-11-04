"""ANPR-only regression checks: routes, uploads, persistence, and model catalogs."""
from contextlib import closing
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
import app as api
from src.pipeline.unified_pipeline import UnifiedPipeline
from src.database.captured_db import CapturedDB
from src.database.investigation_history_db import InvestigationHistoryDB
from src.detection.model_registry import registry

class ANPROnlyTests(unittest.TestCase):
    def test_no_biometric_routes_or_models(self):
        self.assertFalse(any('frs' in r.path or 'face' in r.path for r in api.app.routes if hasattr(r,'path')))
        catalog = registry.get_catalog()
        self.assertIn('vehicle_models',catalog)
        self.assertIn('plate_models',catalog)
        self.assertIn('ocr_models',catalog)
        self.assertFalse(any('face' in key or 'embedder' in key for key in catalog))
    def test_photo_adapter_rejects_removed_modality(self):
        image=np.zeros((120,160,3),np.uint8)
        p=UnifiedPipeline()
        result=p.process_image(image,target='vehicle')
        self.assertTrue(result['success'])
        self.assertNotIn('faces',result)
        with self.assertRaises(ValueError):p.process_image(image,target='face')
    def test_video_upload_has_no_biometric_dependency(self):
        with tempfile.TemporaryDirectory() as d:
            video=Path(d)/'sample.avi'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),5,(160,120))
            self.assertTrue(writer.isOpened())
            for i in range(3):writer.write(np.zeros((120,160,3),np.uint8))
            writer.release()
            class Pipeline:
                def reset_state(self):pass
                def process_frame(self,*a,**k):return []
                def drain_ocr_queue(self,**k):pass
                def finalize(self):return {'verified_vehicles':[],'needs_review':[],'unreadable_vehicles':[]}
            anpr=Pipeline()
            history=InvestigationHistoryDB(str(Path(d)/'history.sqlite'))
            with patch.object(api,'OUTPUTS_DIR',d),patch.object(api,'get_upload_anpr_pipeline',return_value=anpr),patch.object(api,'get_upload_unified_pipeline',return_value=UnifiedPipeline(anpr)),patch.object(api,'investigation_db',history):
                result=api._process_unified_video_sync(video.read_bytes(),'sample.avi',5,{'operator_username':'test'},save_annotated=False,target='vehicle',location='Aggi Park 2')
            self.assertTrue(result['success'])
            self.assertNotIn('faces',result)
            rows=history.list_searches()
            self.assertEqual(len(rows),1)
    def test_new_vehicle_and_history_records_have_no_face_fields(self):
        with tempfile.TemporaryDirectory() as d:
            db=CapturedDB(str(Path(d)/'captures.sqlite'))
            cid=db.add_capture('HR26AB1234',confidence=95,location='Aggi Park 2',gps_coords='0,0')
            record=db.get_by_id(cid)
            self.assertEqual(record['district'],'Karnal')
            self.assertFalse(any('face' in k for k in record))
            history=InvestigationHistoryDB(str(Path(d)/'history.sqlite'))
            added=history.add_search({'filename':'sample.avi','vehicles_json':[]})
            self.assertTrue(added['success'])
            row=history.get_search_by_id(added['search_id'])
            self.assertNotIn('frs_enabled',row)
            self.assertNotIn('faces',row)
    def test_karnal_accounts_exist(self):
        from src.database.auth_db import AuthDB
        with tempfile.TemporaryDirectory() as d:
            db=AuthDB(str(Path(d)/'auth.sqlite'))
            with closing(db._get_connection()) as conn:
                rows=conn.execute("SELECT username,district FROM users WHERE username IN ('admin_karnal','op_karnal')").fetchall()
            self.assertEqual(len(rows),2)
            self.assertTrue(all(row['district']=='Karnal' for row in rows))

if __name__=='__main__':unittest.main()
