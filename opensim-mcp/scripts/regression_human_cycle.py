"""One actual force-event gait cycle from separately installed Gait2354 data.

Explicit example-specific mass/axes/actuators; numerical thresholds do not
establish physiological validity. Saves stages so completed solves can resume.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from dataclasses import replace
from opensim_mcp.core import Settings,run_ik,trc_info,xml_model
from opensim_mcp.projects import digest
from opensim_mcp.trial_quality import gait_cycles,resample_coordinates,assess_mesh,audit_trajectory
from opensim_mcp.moco_model import prepare_moco_model
from opensim_mcp.rra import run_rra
from opensim_mcp.studies import run_convergence

def main():
    p=argparse.ArgumentParser();p.add_argument('--resources',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--resume',action='store_true');args=p.parse_args();root=args.resources.resolve();cfg=replace(Settings.from_env(),timeout=1800)
    cfg=replace(cfg,allowed_roots=(*cfg.allowed_roots,root));args.report.parent.mkdir(parents=True,exist_ok=True)
    model=root/'OutputReference/subject01_simbody.osim';markers=root/'subject01_walk1.trc';loads=root/'subject01_walk1_grf.mot'
    inputs={str(path.name):digest(path.read_bytes()) for path in (model,markers,loads)}
    events=gait_cycles(cfg,str(loads),'ground_force_vy',20.,10.,1.,.05,.05)
    if not events['cycles']:raise ValueError('No complete right-foot force-event cycle observed.')
    cycle=events['cycles'][0];start,end=cycle['start_time'],cycle['end_time'];times=trc_info(markers.read_bytes())['times']
    if times[0]>start or times[-1]<end:raise ValueError('Markers do not cover both measured heel-strike events.')
    checkpoint=args.report.with_suffix('.stages.json');stages={};stage_hashes={};script_sha=digest(Path(__file__).read_bytes())
    if args.resume and checkpoint.is_file():
        saved=json.loads(checkpoint.read_text(encoding='utf-8'))
        if saved['input_hashes']!=inputs or saved['cycle']!=cycle or saved.get('script_sha256')!=script_sha:raise ValueError('Resume input/event/script mismatch.')
        stages=saved['stages'];stage_hashes=saved['stage_output_hashes']
    def stage(name,operation):
        if name in stages:
            result=stages[name]
            # All serialized stage outputs are retained in the caller's results.
            for path,sha in stage_hashes[name].items():
                if not Path(path).is_file() or digest(Path(path).read_bytes())!=sha:raise ValueError('Resume output missing/changed; start a new report: '+str(path))
            return result
        result=operation();stages[name]=result
        files=set(result.get('files',[]))|{result[k] for k in ('model_file','motion_file','report_file') if k in result}
        stage_hashes[name]={str(path):digest(Path(path).read_bytes()) for path in files}
        checkpoint.write_text(json.dumps(dict(input_hashes=inputs,cycle=cycle,script_sha256=script_sha,stages=stages,stage_output_hashes=stage_hashes),indent=2),encoding='utf-8');print(name+' completed',flush=True);return result
    ik=stage('ik',lambda:run_ik(cfg,str(model),str(markers),max(t for t in times if t<=start),min(t for t in times if t>=end)))
    coordinates=ik['motion_file']
    resampled=stage('resampling',lambda:resample_coordinates(cfg,coordinates,60.))
    _,tree=xml_model(model.read_bytes());names=[n.get('name') for n in tree.iter('Coordinate')]
    residuals={'pelvis_tx':'FX','pelvis_ty':'FY','pelvis_tz':'FZ','pelvis_list':'MX','pelvis_rotation':'MY','pelvis_tilt':'MZ'}
    definitions=[dict(name=residuals.get(n,'reserve_'+n),coordinate=n,role='residual' if n in residuals else 'reserve',unit='N' if n in {'pelvis_tx','pelvis_ty','pelvis_tz'} else 'Nm',optimal_force=1.,min_control=-10000.,max_control=10000.) for n in names]
    forces=[dict(name=name,applied_to_body=body,force_identifier=prefix+'ground_force_v',point_identifier=prefix+'ground_force_p',torque_identifier=torque,force_expressed_in_body='ground',point_expressed_in_body='ground')
        for name,body,prefix,torque in [('right','calcn_r','','ground_torque_'),('left','calcn_l','1_','1_ground_torque_')]]
    rra=stage('rra',lambda:run_rra(cfg,str(model),resampled['motion_file'],definitions,{n:1. for n in names},str(loads),forces,start_time=start,end_time=end,adjust_com_body='torso'))
    prepared=stage('moco_model',lambda:prepare_moco_model(cfg,str(model),True,True,False,definitions))
    parameters=dict(model_path=prepared['model_file'],coordinates_path=coordinates,initial_time=start,final_time=end,loads_path=str(loads),external_forces=forces,
        ignore_tendon_compliance=True,max_iterations=1000,convergence_tolerance=1e-3,constraint_tolerance=1e-4)
    study=stage('moco_mesh',lambda:run_convergence(cfg,'moco_inverse',parameters,[.04,.02]))
    comparison=study['comparisons'][-1]
    state_limits={n:.05 if n.endswith('/activation') else .1 if n.endswith('/speed') else .02 for n in comparison['states']}
    control_limits={n:.05 if n in {'/forceset/'+key for key in prepared['quality']['muscles_after']} else 5. for n in comparison['controls']}
    quality=assess_mesh(cfg,study['report_file'],state_limits,control_limits)
    final=study['runs'][-1]['result'];files={Path(f).name:f for f in final['files']}
    audit=stage('audit',lambda:audit_trajectory(cfg,prepared['model_file'],coordinates,files['states.sto'],files['controls.sto'],str(loads),forces,ignore_tendon_compliance=True))
    result=dict(executed=True,passed_native_execution=True,cycle=cycle,events=events,input_hashes=inputs,inputs_redistributed=False,stages=stages,
        complete_named_trajectory_assessment=quality,quality_status=quality['status'],physiological_validation=False,
        scope='One observed same-foot onset-to-onset cycle; raw marker IK for Moco, explicit 60 Hz interpolation for RRA filtering, DGF/tendon change and explicit reserves. Native success is separate from all-column numerical quality and physiological interpretation.')
    if inputs!={path.name:digest(path.read_bytes()) for path in (model,markers,loads)}:raise ValueError('Original human inputs changed.')
    args.report.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(executed=True,cycle_s=[start,end],quality_status=quality['status'],state_columns=len(state_limits),control_columns=len(control_limits))))

if __name__=='__main__':main()
