"""Native MocoTrack/MocoInverse analytic fixtures, including a muscle-driven inverse problem."""
import argparse
import json
from pathlib import Path
from opensim_mcp.core import Settings,read_motion
from opensim_mcp.tracking import moco_track,moco_inverse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    cfg=Settings.from_env();examples=Path(__file__).resolve().parents[1]/'examples';evidence={}
    problem=json.loads((examples/'moco_problem.json').read_text());bounds=problem['state_bounds']
    bounds={k:{'bounds':v['bounds']} for k,v in bounds.items()}
    # Zero reference and zero gravity: exact zero control / zero state is the minimum for both terms.
    track=moco_track(cfg,str(examples/'moco_slider.osim'),str(examples/'muscle_slider_static.mot'),0.,1.,bounds,
        problem['control_bounds'],no_external_loads=True,mesh_interval=.1,max_tracking_rms={'slider_tx':1e-5})
    assert track['quality']['solver_success'] and abs(track['quality']['objective'])<1e-7,track
    evidence['track']=track['quality']
    inverse=moco_inverse(cfg,str(examples/'moco_slider.osim'),str(examples/'muscle_slider_static.mot'),0.,1.,no_external_loads=True,mesh_interval=.1)
    assert inverse['quality']['solver_success'] and abs(inverse['quality']['objective'])<1e-7,inverse
    evidence['inverse_actuator']=inverse['quality']
    muscle=moco_inverse(cfg,str(examples/'muscle_slider.osim'),str(examples/'muscle_slider_static.mot'),0.,1.,
        no_external_loads=True,ignore_tendon_compliance=True,mesh_interval=.1,max_iterations=1000)
    assert muscle['quality']['solver_success'],muscle
    controls=read_motion(Path(next(p for p in muscle['files'] if p.endswith('controls.sto'))))
    assert all(-1e-6<=v<=1.000001 for r in controls['rows'] for v in r[1:])
    assert abs(muscle['quality']['objective']-.04)<1e-5
    evidence['inverse_muscle']=muscle['quality']
    forces=json.loads((examples/'external_forces.json').read_text())
    assisted=moco_inverse(cfg,str(examples/'muscle_slider.osim'),str(examples/'muscle_slider_static.mot'),0.,1.,
        loads_path=str(examples/'muscle_slider_loads.sto'),external_forces=forces,ignore_tendon_compliance=True,mesh_interval=.1)
    assert abs(assisted['quality']['objective']-.0225)<1e-5,assisted
    evidence['inverse_with_external_loads']=assisted['quality']
    pin=moco_track(cfg,str(examples/'moco_pin.osim'),str(examples/'moco_pin_degrees.mot'),0.,1.,
        {'/jointset/pin/angle/value':{'bounds':[-3.,3.]},'/jointset/pin/angle/speed':{'bounds':[-5.,5.]}},
        {'/forceset/torque':[-50.,50.]},no_external_loads=True,mesh_interval=.1,convergence_tolerance=1e-8,constraint_tolerance=1e-8,max_tracking_rms={'angle':1e-5})
    assert pin['quality']['coordinate_fit']['angle']['unit']=='rad'
    table=read_motion(Path(next(p for p in pin['files'] if p.endswith('states.sto'))))
    import math
    assert all(abs(r[1]-math.pi/2)<1e-5 for r in table['rows'])
    evidence['degree_reference_converted_to_rad']=pin['quality']
    whitespace=cfg.results_root/'space-reference.mot';whitespace.parent.mkdir(parents=True,exist_ok=True)
    whitespace.write_text((examples/'muscle_slider_static.mot').read_text(encoding='utf-8').replace('\t',' '),encoding='utf-8')
    spaces=moco_inverse(cfg,str(examples/'moco_slider.osim'),str(whitespace),0.,1.,no_external_loads=True,mesh_interval=.1)
    assert abs(spaces['quality']['objective'])<1e-7
    evidence['whitespace_reference_native_solve']=True;evidence['passed']=True
    args.report.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))


if __name__=='__main__':main()
