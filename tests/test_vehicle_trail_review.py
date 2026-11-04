"""Exact/near-match routing, decisions, persistence, camera routes and scope."""
import app as api
import tempfile
import unittest
from pathlib import Path
import numpy as np
from src.database.vehicle_db import VehicleDB
from src.database.captured_db import CapturedDB
from src.database.trail_review_db import review_store

class VehicleReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.watch=VehicleDB(str(self.root/'vehicle_db.sqlite'))
        with self.watch._get_connection() as conn:
            conn.execute("INSERT INTO vehicles(vehicle_number,display_number,vehicle_type,vehicle_color,involved_in_case,created_at,status) VALUES ('HR63GV5303','HR 63 GV 5303','Car','White',1,'2026-11-04','ACTIVE')")
        conn.close()
        self.captures=CapturedDB(str(self.root/'captured_db.sqlite'),max_records=1)
        self.store=review_store(str(self.root))
    def tearDown(self):self.tmp.cleanup()
    def capture(self,plate,location='Aggi Park 1',at='2026-11-04T10:00:00+05:30'):
        return self.captures.add_capture(plate,confidence=95,location=location,captured_at=at,operator_username='op_karnal',plate_img=np.ones((25,90,3),dtype=np.uint8)*128,cooldown_seconds=0)
    def test_exact_auto_added_and_single_camera(self):
        cid=self.capture('HR63GV5303');row=self.store.list()[0]
        self.assertEqual(row['status'],'EXACT');self.assertEqual(row['route_plate'],'HR63GV5303')
        self.assertEqual(row['camera_id'],'KNL-ICCC-001-C01');self.assertEqual(row['lat'],29.693996)
        self.assertTrue(row['plate_photo'])
    def test_near_match_waits_for_same_then_links_without_changing_detected_plate(self):
        cid=self.capture('HR63GW5303');row=self.store.list()[0]
        self.assertEqual(row['status'],'PENDING');self.assertEqual(row['route_plate'],'HR63GW5303')
        decided=self.store.decide(row['id'],'SAME','op_karnal','Karnal','op_karnal')
        self.assertEqual(decided['route_plate'],'HR63GV5303');self.assertEqual(decided['detected_plate'],'HR63GW5303')
        self.captures.update_capture(cid,confidence=97,update_timestamp=False)
        self.assertEqual(self.store.list()[0]['status'],'SAME')
        self.assertEqual(self.store.decide(row['id'],'SAME','op_karnal')['status'],'SAME')
        with self.assertRaises(ValueError):self.store.decide(row['id'],'NOT_SAME','op_karnal')
    def test_not_same_is_normal_and_does_not_join_watchlist_route(self):
        self.capture('HR63GW5303');row=self.store.list()[0]
        decided=self.store.decide(row['id'],'NOT_SAME','op_karnal')
        self.assertEqual(decided['route_plate'],'HR63GW5303');self.assertEqual(decided['status'],'NOT_SAME')
        self.assertFalse(any(r['status'] in ('EXACT','SAME') for r in self.store.list()))
    def test_multiple_cameras_and_fifo_photo_survival(self):
        cid=self.capture('HR63GW5303');pending=self.store.list()[0]
        saved=self.store.photos/Path(pending['plate_photo']).name
        self.capture('DL01AA1234','Ambedkar Chowk 1','2026-11-04T10:01:00+05:30')
        self.assertIsNone(self.captures.get_by_id(cid));self.assertTrue(saved.is_file())
        self.capture('DL01AA1234','Atal Park 1','2026-11-04T10:02:00+05:30')
        normal=[r for r in self.store.list() if r['route_plate']=='DL01AA1234']
        self.assertEqual(len(normal),2);self.assertEqual(len({r['camera_id'] for r in normal}),2)
        self.store.decide(pending['id'],'SAME','op_karnal')
    def test_scope_blocks_cross_district_and_operator_review(self):
        self.capture('HR63GW5303');row=self.store.list()[0]
        self.assertEqual(self.store.list('Panipat'),[])
        with self.assertRaises(LookupError):self.store.decide(row['id'],'SAME','intruder','Panipat')
        with self.assertRaises(LookupError):self.store.decide(row['id'],'SAME','intruder','Karnal','intruder')

    def test_api_review_and_unauthenticated_access(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from types import SimpleNamespace
        client=TestClient(api.app)
        cid=self.capture('HR63GW5303')
        row=self.store.list()[0]
        user={'username':'op_karnal','role':'OPERATOR','district':'Karnal'}
        with patch.object(api,'get_current_user_optional',return_value=None):
            self.assertEqual(client.get('/api/vehicle-trails/observations').status_code,401)
        with patch.object(api,'get_current_user_optional',return_value=user),patch.object(api,'captured_db',SimpleNamespace(_get_target=lambda:self.captures)):
            res=client.get('/api/vehicle-trails/observations')
            self.assertEqual(res.status_code,200);self.assertEqual(res.json()['pending_count'],1)
            url=f"/api/vehicle-trails/observations/{row['id']}/decision"
            bad=client.post(url,json={'decision':'SAME','detected_plate':'STALE','candidate_plate':row['candidate_plate']})
            self.assertEqual(bad.status_code,409)
            res=client.post(url,json={'decision':'NOT_SAME','detected_plate':row['detected_plate'],'candidate_plate':row['candidate_plate']})
            self.assertEqual(res.status_code,200)
            self.assertEqual(res.json()['observation']['status'],'NOT_SAME')
            self.assertFalse(self.captures.get_by_id(cid)['is_hotlist_hit'])
            self.assertEqual(client.get('/api/vehicle-trails/observations').json()['pending_count'],0)

if __name__=='__main__':unittest.main()
