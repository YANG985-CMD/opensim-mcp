"""Actual MocoInverse mesh refinement and physical force-parameter perturbation."""
import argparse,json
from pathlib import Path
from opensim_mcp.core import Settings
from opensim_mcp.studies import run_convergence,run_sensitivity

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]/'examples';cfg=Settings.from_env()
    parameters=dict(model_path=str(root/'muscle_slider.osim'),coordinates_path=str(root/'muscle_slider_static.mot'),
        initial_time=0.,final_time=1.,no_external_loads=True,mesh_interval=.1)
    mesh=run_convergence(cfg,'moco_inverse',parameters,[.1,.05])
    assert mesh['status']=='objective_only' and abs(mesh['runs'][0]['result']['quality']['objective']-.04)<1e-6
    strength=run_sensitivity(cfg,'moco_inverse',parameters,[dict(label='double muscle strength',model_edits=[dict(component_type='muscle',component_name='puller',property_name='max_isometric_force',value=200.)])])
    assert abs(strength['cases'][0]['result']['quality']['objective']-.01)<1e-6
    result=dict(passed=True,mesh=mesh,sensitivity=strength)
    a.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,mesh_status=mesh['status'],baseline_objective=.04,doubled_strength_objective=.01)))

if __name__=='__main__':main()
