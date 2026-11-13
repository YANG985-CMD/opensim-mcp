"""Failure containment: reject late invalid input, restore on native failure."""
import os,tempfile,types,unittest
from pathlib import Path
from swlocal.cad import Failure
from swlocal.pose_update import PoseUpdateTools


class Harness(PoseUpdateTools):
    def __init__(self,scratch):
        self.scratch=Path(scratch);self.sw=types.SimpleNamespace(GetProcessID=lambda:123)
        self.binding=types.SimpleNamespace(cast=lambda obj,interface:obj);self.calls=[];self.fail_part=False
        self.angle=types.SimpleNamespace(SystemValue=1.);self.length=types.SimpleNamespace(SystemValue=.26)
        def model(path):return types.SimpleNamespace(ActiveView=types.SimpleNamespace(EnableGraphicsUpdate=True),GetPathName=path,GraphicsRedraw2=lambda:None,ForceRebuild3=lambda top:True)
        self.asm=model('assembly.SLDASM');self.part=model('muscle.SLDPRT');self.part.Parameter=lambda name:self.length
        self.before={'state':'a0','path':'assembly.SLDASM','components':[{'name':'one','path':'muscle.SLDPRT','transform':[1.]*16}],
                     'mates':[{'name':'hip','mate_type':6,'suppressed':False,'dimension_driven_state':2,'is_limit':True,'minimum':69,'maximum':113}]}
    def _edit(self,doc,state,kind):return (self.asm,self.before) if doc=='asm' else (self.part,{'path':'muscle.SLDPRT','state':'p0'})
    def _mate_objects_for_snapshot(self,*args):return {'hip':(None,types.SimpleNamespace(DisplayDimension=types.SimpleNamespace(GetDimension2=lambda i:self.angle)))}
    def _features(self,*args):return [{'dimensions':[{'name':'length'}]}]
    def _activate(self,doc):pass
    def _finish(self,doc):return dict(self.before)
    def _verify_rigid_connections(self,*args):pass
    def set_mate_positions(self,*args):self.calls.append('pose');self.angle.SystemValue=1.5
    def set_dimensions(self,*args):
        self.calls.append('part');self.length.SystemValue=.20
        if self.fail_part:raise RuntimeError('native part rebuild failed')
        return {'document_id':'part','state':'p1'}
    def request(self,bad=False):
        return self.set_assembly_pose('asm','a0',[{'mate_name':'hip','value':90}],[{'document_id':'part','state':'p0','dimensions':[{'dimension_name':'missing' if bad else 'length','value_si':.20}]}])


class PoseTests(unittest.TestCase):
    def scratch(self):
        root=Path(os.environ.get('SWLOCAL_TEMP',r'E:\simulink\_codex_tmp\solidworks_test_runtime'));root.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)
    def test_late_invalid_part_request_does_not_move_assembly(self):
        with self.scratch() as p:
            h=Harness(p)
            with self.assertRaises(Failure):h.request(bad=True)
            self.assertEqual(h.calls,[]);self.assertEqual(h.angle.SystemValue,1.);self.assertTrue(h.asm.ActiveView.EnableGraphicsUpdate)
    def test_native_failure_restores_captured_dimensions_and_display(self):
        with self.scratch() as p:
            h=Harness(p);h.fail_part=True
            with self.assertRaises(Failure) as caught:h.request()
            self.assertTrue(caught.exception.payload['restored_captured_parameters']);self.assertFalse(caught.exception.payload['edit_may_be_partial'])
            self.assertEqual(h.angle.SystemValue,1.);self.assertEqual(h.length.SystemValue,.26);self.assertTrue(h.asm.ActiveView.EnableGraphicsUpdate);self.assertTrue(h.part.ActiveView.EnableGraphicsUpdate)
            self.assertFalse((Path(p)/'pose_display_lease.json').exists())
    def test_success_returns_complete_update_and_restores_display(self):
        with self.scratch() as p:
            h=Harness(p);result=h.request();self.assertTrue(result['complete_pose_update']);self.assertEqual(h.length.SystemValue,.20)
            self.assertTrue(h.asm.ActiveView.EnableGraphicsUpdate);self.assertFalse((Path(p)/'pose_display_lease.json').exists())
