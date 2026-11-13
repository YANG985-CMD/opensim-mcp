import types
import unittest
from swlocal.cad import CAD,Failure
from swlocal.geometry import validate_rigid_transform


class AssemblyBuildTests(unittest.TestCase):
    def test_transform_rejects_reflections_scale_and_bad_axes(self):
        identity=[1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0]
        self.assertEqual(validate_rigid_transform(identity),identity)
        for index,value in [(0,-1),(1,.1),(12,2),(9,6),(15,1)]:
            t=identity.copy();t[index]=value
            with self.assertRaises(ValueError):validate_rigid_transform(t)

    def test_geometry_cache_is_guarded_by_native_identity_stamp_configuration_and_fresh_material(self):
        c=object.__new__(CAD);c._part_fingerprints={};state={'stamp':1,'material':'aluminium','geometry':1,'identity':object()};reads=[]
        model=types.SimpleNamespace(GetPathName=lambda:'part.SLDPRT',GetTitle=lambda:'part',GetUpdateStamp=lambda:state['stamp'],
          _oleobj_=types.SimpleNamespace(QueryInterface=lambda iid:state['identity']))
        c._assembly_part_summary=lambda m:reads.append(state['geometry']) or {'geometry':state['geometry']}
        c._material_identity=lambda m,conf:{'material':state['material']}
        a=c._part_fingerprint(model,'a','a');self.assertEqual(a,c._part_fingerprint(model,'a','a'));self.assertEqual(len(reads),1)
        state['material']='steel';b=c._part_fingerprint(model,'a','a');self.assertNotEqual(a,b);self.assertEqual(len(reads),1)
        state['stamp']=2;state['geometry']=2;d=c._part_fingerprint(model,'a','a');self.assertNotEqual(b,d);self.assertEqual(len(reads),2)
        c._part_fingerprint(model,'b','b');self.assertEqual(len(reads),3)
        state['identity']=object();state['geometry']=3;e=c._part_fingerprint(model,'a','a');self.assertNotEqual(d,e);self.assertEqual(len(reads),4)

    def test_geometry_change_during_inspection_is_reported(self):
        c=object.__new__(CAD);c._part_fingerprints={};state={'stamp':1}
        model=types.SimpleNamespace(GetPathName=lambda:'p',GetTitle=lambda:'p',GetUpdateStamp=lambda:state['stamp'],
          _oleobj_=types.SimpleNamespace(QueryInterface=lambda iid:'native-identity'))
        def geometry(m):state['stamp']=2;return {'body_count':1}
        c._assembly_part_summary=geometry;c._material_identity=lambda *args:{}
        with self.assertRaises(Failure) as error:c._part_fingerprint(model,'a','a')
        self.assertEqual(error.exception.payload['code'],'INSPECTION_CHANGED_STATE')

    def test_combined_pose_checks_all_limits_before_writing_any_dimension(self):
        c=object.__new__(CAD)
        rows=[{'name':name,'mate_type':5,'suppressed':False,'dimension_driven_state':2,'is_limit':True,'minimum':10,'maximum':100} for name in ('a','b')]
        c._edit=lambda *args:(object(),{'mates':rows});c._mate_objects_for_snapshot=lambda *args:{}
        with self.assertRaises(Failure) as error:c.set_mate_positions('doc','state',[{'mate_name':'a','value':20},{'mate_name':'b','value':101}])
        self.assertEqual(error.exception.payload['code'],'MATE_LIMIT')
        self.assertFalse(error.exception.payload['edit_may_be_partial'])

    def test_motion_scan_rejects_a_later_invalid_pose_before_any_move(self):
        c=object.__new__(CAD);row={'name':'hip','mate_type':6,'suppressed':False,'dimension_driven_state':2,'is_limit':True,'minimum':69,'maximum':113}
        c._edit=lambda *args:(object(),{'mates':[row]})
        c.set_mate_positions=lambda *args:self.fail('No move should be issued')
        with self.assertRaises(Failure) as error:c.scan_motion('doc','state',[[{'mate_name':'hip','value':90}],[{'mate_name':'hip','value':114}]])
        self.assertEqual(error.exception.payload['code'],'MATE_LIMIT')

    def test_prismatic_template_rejects_parallel_guide_planes_before_any_mate(self):
        c=object.__new__(CAD);model=object();c._edit=lambda *args:(model,{})
        c._doc=lambda *args:{'model':model};c._features=lambda *args:[]
        c._resolve_reference=lambda m,r:{'kind':'plane','geometry':{'normal':[1,0,0]}}
        c.add_mate=lambda *args,**kw:self.fail('Invalid guide must not create a mate')
        pair={'a':{'component':'a','plane_name':'x'},'b':{'component':'b','plane_name':'x'}}
        with self.assertRaises(Failure) as error:c.create_joint('d','s','prismatic','guide',plane_pairs=[pair,pair])
        self.assertEqual(error.exception.payload['code'],'ARGUMENT')
        self.assertFalse(error.exception.payload['edit_may_be_partial'])

    def test_joint_checks_all_proposed_names_before_first_native_edit(self):
        c=object.__new__(CAD);model=object();c._edit=lambda *args:(model,{})
        c._doc=lambda *args:{'model':model};c._features=lambda *args:[{'name':'hip_guide_0'}]
        c.add_mate=lambda *args,**kw:self.fail('Duplicate later name must be caught before first mate')
        pair={'a':{'component':'a','plane_name':'x'},'b':{'component':'b','plane_name':'x'}}
        with self.assertRaises(Failure) as error:c.create_joint('d','s','revolute','hip',axis_a={'component':'a','face_id':0},axis_b={'component':'b','face_id':0},plane_pairs=[pair])
        self.assertEqual(error.exception.payload['code'],'FEATURE_NAME')
        self.assertFalse(error.exception.payload['edit_may_be_partial'])

if __name__=='__main__':unittest.main()
