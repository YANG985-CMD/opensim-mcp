"""Analytic one-muscle force/added-mass/volume regression; no human data required."""
import argparse,json
from pathlib import Path
from opensim_mcp.core import Settings,InputError
from opensim_mcp.wearable import assemble
from opensim_mcp.muscle_forces import compare_studies,force_study,load_report,estimate_volumes
from opensim_mcp.session import ApiSession
from opensim_mcp.viewer import export_animation

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    cfg=Settings.from_env();examples=Path(__file__).resolve().parents[1]/'examples'
    # In a staged developer run, OPENSIM_MCP_EXAMPLES points at the installed fixtures.
    import os
    examples=Path(os.environ.get('OPENSIM_MCP_EXAMPLES',examples))
    definitions=[dict(name='reserve_tx',coordinate='slider_tx',role='reserve',unit='N',optimal_force=1.,min_control=-100.,max_control=100.)]
    limits=dict(max_reserve_peak_fraction=.1,max_residual_actuator_force_N=20.,max_residual_actuator_moment_Nm=75.)
    links=[dict(name='test_mass',parent_frame='/bodyset/block',mesh_path=str(examples/'Geometry/wearable_cuff_mm.obj'),mesh_units='mm',
                translation_m=[0,0,0],orientation_xyz_rad=[0,0,0],mass_kg=.6,mass_center_m=[0,0,0],inertia_kg_m2=[.001,.001,.001,0,0,0],joint_type='WeldJoint')]
    assembly=assemble(cfg,str(examples/'muscle_slider.osim'),links)
    common=dict(coordinates_path=str(examples/'muscle_slider_static.mot'),actuator_profile=definitions,quality_limits=limits,no_external_loads=True)
    comparison=compare_studies(cfg,str(examples/'muscle_slider.osim'),assembly['report_file'],**common)
    baseline=load_report(cfg,comparison['baseline']['report_file']);worn=load_report(cfg,comparison['wearable']['report_file'])
    totals=[]
    for r,expected in ((baseline,20.),(worn,26.)):
        values=[m+reserve for m,reserve in zip(r['series']['forces_N']['puller'],r['audit_series']['actuator_forces']['reserve_tx'])]
        error=max(abs(v-expected) for v in values);assert error<.002,(expected,error);totals.append(dict(expected_N=expected,max_balance_error_N=error))
    assert comparison['quality_status']=='pass'
    volume=estimate_volumes(cfg,assembly['model_file'],300000.);assert abs(volume['muscles']['puller']['volume_cm3']-200)<1e-9
    api=ApiSession(cfg)
    try:
        api.load(assembly['model_file'])
        viewer=export_animation(cfg,api,common['coordinates_path'],geometry_model_path=assembly['model_file'],muscle_result_path=comparison['wearable']['report_file'],comparison_muscle_result_path=comparison['baseline']['report_file'],muscle_volume_path=volume['report_file'])
        assert viewer['muscle_force_results_included'] and viewer['muscle_count']==1
    finally:api.close()
    result=dict(passed=True,balance_checks=totals,analytic_volume_cm3=200,comparison_report=comparison['report_file'],viewer=viewer)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
