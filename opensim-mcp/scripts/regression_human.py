"""Opt-in regression on the official installed Gait2354 example and force plates.

Uses local public example resources; never redistributes the participant trial.
Run under env.ps1 with dedicated scratch/results. Optional legacy SDK comparison.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path

from opensim_mcp.analysis import run_analysis
from opensim_mcp.core import Settings,read_motion,run_ik,trc_info
from opensim_mcp.session import ApiSession
from opensim_mcp.workflows import assess_ik_quality


@contextmanager
def settings_env(values):
    old={key:os.environ.get(key) for key in values}
    os.environ.update(values)
    try:yield
    finally:
        for key,value in old.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def compare_tables(a,b,tolerance):
    first,second=read_motion(Path(a)),read_motion(Path(b))
    assert set(first['columns'])==set(second['columns'])
    assert len(first['rows'])==len(second['rows'])
    maximum=0
    for ra,rb in zip(first['rows'],second['rows']):
        assert abs(ra[0]-rb[0])<1e-5
        maximum=max(maximum,max(abs(ra[i]-rb[second['columns'].index(name)]) for i,name in enumerate(first['columns']) if i))
    assert maximum<tolerance,(maximum,tolerance)
    return {'max_absolute_force_or_moment_difference':maximum,'tolerance_N_or_Nm':tolerance,'rows':len(first['rows'])}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--resources',required=True,type=Path)
    parser.add_argument('--legacy-python',type=Path);parser.add_argument('--legacy-root',type=Path)
    parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    cfg=Settings.from_env();root=args.resources.resolve()
    cfg=replace(cfg,allowed_roots=(*cfg.allowed_roots,root))
    model=root/'OutputReference/subject01_simbody.osim';coordinates=root/'OutputReference/subject01_walk1_ik.mot'
    markers=root/'subject01_walk1.trc';plates=root/'subject01_walk1_grf.mot'
    inputs=[model,coordinates,markers,plates]
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    report={'dataset':'Official OpenSim Gait2354_Simbody / subject01 example; public demonstration trial',
            'input_hashes':before,'inputs_redistributed':False,'physiological_validation':False}
    api=ApiSession(cfg)
    try:
        status=api.load(str(model));saved=api.save();report['api46_model']={k:status[k] for k in ('opensim_version','counts','total_mass_kg')}
    finally:api.close()
    coords=read_motion(coordinates);start,end=coords['rows'][0][0],coords['rows'][-1][0]
    # Public sample force/point/torque identifiers from its installed ExternalLoads XML.
    forces=[]
    for name,body,prefix,torque in [('right','calcn_r','','ground_torque_'),('left','calcn_l','1_','1_ground_torque_')]:
        forces.append(dict(name=name,applied_to_body=body,force_identifier=prefix+'ground_force_v',
                           point_identifier=prefix+'ground_force_p',torque_identifier=torque,
                           force_expressed_in_body='ground',point_expressed_in_body='ground'))
    parameters=dict(model_path=str(model),coordinates_path=str(coordinates),loads_path=str(plates),
                    external_forces=forces,start_time=start,end_time=end,lowpass_cutoff_hz=6)
    result=run_analysis(cfg,'id',**parameters)
    id46=next(p for p in result['files'] if p.endswith('inverse_dynamics.sto'))
    table=read_motion(Path(id46));weight=status['total_mass_kg']*9.80665
    indexes=[table['columns'].index('pelvis_t'+axis+'_force') for axis in 'xyz']
    norms=[math.sqrt(sum(row[i]**2 for i in indexes)) for row in table['rows']]
    report['force_plate_id']={'rows':len(table['rows']),'time_range':result['time_range'],
        'pelvis_residual_force_rms_N':math.sqrt(sum(v*v for v in norms)/len(norms)),
        'pelvis_residual_force_peak_N':max(norms),'pelvis_residual_rms_fraction_body_weight':math.sqrt(sum(v*v for v in norms)/len(norms))/weight,
        'interpretation':'Residuals are measured and reported; no automatic physiological acceptance threshold.'}
    fit=assess_ik_quality(cfg,str(model),str(coordinates),str(markers),max_frames=200,interpolation='linear')
    report['reference_ik_marker_fit']=fit['quality']
    # A fresh native IK solve on an actual measured trial window, not just static parsing.
    marker_times=[t for t in trc_info(markers.read_bytes())['times'] if start<=t<=end]
    ik=run_ik(cfg,str(model),str(markers),marker_times[0],marker_times[10])
    report['fresh_ik']={'rows':ik['rows'],'quality':assess_ik_quality(cfg,str(model),ik['motion_file'],str(markers),max_frames=200)['quality']}
    if args.legacy_python or args.legacy_root:
        assert args.legacy_python and args.legacy_root,'Supply both legacy interpreter and root.'
        legacy=replace(cfg,cli=str(args.legacy_root/'bin/opensim-cmd.exe'))
        with settings_env({'OPENSIM_MCP_API_PYTHON':str(args.legacy_python),'OPENSIM_MCP_INSTALL_DIR':str(args.legacy_root),
                           'OPENSIM_MCP_API_SDK':str(args.legacy_root/'sdk/Python'),'OPENSIM_MCP_TOOL_BACKEND':'cli'}):
            old=ApiSession(legacy)
            try:
                restored=old.load(saved['model_file'])
                assert restored['counts']==status['counts']
                assert abs(restored['total_mass_kg']-status['total_mass_kg'])<1e-8
                back=old.save()
                report['cross_version_46_to_43']={k:restored[k] for k in ('opensim_version','counts','total_mass_kg')}
            finally:old.close()
            id43=run_analysis(legacy,'id',**parameters)
            id43=next(p for p in id43['files'] if p.endswith('inverse_dynamics.sto'))
            report['id43_vs_id46']=compare_tables(id46,id43,.1)
        new=ApiSession(cfg)
        try:
            reopened=new.load(back['model_file']);assert reopened['counts']==status['counts']
            assert abs(reopened['total_mass_kg']-status['total_mass_kg'])<1e-8
            report['cross_version_43_back_to_46']=True
        finally:new.close()
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    report.update(passed=True,original_inputs_unchanged=True)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'human_model_counts':status['counts'],'measured_force_plate_rows':report['force_plate_id']['rows'],
                      'fresh_ik_rows':report['fresh_ik']['rows'],'cross_version':report.get('cross_version_43_back_to_46',False)}))


if __name__=='__main__':main()
