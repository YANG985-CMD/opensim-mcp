"""Native-like strict limits must accept displayed endpoints without overrun."""
import types
import unittest
from swlocal.cad import Failure
from swlocal.mechanisms import MechanismTools


class StrictNativeDimension:
    def __init__(self,maximum):
        self.maximum=maximum*.001;self.value=.032;self.writes=[]
    @property
    def SystemValue(self):return self.value
    @SystemValue.setter
    def SystemValue(self,value):
        self.writes.append(value)
        # Reproduce the observed native behavior: silently retain old value
        # when even an IEEE rounding increment exceeds the stored maximum.
        if .032<=value<=self.maximum:self.value=value


class Harness(MechanismTools):
    def __init__(self):
        self.maximum=175.99999999999997;self.dim=StrictNativeDimension(self.maximum)
    def row(self):
        return dict(name='slide',mate_type=5,suppressed=False,
            dimension_driven_state=2,is_limit=True,minimum=32.,
            maximum=self.maximum,value=self.dim.SystemValue*1000,unit='mm')
    def _edit(self,*args):return object(),dict(mates=[self.row()],components=[])
    def _mate_objects_for_snapshot(self,*args):
        return {'slide':(None,types.SimpleNamespace(DisplayDimension=types.SimpleNamespace(GetDimension2=lambda i:self.dim)))}
    def _finish(self,*args):return dict(mates=[self.row()],components=[])
    def _verify_rigid_connections(self,*args):pass
    def _assembly_status_for_snapshot(self,*args):return dict(native_mate_error_count=0,invalid_components=[],components=[])


class LimitRoundoffTests(unittest.TestCase):
    def test_single_displayed_endpoint_uses_stored_native_bound(self):
        h=Harness();r=h.set_mate_position('d','s','slide',176.)
        self.assertEqual(h.dim.SystemValue,h.maximum*.001)
        self.assertAlmostEqual(r['driven_mate']['value'],176.,places=10)
        self.assertEqual(r['driven_mate']['maximum'],h.maximum)
    def test_batch_displayed_endpoint_uses_stored_native_bound(self):
        h=Harness();r=h.set_mate_positions('d','s',[dict(mate_name='slide',value=176.)])
        self.assertEqual(h.dim.SystemValue,h.maximum*.001)
        self.assertEqual(r['driven_mates'][0]['maximum'],h.maximum)
    def test_genuine_overrun_is_rejected_before_any_write(self):
        for batch in [False,True]:
            with self.subTest(batch=batch):
                h=Harness()
                with self.assertRaises(Failure):
                    if batch:h.set_mate_positions('d','s',[dict(mate_name='slide',value=176.001)])
                    else:h.set_mate_position('d','s','slide',176.001)
                self.assertEqual(h.dim.writes,[])
    def test_late_invalid_batch_row_cannot_write_an_earlier_valid_row(self):
        h=Harness()
        with self.assertRaises(Failure):h.set_mate_positions('d','s',[dict(mate_name='slide',value=176.),dict(mate_name='missing',value=10.)])
        self.assertEqual(h.dim.writes,[])

if __name__=='__main__':unittest.main()
