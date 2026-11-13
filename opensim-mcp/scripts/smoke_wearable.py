"""Native CAD fit, added inertia/ID and weld reaction on original fixtures."""
import argparse,json,math
from pathlib import Path
from opensim_mcp.core import Settings,read_motion
from opensim_mcp.wearable import assemble,prepare_motion
from opensim_mcp.analysis import run_analysis
from opensim_mcp.session import ApiSession
from opensim_mcp.viewer import export_animation
from opensim_mcp.structured import configure_actuators
from opensim_mcp.wearable_analysis import compare_id

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    cfg=Settings.from_env();examples=Path(__file__).resolve().parents[1]/'examples'
    link=dict(name='test_cuff',parent_frame='/bodyset/block',mesh_path=str(examples/'Geometry/block.obj'),mesh_units='m',
        mass_kg=.5,mass_center_m=[0.,0.,0.],inertia_kg_m2=[.001,.001,.001,0.,0.,0.],joint_type='WeldJoint',
        landmarks=dict(cad_points=[[0,0,0],[.1,0,0],[0,.1,0]],parent_points_m=[[0,.2,0],[.1,.2,0],[0,.3,0]]))
    result=assemble(cfg,str(examples/'slider.osim'),[link],True,max_landmark_error_m=1e-8)
    assert abs(result['quality']['added_device_mass_kg']-.5)<1e-10
    assert result['links'][0]['landmark_fit']['max_m']<1e-12
    assert abs(result['links'][0]['translation_m'][1]-.2)<1e-12
    inputs=cfg.results_root/'wearable-smoke-inputs';inputs.mkdir(exist_ok=True,parents=True)
    motion=inputs/'acceleration.mot';motion.write_text('Analytic inertial test\nversion=1\nnRows=41\nnColumns=2\ninDegrees=no\nendheader\ntime\tslider_tx\n'+'\n'.join(f'{i/40:.15g}\t{.5*(i/40)**2:.15g}' for i in range(41))+'\n',encoding='utf-8')
    adapted=prepare_motion(cfg,result['report_file'],str(motion))
    ids=[]
    for model in (str(examples/'slider.osim'),result['model_file']):
        analysis=run_analysis(cfg,'id',model,adapted['motion_file'],no_external_loads=True)
        table=read_motion(next(Path(f) for f in analysis['files'] if f.endswith('inverse_dynamics.sto')));index=table['columns'].index('slider_tx_force')
        ids.append(sum(row[index] for row in table['rows'][5:-5])/len(table['rows'][5:-5]))
    assert abs(ids[1]-ids[0]-.5)<1e-5,ids
    assist=inputs/'assist.sto';assist.write_text('Known ideal assistance\nversion=1\nnRows=41\nnColumns=2\ninDegrees=no\nendheader\ntime\tassist_N\n'+'\n'.join(f'{i/40:.15g}\t.25' for i in range(41))+'\n',encoding='utf-8')
    comparison=compare_id(cfg,str(examples/'slider.osim'),result['report_file'],adapted['motion_file'],no_external_loads=True,assistance_path=str(assist),assistance_mapping=[dict(coordinate='slider_tx',column='assist_N',unit='N')])
    assert abs(comparison['metrics']['slider_tx_force']['remaining_generalized_demand']['rms']-1.25)<1e-5
    driven=configure_actuators(cfg,result['model_file'],[dict(name='test_drive',coordinate='slider_tx',role='reserve',unit='N',optimal_force=1.,min_control=-10.,max_control=10.)])
    forces=inputs/'known_drive.sto';forces.write_text('Known dynamics-consistent drive\nversion=1\nnRows=41\nnColumns=2\ninDegrees=no\nendheader\ntime\ttest_drive\n'+'\n'.join(f'{i/40:.15g}\t1.5' for i in range(41))+'\n',encoding='utf-8')
    reaction=run_analysis(cfg,'joint_reaction',driven['model_file'],adapted['motion_file'],no_external_loads=True,joint_names=['test_cuff_mount'],on_body='child',in_frame='ground',forces_path=str(forces))
    reactions=read_motion(next(Path(f) for f in reaction['files'] if f.endswith('ReactionLoads.sto')))
    expected={name:(.5 if name.endswith('_fx') else 4.903325) for name in reactions['columns'] if name.endswith(('_fx','_fy'))}
    measured={name:sum(row[reactions['columns'].index(name)] for row in reactions['rows'][5:-5])/len(reactions['rows'][5:-5]) for name in expected}
    assert all(abs(measured[name]-value)<1e-5 for name,value in expected.items()),measured
    native=ApiSession(cfg)
    try:
        loaded=native.load(result['model_file']);assert loaded['counts']['bodies']==2
        viewer=export_animation(cfg,native,adapted['motion_file'],result['model_file'],max_frames=41)
        assert viewer['mesh_count']==1
    finally:native.close()
    # Separate rotational example checks explicit coupling and degree conversion.
    coupled=dict(link);coupled.pop('landmarks');coupled.update(parent_frame='/bodyset/block',joint_type='PinJoint',joint_location_in_child_m=[0.,0.,0.],joint_orientation_in_child_xyz_rad=[0.,0.,0.],coordinate={'name':'device_angle','range':[-3.,3.],'default_value':0.},coupling={'independent_coordinate':'angle','scale':1.,'offset':.1})
    coupled_model=assemble(cfg,str(examples/'moco_pin.osim'),[coupled],True)
    degree_motion=inputs/'degrees.mot';degree_motion.write_text('Coupling test\nversion=1\nnRows=2\nnColumns=2\ninDegrees=yes\nendheader\ntime\tangle\n0\t0\n1\t30\n',encoding='utf-8')
    mapped=prepare_motion(cfg,coupled_model['report_file'],str(degree_motion));table=read_motion(Path(mapped['motion_file']))
    assert abs(table['rows'][-1][table['columns'].index('device_angle')]-(30+math.degrees(.1)))<1e-10
    report=dict(passed=True,assembly=result,added_device_mass_kg=.5,baseline_id_N=ids[0],combined_id_N=ids[1],expected_added_inertial_force_N=.5,
        native_joint_reaction=reaction,analytic_joint_reaction_N=measured,matched_mass_and_assistance_comparison=comparison,coupled_pin_model=coupled_model,degree_coupling_verified=True,viewer=viewer,scope='Original rigid cuff + analytic slider/pin; force/torque units explicit, not a human fitting/strap/contact validation.')
    args.report.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,mass_kg=.5,id_delta_N=ids[1]-ids[0],viewer_meshes=viewer['mesh_count'])))
if __name__=='__main__':main()
