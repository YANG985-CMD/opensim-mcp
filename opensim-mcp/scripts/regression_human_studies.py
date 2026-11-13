"""Opt-in short-window RRA and muscle MocoInverse on installed Gait2354 data.

This reproduces one named public example, with explicit example-specific
actuators, loads and times. It is not a generic physiological protocol.
"""
from __future__ import annotations
import argparse,hashlib,json
from dataclasses import replace
from pathlib import Path
from opensim_mcp.core import Settings,MAX_MODEL,bounded_read,xml_model
from opensim_mcp.rra import run_rra
from opensim_mcp.moco_model import prepare_moco_model
from opensim_mcp.studies import run_convergence

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resources',type=Path,required=True,help='Installed Gait2354_Simbody folder, including OutputReference.')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();root=args.resources.resolve()
    cfg=Settings.from_env();cfg=replace(cfg,allowed_roots=(*cfg.allowed_roots,root),timeout=600)
    model=root/'OutputReference/subject01_simbody.osim'
    coordinates=root/'OutputReference/subject01_walk1_ik.mot';loads=root/'subject01_walk1_grf.mot'
    inputs=[model,coordinates,loads];before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    _,tree=xml_model(bounded_read(model,MAX_MODEL));names=[c.get('name') for c in tree.iter('Coordinate')]
    residual_map={'pelvis_tx':'FX','pelvis_ty':'FY','pelvis_tz':'FZ','pelvis_list':'MX','pelvis_rotation':'MY','pelvis_tilt':'MZ'}
    if not residual_map.keys()<=set(names):raise ValueError('Expected Gait2354 pelvis coordinate names.')
    definitions=[dict(name=residual_map.get(n,'reserve_'+n),coordinate=n,role='residual' if n in residual_map else 'reserve',
        unit='N' if n in {'pelvis_tx','pelvis_ty','pelvis_tz'} else 'Nm',optimal_force=1.,min_control=-10000.,max_control=10000.) for n in names]
    forces=[]
    for name,body,prefix,torque in [('right','calcn_r','','ground_torque_'),('left','calcn_l','1_','1_ground_torque_')]:
        forces.append(dict(name=name,applied_to_body=body,force_identifier=prefix+'ground_force_v',point_identifier=prefix+'ground_force_p',
            torque_identifier=torque,force_expressed_in_body='ground',point_expressed_in_body='ground'))
    rra=run_rra(cfg,str(model),str(coordinates),definitions,{n:1. for n in names},str(loads),forces,start_time=.4,end_time=.6,adjust_com_body='torso')
    prepared=prepare_moco_model(cfg,str(model),True,True,False,definitions)
    parameters=dict(model_path=prepared['model_file'],coordinates_path=str(coordinates),initial_time=.4,final_time=.5,loads_path=str(loads),external_forces=forces,
        ignore_tendon_compliance=True,max_iterations=1000,convergence_tolerance=1e-4,constraint_tolerance=1e-4)
    study=run_convergence(cfg,'moco_inverse',parameters,[.015,.0075])
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==before[p.name] for p in inputs),'Source example changed.'
    report=dict(passed=True,dataset='Official installed Gait2354_Simbody / subject01',input_hashes=before,inputs_redistributed=False,
        physiological_validation=False,rra=rra,prepared_moco_model=prepared,moco_mesh_study=study,
        scope='Short windows only, explicit DGF conversion and reserves; objective-only mesh agreement is not full trajectory convergence or physiological validation.')
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(passed=True,coordinate_count=len(names),mesh_status=study['status'],rra_time_range_s=rra['quality']['time_range_s'])))

if __name__=='__main__':main()
