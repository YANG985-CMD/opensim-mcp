"""Independent analytic mass distributions, units, frame and inertia failures."""
import copy
import math
import random
import pytest
from opensim_mcp.core import InputError,Settings
from opensim_mcp.mass_properties import convert_mass_properties,validate_central_inertia,_principal_moments
from opensim_mcp.wearable import assemble,validate_links

IDENTITY=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]


def source():
    return dict(mass=2000.,mass_unit='g',center_of_mass=[10.,20.,30.],length_unit='mm',
                inertia=[.02,.025,.03,.001,.002,.003],inertia_unit='kg_m2',
                inertia_reference='center_of_mass',inertia_convention='tensor_entries',
                source_frame='CAD part',source_description='Original analytic fixture; no hardware claim')


def transform():
    return dict(target_frame='device body',rotation_source_to_target=copy.deepcopy(IDENTITY),
                translation_source_origin_in_target_m=[0.,0.,0.])


def assert_close(a,b,abs_tol=1e-12):
    assert a==pytest.approx(b,abs=abs_tol,rel=1e-10)


def test_unit_scales_are_independent_and_no_unit_is_inferred():
    a=source();expected=convert_mass_properties(a,transform())['body_parameters']
    for units,factor in [('kg_m2',1.),('kg_mm2',1e-6),('g_mm2',1e-9),('g_cm2',1e-7)]:
        b=copy.deepcopy(a);b['inertia_unit']=units;b['inertia']=[v/factor for v in a['inertia']]
        measured=convert_mass_properties(b,transform())
        assert_close(measured['body_parameters']['inertia_kg_m2'],expected['inertia_kg_m2'])
        assert_close(measured['body_parameters']['mass_center_m'],[.01,.02,.03])
        assert measured['body_parameters']['mass_kg']==2
    for key in ('mass_unit','length_unit','inertia_unit','inertia_reference','inertia_convention','source_description'):
        b=copy.deepcopy(a);del b[key]
        with pytest.raises(InputError):convert_mass_properties(b,transform())


def test_nondiagonal_tensor_rotates_with_two_sided_rotation_and_com_translates():
    p=source();t=transform();t['rotation_source_to_target']=[[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]]
    t['translation_source_origin_in_target_m']=[.1,.2,.3]
    r=convert_mass_properties(p,t)
    assert_close(r['body_parameters']['inertia_kg_m2'],[.025,.02,.03,-.001,-.003,.002])
    assert_close(r['body_parameters']['mass_center_m'],[.08,.21,.33])
    assert r['quality']['principal_moment_invariance_error_kg_m2']<1e-14
    # The translation must not be added to the central inertia a second time.
    t['translation_source_origin_in_target_m']=[1.,2.,3.]
    assert_close(convert_mass_properties(p,t)['body_parameters']['inertia_kg_m2'],r['body_parameters']['inertia_kg_m2'])


def test_positive_products_and_row_major_source_origin_inertia_recover_central_tensor():
    p=source();c=[.01,.02,.03];mass=2.
    central=[[.02,.001,.002],[.001,.025,.003],[.002,.003,.03]]
    origin=[[central[i][j]+mass*((sum(v*v for v in c) if i==j else 0)-c[i]*c[j]) for j in range(3)] for i in range(3)]
    p.update(inertia_reference='source_origin',inertia_convention='positive_products',inertia_unit='g_mm2',
             inertia=[origin[i][j]*(1 if i==j else -1)*1e9 for i in range(3) for j in range(3)])
    r=convert_mass_properties(p,transform())
    assert_close(r['body_parameters']['inertia_kg_m2'],[.02,.025,.03,.001,.002,.003])
    assert r['conversion']['parallel_axis_subtracted'] and r['conversion']['off_diagonal_sign_changed']


def test_independent_point_cloud_moments_survive_rotation_shift_and_unit_conversion():
    # Direct point-mass sums are independent of the conversion algorithm.
    rng=random.Random(1901)
    for _ in range(15):
        points=[[rng.uniform(-.2,.2) for _ in range(3)] for _ in range(9)]
        masses=[rng.uniform(.1,.5) for _ in points];mass=sum(masses)
        c=[sum(m*p[i] for m,p in zip(masses,points))/mass for i in range(3)]
        origin=[[sum(m*((sum(x*x for x in p) if i==j else 0)-p[i]*p[j]) for m,p in zip(masses,points)) for j in range(3)] for i in range(3)]
        angle=rng.uniform(-3,3);cs,sn=math.cos(angle),math.sin(angle);r=[[cs,-sn,0.],[sn,cs,0.],[0.,0.,1.]];t=[.4,-.2,.7]
        moved=[[sum(r[i][k]*p[k] for k in range(3))+t[i] for i in range(3)] for p in points]
        cm=[sum(m*p[i] for m,p in zip(masses,moved))/mass for i in range(3)]
        deltas=[[p[i]-cm[i] for i in range(3)] for p in moved]
        expected=[[sum(m*((sum(x*x for x in p) if i==j else 0)-p[i]*p[j]) for m,p in zip(masses,deltas)) for j in range(3)] for i in range(3)]
        p=source();p.update(mass=mass*1000,center_of_mass=[v*1000 for v in c],inertia_unit='kg_mm2',
                           inertia_reference='source_origin',inertia=[v*1e6 for row in origin for v in row])
        tf=transform();tf.update(rotation_source_to_target=r,translation_source_origin_in_target_m=t)
        out=convert_mass_properties(p,tf)
        assert_close(out['body_parameters']['mass_center_m'],cm)
        for a,b in zip(out['inertia_matrix_kg_m2'],expected):assert_close(a,b)


