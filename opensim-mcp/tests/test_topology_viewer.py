from pathlib import Path
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.topology import validate_operations
from opensim_mcp.viewer import geometry,mesh_data

@pytest.mark.parametrize('operations',[
    [dict(op='execute',code='arbitrary')],
    [dict(op='remove_component',component_path='/bodyset/../secret')],
    [dict(op='add_joint',name='x',joint_type='UnknownJoint',parent_frame='/ground',child_body='x')],
    [dict(op='remove_component',component_path='/bodyset/x',code='unexpected')],
])
def test_topology_rejects_unknown_commands_paths_and_fields(operations):
    with pytest.raises(InputError):validate_operations(operations)

def test_visual_mesh_model_cannot_grant_access_outside_allowed_roots(tmp_path):
    inputs=tmp_path/'inputs';inputs.mkdir();(tmp_path/'secret.obj').write_text('secret')
    model=inputs/'model.osim';model.write_text('<OpenSimDocument><Model name="test"><BodySet><objects><Body name="b"><attached_geometry><Mesh name="m"><mesh_file>../secret.obj</mesh_file></Mesh></attached_geometry></Body></objects></BodySet></Model></OpenSimDocument>')
    c=Settings((inputs,),tmp_path/'results',tmp_path/'scratch',None)
    records,warnings=geometry(c,str(model),None,1.)
    assert not records and warnings and str(tmp_path) not in warnings[0]

def test_vtp_external_piece_rejected_before_native_reader(tmp_path):
    (tmp_path/'scratch').mkdir();p=tmp_path/'external.vtp';p.write_text('<VTKFile type="PolyData"><PolyData><Piece Source="secret.vtp"/></PolyData></VTKFile>')
    c=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    with pytest.raises(InputError,match='self-contained'):mesh_data(c,[dict(type='mesh',source_path=str(p),frame='/ground',name='x',scale=[1.,1.,1.],color=[.5,.5,.5])])

def test_vtk_binary_vtp_and_stl_meshes_preserve_known_cube_extent(tmp_path):
    from vtkmodules.vtkFiltersSources import vtkCubeSource
    from vtkmodules.vtkIOXML import vtkXMLPolyDataWriter
    from vtkmodules.vtkIOGeometry import vtkSTLWriter
    (tmp_path/'scratch').mkdir();cube=vtkCubeSource();cube.SetXLength(.2);cube.SetYLength(.4);cube.SetZLength(.6);cube.Update()
    vtp=tmp_path/'cube.vtp';writer=vtkXMLPolyDataWriter();writer.SetFileName(str(vtp));writer.SetInputConnection(cube.GetOutputPort());writer.SetDataModeToAppended();writer.EncodeAppendedDataOn();assert writer.Write()
    stl=tmp_path/'cube.stl';writer=vtkSTLWriter();writer.SetFileName(str(stl));writer.SetInputConnection(cube.GetOutputPort());writer.SetFileTypeToBinary();assert writer.Write()
    c=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    records=[dict(type='mesh',source_path=str(p),frame='/ground',name=p.stem,scale=[1.,1.,1.],color=[.5,.5,.5]) for p in (vtp,stl)]
    meshes,hashes=mesh_data(c,records);assert len(meshes)==2 and len(hashes)==2
    for m in meshes:
        assert len(m['triangles'])==12
        assert abs(max(v[2] for v in m['vertices'])-min(v[2] for v in m['vertices'])-.6)<1e-6
