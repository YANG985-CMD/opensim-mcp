"""Reproduce the provided Gait2354 reference segment with explicit example settings."""
import argparse,json
from pathlib import Path
from dataclasses import replace
from opensim_mcp.core import Settings,xml_model,local_path
from opensim_mcp.trial_quality import resample_coordinates
from opensim_mcp.wearable import assemble
from opensim_mcp.muscle_forces import compare_studies,estimate_volumes
from opensim_mcp.session import ApiSession
from opensim_mcp.viewer import export_animation

def main():
    p=argparse.ArgumentParser();p.add_argument('--resources',type=Path,required=True);p.add_argument('--geometry',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--specific-tension-pa',type=float);args=p.parse_args()
    project=Path(__file__).resolve().parents[1];examples=project/'examples'
    resources=local_path(args.resources);geometry=local_path(args.geometry)
    if any(not d.is_dir() or d.parent==d for d in (resources,geometry)):raise ValueError('Supply installed model/Geometry folders, never a drive root.')
    cfg=Settings.from_env();cfg=replace(cfg,allowed_roots=(*cfg.allowed_roots,resources,geometry),timeout=600)
    source=resources/'OutputReference/subject01_simbody_adjusted.osim';reference=resources/'OutputReference/ResultsRRA/subject01_walk1_RRA_Kinematics_q.sto';loads=resources/'subject01_walk1_grf.mot'
    profile=json.loads((examples/'gait2354_study_profile.json').read_text(encoding='utf-8'))
    _,model=xml_model(source.read_bytes());names={n.get('name') for n in model.iter('Coordinate')}
    if names!={d['coordinate'] for d in profile['actuator_profile']}:raise ValueError('This example profile requires the supplied 23-coordinate Gait2354 model.')
    motion=resample_coordinates(cfg,str(reference),60.)
    links=json.loads((examples/'lower_limb_wearable_links.json').read_text(encoding='utf-8'))['links']
    for link in links:link['mesh_path']=str(examples/link['mesh_path'])
    assembly=assemble(cfg,str(source),links,True,[str(geometry)])
    comparison=compare_studies(cfg,str(source),assembly['report_file'],motion['motion_file'],profile['actuator_profile'],profile['quality_limits'],str(loads),profile['external_forces'])
    volume=estimate_volumes(cfg,assembly['model_file'],args.specific_tension_pa) if args.specific_tension_pa is not None else None
    api=ApiSession(cfg)
    try:
        api.load(assembly['model_file'])
        viewer=export_animation(cfg,api,motion['motion_file'],geometry_model_path=assembly['model_file'],muscle_result_path=comparison['wearable']['report_file'],comparison_muscle_result_path=comparison['baseline']['report_file'],muscle_volume_path=volume['report_file'] if volume else None)
    finally:api.close()
    report=dict(completed=True,quality_status=comparison['quality_status'],model_file=assembly['model_file'],comparison_report=comparison['report_file'],motion=motion,viewer=viewer,
                volume_report=volume['report_file'] if volume else None,scope='Provided reference segment only, not a complete cycle. Welded example masses; no active assistance or individual physiological validation.')
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
