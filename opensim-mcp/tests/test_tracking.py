from pathlib import Path
import pytest
from opensim_mcp.core import InputError,Settings
from opensim_mcp.tracking import moco_track,moco_inverse,solver_options
from opensim_mcp.jobs import validate_submission
ROOT=Path(__file__).resolve().parents[1]/'examples'


@pytest.fixture
def cfg(tmp_path):return Settings((ROOT,),tmp_path/'results',tmp_path/'temp',None)


def test_prescribed_motion_requires_explicit_load_assumption(cfg):
    with pytest.raises(InputError,match='loads'):moco_inverse(cfg,str(ROOT/'muscle_slider.osim'),str(ROOT/'muscle_slider_static.mot'),0.,1.)


def test_conflicting_load_assumptions_rejected(cfg):
    with pytest.raises(InputError,match='together'):moco_inverse(cfg,str(ROOT/'muscle_slider.osim'),str(ROOT/'muscle_slider_static.mot'),0.,1.,loads_path=str(ROOT/'muscle_slider_loads.sto'),no_external_loads=True)


def test_reference_coverage_no_extrapolation(cfg):
    with pytest.raises(InputError,match='covered'):moco_inverse(cfg,str(ROOT/'muscle_slider.osim'),str(ROOT/'muscle_slider_static.mot'),0.,2.,no_external_loads=True)


@pytest.mark.parametrize('mesh,iterations,tolerance',[(0.,10,1e-4),(.001,10,1e-4),(.1,0,1e-4),(.1,10,float('nan'))])
def test_solver_budgets_bounded(mesh,iterations,tolerance):
    with pytest.raises(InputError):solver_options(mesh,iterations,tolerance,1e-4,0.,1.)


def test_endpoint_bounds_must_be_inside_general_bounds(cfg):
    with pytest.raises(InputError,match='Endpoint'):moco_track(cfg,str(ROOT/'moco_slider.osim'),str(ROOT/'muscle_slider_static.mot'),0.,1.,{'/q':{'bounds':[-1.,1.],'initial':[2.]}},{'/u':[-1.,1.]},no_external_loads=True)


def test_new_profiles_use_async_submission_validation():
    validate_submission('moco_inverse',dict(model_path='m',coordinates_path='c',initial_time=0.,final_time=1.))
    with pytest.raises(InputError):validate_submission('moco_track',dict(model_path='m'))
