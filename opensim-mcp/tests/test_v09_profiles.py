from pathlib import Path
import json
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.rra import run_rra
from opensim_mcp.templates import create_biomechanics_project
from opensim_mcp.projects import prepare_submission
ROOT=Path(__file__).resolve().parents[1]/'examples'

def cfg(tmp_path):
    (tmp_path/'scratch').mkdir();return Settings((ROOT,),tmp_path/'results',tmp_path/'scratch',None)

def test_full_muscle_template_produces_typed_ordered_project(tmp_path):
    c=cfg(tmp_path)
    r=create_biomechanics_project(c,'reviewable',str(ROOT/'muscle_slider_markers.osim'),str(ROOT/'slider_scale_static.trc'),str(ROOT/'slider.trc'),
        2.,{'block':[1.,1.,1.]},['M2'],{'M1':1.,'M2':1.,'M3':1.},2.,no_external_loads=True,quality_limits={'marker_rms_m':.001})
    prepared=prepare_submission(c,r['project_path']);assert len(prepared['project']['stages'])==8
    assert r['quality_thresholds_automatically_inferred'] is False

def test_full_pipeline_requires_explicit_load_assumption_and_muscles(tmp_path):
    c=cfg(tmp_path)
    with pytest.raises(InputError,match='muscles'):create_biomechanics_project(c,'x',str(ROOT/'slider.osim'),str(ROOT/'slider.trc'),str(ROOT/'slider.trc'),1.,{'block':[1.,1.,1.]},['M1'],{'M1':1.},2.,no_external_loads=True)

def test_rra_com_adjustment_requires_explicit_six_axis_residuals(tmp_path):
    c=cfg(tmp_path)
    with pytest.raises(InputError):run_rra(c,str(ROOT/'muscle_slider.osim'),str(ROOT/'muscle_slider_static.mot'),
        [dict(name='reserve',coordinate='slider_tx',role='reserve',unit='N',optimal_force=1.,min_control=-100.,max_control=100.)],
        {'slider_tx':1.},no_external_loads=True,adjust_com_body='block')
