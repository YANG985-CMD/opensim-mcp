"""Regressions for ambiguous configuration context and native DOF enums."""
import threading
import types
import unittest
from swlocal.cad import CAD,Failure
from swlocal.geometry import relative_component_pose


class StateAndDofTests(unittest.TestCase):
    def bare(self):
        c=object.__new__(CAD);c.owner=threading.get_ident();c.generation='test';return c

    def test_native_availability_code_is_never_reported_as_two_dofs(self):
        c=self.bare()
        component=types.SimpleNamespace(GetConstrainedStatus=lambda:3,IsFixed=lambda:False,
          GetRemainingDOFs=lambda *args:(2,0,None,0,None,0,None,0,None,0,None,0,None))
        r=c._dof(component)
        self.assertIsNone(r['remaining_dof_count'])
        self.assertEqual(r['native_dof_return_code'],2)
        self.assertEqual(r['native_dof_availability'],'unavailable')

    def test_relative_lock_check_accepts_common_motion_but_rejects_a_left_behind_child(self):
        c=self.bare()
        identity=[1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0]
        child=identity.copy();child[9]=1
        parent_rotated=[0,1,0,-1,0,0,0,0,1,0,0,0,1,0,0,0]
        child_rotated=parent_rotated.copy();child_rotated[10]=1
        self.assertEqual(relative_component_pose(identity,child),relative_component_pose(parent_rotated,child_rotated))
        before={'components':[{'name':'a','transform':identity},{'name':'b','transform':child}],
          'mates':[{'name':'rigid','mate_type':16,'references':[{'component':'a'},{'component':'b'}]}]}
        after={'components':[{'name':'a','transform':parent_rotated},{'name':'b','transform':child_rotated}]}
        c._verify_rigid_connections(before,after)
        after['components'][1]['transform']=child
        with self.assertRaises(Failure) as error:c._verify_rigid_connections(before,after)
        self.assertEqual(error.exception.payload['code'],'MATE_GEOMETRY')
        self.assertTrue(error.exception.payload['edit_may_be_partial'])

    def test_configuration_change_invalidates_an_identical_geometry_snapshot(self):
        c=self.bare();configuration=types.SimpleNamespace(Name='configuration_a')
        model=types.SimpleNamespace(GetTitle=lambda:'test_part',GetPathName=lambda:'',GetType=lambda:1,
          ConfigurationManager=types.SimpleNamespace(ActiveConfiguration=configuration))
        c.documents={'test':{'model':model,'editable':True}}
        c._part_geometry=lambda model:{'body_count':1,'volume_mm3':1000}
        c._material_identity=lambda model:{'assigned':False}
        c._features=lambda model:[]
        old=c.snapshot('test');configuration.Name='configuration_b'
        current=c.snapshot('test')
        self.assertNotEqual(old['state'],current['state'])
        with self.assertRaises(Failure) as error:c._edit('test',old['state'],1)
        self.assertEqual(error.exception.payload['code'],'STALE_STATE')
        self.assertFalse(error.exception.payload['edit_may_be_partial'])

    def test_component_geometry_context_rejects_a_different_loaded_configuration(self):
        c=self.bare();child=types.SimpleNamespace(ConfigurationManager=types.SimpleNamespace(ActiveConfiguration=types.SimpleNamespace(Name='loaded_a')))
        component=types.SimpleNamespace(Name2='link-1',GetModelDoc2=lambda:child,ReferencedConfiguration='referenced_b')
        model=types.SimpleNamespace(GetComponents=lambda top:[component])
        with self.assertRaises(Failure) as error:c._component(model,'link-1')
        self.assertEqual(error.exception.payload['code'],'CONFIGURATION_SCOPE')
        self.assertFalse(error.exception.payload['edit_may_be_partial'])

if __name__=='__main__':unittest.main()
