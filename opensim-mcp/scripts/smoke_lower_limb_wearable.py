"""Original schematic lower-limb CAD wearing + native mass/ID comparison."""
import argparse,json
from pathlib import Path
from opensim_mcp.core import Settings
from opensim_mcp.session import ApiSession
from opensim_mcp.wearable import assemble,prepare_motion
from opensim_mcp.wearable_analysis import compare_id
from opensim_mcp.viewer import export_animation

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);args=p.parse_args();cfg=Settings.from_env()
    examples=Path(__file__).resolve().parents[1]/'examples';spec=json.loads((examples/'lower_limb_wearable_links.json').read_text(encoding='utf-8'))
    for link in spec['links']:link['mesh_path']=str(examples/link['mesh_path'])
    assembly=assemble(cfg,str(examples/spec['model']),spec['links'],True)
    assert abs(assembly['quality']['added_device_mass_kg']-.6)<1e-10
    motion=prepare_motion(cfg,assembly['report_file'],str(examples/'lower_limb_demo.mot'))
    comparison=compare_id(cfg,str(examples/spec['model']),assembly['report_file'],motion['motion_file'],no_external_loads=True)
    api=ApiSession(cfg)
    try:
        loaded=api.load(assembly['model_file']);assert loaded['counts']['bodies']==9
        viewer=export_animation(cfg,api,motion['motion_file'],assembly['model_file'],max_frames=121)
        assert viewer['mesh_count']==9
        assert not any('Missing' in warning or 'Unsupported' in warning for warning in viewer['warnings'])
    finally:api.close()
    result=dict(passed=True,assembly=assembly,matched_id_comparison=comparison,viewer=viewer,
        original_synthetic_fixture=True,physiological_validation=False,scope='Schematic seven-body lower limbs + two original CAD cuffs. Example masses/inertias and prescribed motion, no measured participant/device data, straps/contact absent.')
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,bodies=9,mesh_count=9,frames=121,added_device_mass_kg=.6)))

if __name__=='__main__':main()
