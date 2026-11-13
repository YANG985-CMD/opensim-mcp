"""Native MarkerPlacer and explicit reserve/usage regression."""
import argparse
import json
from pathlib import Path
from opensim_mcp.core import Settings,InputError,read_motion
from opensim_mcp.structured import place_markers,configure_actuators,assess_actuator_usage
from opensim_mcp.analysis import run_analysis


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    cfg=Settings.from_env();examples=Path(__file__).resolve().parents[1]/'examples';evidence={}
    p=dict(model_path=str(examples/'slider.osim'),static_marker_path=str(examples/'slider_scale_static.trc'),
           movable_markers=['M2'],marker_weights={'M1':1.,'M2':1.,'M3':1.},max_marker_movement_m=.11)
    placed=place_markers(cfg,**p);assert abs(placed['quality']['max_marker_shift_m']-.1)<1e-6,placed
    assert placed['quality']['protected_markers_unchanged'];evidence['placement']=placed['quality']
    try:place_markers(cfg,**dict(p,max_marker_movement_m=.01))
    except InputError:evidence['movement_limit_rejected']=True
    else:raise AssertionError('Movement limit did not reject native result')
    definitions=[dict(name='reserve_tx',coordinate='slider_tx',role='reserve',unit='N',optimal_force=1.,min_control=-100.,max_control=100.)]
    model=configure_actuators(cfg,str(examples/'muscle_slider.osim'),definitions)['model_file']
    try:configure_actuators(cfg,model,definitions)
    except InputError:evidence['duplicate_rejected']=True
    else:raise AssertionError('Duplicate was accepted')
    try:configure_actuators(cfg,str(examples/'muscle_slider.osim'),[dict(definitions[0],unit='Nm')])
    except InputError:evidence['wrong_unit_rejected']=True
    else:raise AssertionError('Wrong unit was accepted')
    common=dict(model_path=model,coordinates_path=str(examples/'muscle_slider_static.mot'),no_external_loads=True)
    so=run_analysis(cfg,'static_optimization',**common);id_result=run_analysis(cfg,'id',**common)
    forces=next(p for p in so['files'] if p.endswith('_force.sto'));reference=id_result['files'][0]
    usage=assess_actuator_usage(cfg,model,forces,[dict(name='reserve_tx',role='reserve',unit='N',force_column='reserve_tx',reference_column='slider_tx_force')],reference)
    assert usage['quality']['max_rms_fraction_reference'] is not None
    assert 0<=usage['quality']['max_rms_fraction_reference']<.05,usage
    evidence['usage']=usage['quality'];evidence['passed']=True
    args.report.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))


if __name__=='__main__':main()