@pytest.mark.parametrize('matrix',[
    [1.,1.,3.,0.,0.,0.], # SPD alone is insufficient: impossible principal triangle
    [1.,1.,1.,2.,0.,0.], # positive diagonal but a negative principal moment
    [-1.,1.,1.,0.,0.,0.],
    [0.,0.,0.,0.,0.,0.],
    [0.,1.,1.,0.,0.,0.], # degenerate line profile is explicit, not silently repaired
    [1.,2.,float('nan'),0.,0.,0.],
    [True,1.,1.,0.,0.,0.],
])
def test_impossible_or_unsupported_central_inertia_is_rejected(matrix):
    with pytest.raises(InputError):validate_central_inertia(matrix)


@pytest.mark.parametrize('rotation',[
    [[-1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],
    [[2.,0.,0.],[0.,2.,0.],[0.,0.,2.]],
    [[1.,.01,0.],[0.,1.,0.],[0.,0.,1.]],
    [[1.,0.,0.],[0.,1.,0.]],
])
def test_reflection_scaling_shear_or_bad_axes_are_rejected(rotation):
    t=transform();t['rotation_source_to_target']=rotation
    with pytest.raises(InputError):convert_mass_properties(source(),t)


def test_nonsymmetric_row_major_inertia_is_not_silently_repaired():
    p=source();p['inertia']=[.02,.001,.002,.003,.025,.003,.002,.003,.03]
    with pytest.raises(InputError,match='symmetric'):convert_mass_properties(p,transform())


def test_inconsistent_origin_inertia_is_rejected_after_parallel_axis_subtraction():
    p=source();p.update(center_of_mass=[1000.,2000.,3000.],inertia_reference='source_origin')
    with pytest.raises(InputError,match='positive definite'):convert_mass_properties(p,transform())


def test_frame_labels_and_explicit_units_are_required_and_preserved():
    p=source();t=transform();before=copy.deepcopy((p,t))
    r=convert_mass_properties(p,t)
    assert (p,t)==before
    assert r['provenance']['source_description']==p['source_description']
    assert any('mesh vertices' in w for w in r['warnings'])
    for changes in ({'mass':True},{'mass_unit':'guess'},{'inertia_convention':None},{'inertia_reference':'unknown'},{'source_description':''}):
        with pytest.raises(InputError):convert_mass_properties(dict(p,**changes),t)
    t['target_frame']=p['source_frame'];t['translation_source_origin_in_target_m']=[1,0,0]
    with pytest.raises(InputError,match='Identical'):convert_mass_properties(p,t)


def test_tiny_valid_inertia_uses_relative_not_an_absolute_unit_threshold():
    for factor in (1e-18,1.,1e12):
        r=validate_central_inertia([factor,2*factor,2.5*factor,0.,0.,0.])
        assert_close([v/factor for v in r['principal_moments_kg_m2']],[1,2,2.5])


def test_existing_assembly_rejects_invalid_later_inertia_before_any_native_execution(tmp_path,monkeypatch):
    model=tmp_path/'model.osim';model.write_text('<OpenSimDocument><Model name="test"/></OpenSimDocument>')
    mesh=tmp_path/'cuff.stl';mesh.write_bytes(b'Only validation is reached')
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'temp',None)
    valid=dict(name='first',parent_frame='/ground',mesh_path=str(mesh),mesh_units='m',mass_kg=.2,
               mass_center_m=[0.,0.,0.],inertia_kg_m2=[.001,.001,.001,0.,0.,0.],joint_type='WeldJoint')
    invalid=dict(valid,name='second',inertia_kg_m2=[1.,1.,3.,0.,0.,0.])
    monkeypatch.setattr('opensim_mcp.wearable.run_native',lambda *a,**k:pytest.fail('Invalid input reached native execution'))
    with pytest.raises(InputError,match='triangle'):assemble(cfg,str(model),[valid,invalid])
    assert not cfg.results_root.exists()
    assert validate_links(cfg,[valid],True)[0]['mass_kg']==.2
