"""Opt-in real human pipeline and cancellation/resume checks. No participant files redistributed."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import time
from opensim_mcp.core import Settings
from opensim_mcp.jobs import JobManager
from opensim_mcp.pipeline import get_run
from opensim_mcp.projects import create_project
from opensim_mcp.process_tree import process_alive
from smoke_projects import wait


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--resources',type=Path);parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    cfg=Settings.from_env();examples=Path(__file__).resolve().parents[1]/'examples'
    if args.resources:cfg=replace(cfg,allowed_roots=(*cfg.allowed_roots,args.resources.resolve()))
    manager=JobManager(cfg);evidence={}
    try:
        moco=json.loads((examples/'moco_problem.json').read_text())
        moco.update(model_path='${inputs.model}',mesh_intervals=200,max_iterations=2000,refine_mesh=True)
        project={'schema_version':1,'name':'Native cancel and resume','inputs':{'model':{'path':str(examples/'moco_slider.osim'),'kind':'model'}},
                 'stages':[{'id':'scale','workflow':'scale','parameters':{'model_path':'${inputs.model}','subject_mass_kg':2.,'body_scales':{'block':[1.,1.,1.]}}},
                           {'id':'long','workflow':'moco','parameters':moco}]}
        path=create_project(cfg,project)['project_path'];job=manager.submit('pipeline',{'project_path':path},600)['job_id']
        deadline=time.monotonic()+60;pid=None
        while time.monotonic()<deadline:
            status=manager.get(job)
            assert status['status'] not in {'failed','completed'},status
            progress=status.get('progress',{})
            try:prefix=get_run(cfg,job)['stages'].get('scale')
            except FileNotFoundError:prefix=None
            if prefix and progress.get('phase')=='native_running' and progress.get('native_pid'):
                pid=progress['native_pid'];break
            time.sleep(.02)
        assert pid,'Did not observe in-flight native Moco stage'
        cancelled=manager.cancel(job);assert cancelled['cancelled'] and cancelled['process_tree_stopped'],cancelled
        assert not process_alive(pid)
        partial=get_run(cfg,job);assert partial['status']=='cancelled' and set(partial['stages'])=={'scale'}
        project['stages'][1]['parameters'].update(mesh_intervals=10,refine_mesh=False)
        path=create_project(cfg,project)['project_path'];resumed=wait(manager,manager.submit('pipeline',{'project_path':path},600)['job_id'])
        assert resumed['status']=='completed' and resumed['result']['reused_stages']==1,resumed
        evidence['native_cancel_retains_only_complete_prefix_and_resumes']=True
        if args.resources:
            root=args.resources.resolve();forces=[]
            for name,body,prefix,torque in [('right','calcn_r','','ground_torque_'),('left','calcn_l','1_','1_ground_torque_')]:
                forces.append(dict(name=name,applied_to_body=body,force_identifier=prefix+'ground_force_v',point_identifier=prefix+'ground_force_p',torque_identifier=torque,force_expressed_in_body='ground',point_expressed_in_body='ground'))
            project={'schema_version':1,'name':'Official Gait2354 subject01 / measured force plates','inputs':{
                'model':{'path':str(root/'OutputReference/subject01_simbody.osim'),'kind':'model'},
                'coords':{'path':str(root/'OutputReference/subject01_walk1_ik.mot'),'kind':'coordinates'},
                'trc':{'path':str(root/'subject01_walk1.trc'),'kind':'markers','length_unit':'mm'},
                'grf':{'path':str(root/'subject01_walk1_grf.mot'),'kind':'loads','force_unit':'N','point_unit':'m','torque_unit':'Nm'}},
                'stages':[{'id':'fit','workflow':'ik_quality','parameters':{'model_path':'${inputs.model}','coordinates_path':'${inputs.coords}','marker_path':'${inputs.trc}','interpolation':'linear'}},
                          {'id':'id','workflow':'id','parameters':{'model_path':'${inputs.model}','coordinates_path':'${inputs.coords}','loads_path':'${inputs.grf}','external_forces':forces,'lowpass_cutoff_hz':6.}}],
                'residuals':[{'stage':'id','force_columns':['pelvis_t'+a+'_force' for a in 'xyz']}],
                'checks':[{'id':'illustrative_marker_limit','stage':'fit','metric':'marker_rms_m','limit':.03,'unit':'m'},
                          {'id':'illustrative_residual_limit','stage':'id','metric':'residual_force_rms_fraction_BW','limit':.05,'unit':'BW fraction'}],
                'plots':[{'stage':'id','output':'forces','columns':['pelvis_t'+a+'_force' for a in 'xyz'],'ylabel':'Pelvis residual force (N)'}]}
            path=create_project(cfg,project)['project_path'];actual=wait(manager,manager.submit('pipeline',{'project_path':path},600)['job_id'])
            assert actual['status']=='completed',actual
            record=get_run(cfg,actual['job_id']);rms=record['stages']['id']['metrics']['residual_force_rms_N']
            assert abs(rms-52.9397181486)<.001,rms
            assert record['quality_status']=='needs_review'
            assert Path(record['html_file']).is_file()  # Publication paths survive disposable job scratch cleanup.
            evidence['human']={'marker_rms_m':record['stages']['fit']['metrics']['marker_rms_m'], 'residual_rms_N':rms,
                'residual_rms_fraction_BW':record['stages']['id']['metrics']['residual_force_rms_fraction_BW'],
                'quality_status':record['quality_status'],'report':record['html_file'],'input_files_redistributed':False}
        evidence['passed']=True
    finally:manager.close()
    args.report.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))


if __name__=='__main__':main()
