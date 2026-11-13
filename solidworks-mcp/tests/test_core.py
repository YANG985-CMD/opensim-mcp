import os
import math
import sys
import tempfile
import unittest
from pathlib import Path
from swlocal.geometry import coaxial_error,direction_from_bounds,polygon_area,incremental_transform,validate_mate_values
from swlocal.broker import Broker,CadError
from swlocal.errors import load_error


class GeometryTests(unittest.TestCase):
    def test_transform_uses_world_rotation_and_pivot(self):
        t=[1,0,0,0,1,0,0,0,1,.1,0,0,1,0,0,0]
        r=incremental_transform(t,[0,0,10],[0,0,1],90,[0,0,0])
        for actual,expected in zip(r[:12],[0,1,0,-1,0,0,0,0,1,0,.1,.01]):self.assertAlmostEqual(actual,expected,places=10)
        pinned=incremental_transform(t,None,[0,0,1],90,[100,0,0])
        self.assertEqual(pinned[9:12],[.1,0,0])
        for kw in [{'axis_world':[0,0,0]},{'angle_deg':float('nan')},{'translation_mm':[1,2]},{'angle_deg':30}]:
            with self.assertRaises(ValueError):incremental_transform(t,**kw)
    def test_limit_units_and_invalid_bounds(self):
        s=validate_mate_values('limit_angle',90,69,113,'closest',False,False,'hip_limit')
        self.assertAlmostEqual(s['angle'],math.pi/2)
        self.assertAlmostEqual(s['angle_min'],math.radians(69))
        self.assertAlmostEqual(s['angle_max'],math.radians(113))
        s=validate_mate_values('limit_distance',80,10,150,'aligned',False,False,'slide')
        self.assertEqual((s['distance'],s['distance_min'],s['distance_max']),(.08,.01,.15))
        for args in [('limit_angle',0,-21,23),('limit_distance',0,20,10),('limit_distance',50,0,40),('distance',10,0,20),('angle',float('nan'),0,0)]:
            with self.assertRaises(ValueError):validate_mate_values(*args,'closest',False,False,'')
    def test_native_load_failure_is_not_accepted_or_retried(self):
        for native,code in [(262144,'LOW_RESOURCES'),(1048576,'OPEN_INTERRUPTED'),(65536,'DOCUMENT_NAME_COLLISION'),(2097152,'FILE_REPAIR_REQUIRED')]:
            error=load_error(native)
            self.assertEqual(error['code'],code)
            self.assertFalse(error['retry_automatically'])
            self.assertFalse(error['edit_may_be_partial'])
        self.assertEqual(load_error(262144|1048576)['code'],'LOW_RESOURCES')
    def test_concentric_axes_ignore_axial_slide_and_reversed_direction(self):
        result=coaxial_error([2,3,0],[0,0,1],[2,3,50],[0,0,-1])
        self.assertEqual(result,{'axis_angle_deg':0.,'axis_offset_mm':0.})
        shifted=coaxial_error([0,0,0],[0,0,1],[30,0,10],[0,0,1])
        self.assertEqual(shifted['axis_offset_mm'],30.)
        angled=coaxial_error([0,0,0],[0,0,1],[0,0,0],[1,0,0])
        self.assertEqual(angled['axis_angle_deg'],90.)
    def test_cut_material_sides(self):
        self.assertEqual(direction_from_bounds([-1,-1,0,1,1,8],[0,0,0],[0,0,1]),(True,False))
        self.assertEqual(direction_from_bounds([-1,-1,-8,1,1,0],[0,0,0],[0,0,1]),(False,False))
        self.assertEqual(direction_from_bounds([-1,-1,-4,1,1,4],[0,0,0],[0,0,1]),(False,True))
    def test_polygon_rejects_crossed_and_degenerate_profiles(self):
        self.assertEqual(polygon_area([(0,0),(4,0),(0,3)])[1],6)
        for p in [[(0,0),(2,2),(0,2),(2,0)],[(0,0),(1,0),(2,0)],[(0,0),(1,float('nan')),(1,2)]]:
            with self.assertRaises(ValueError): polygon_area(p)
    def test_worker_timeout_does_not_replay(self):
        scratch=Path(os.environ['SWLOCAL_TEMP'])
        scratch.mkdir(parents=True,exist_ok=True)
        script=scratch/'fake_worker.py'
        script.write_text('import sys,json,time\nfor line in sys.stdin:\n r=json.loads(line)\n if r["operation"]=="hang":time.sleep(30)\n print(json.dumps({"id":r["id"],"ok":True,"data":{"pid":__import__("os").getpid()}}),flush=True)\n',encoding='utf-8')
        broker=Broker([sys.executable,'-u',str(script)],timeout=.5)
        try:
            first=broker.request('read',{})['data']['pid']
            with self.assertRaises(CadError) as error: broker.request('hang',{},mutating=True)
            self.assertEqual(error.exception.payload['code'],'CAD_TIMEOUT')
            self.assertTrue(error.exception.payload['outcome_unknown'])
            self.assertFalse(error.exception.payload['retry_automatically'])
            second=broker.request('read',{})['data']['pid']
            self.assertNotEqual(first,second)
        finally: broker.close()

if __name__=='__main__': unittest.main()
