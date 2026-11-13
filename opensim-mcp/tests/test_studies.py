from pathlib import Path
import pytest
from opensim_mcp.core import InputError
from opensim_mcp.studies import trajectory_difference,run_convergence,run_sensitivity

def test_mesh_difference_interpolates_matching_columns_without_extrapolation():
    a={'columns':['time','q'],'rows':[[0.,0.],[1.,1.]]}
    b={'columns':['time','q'],'rows':[[0.,0.],[.5,.5],[1.,1.]]}
    assert trajectory_difference(a,b)['q']['rms']==0.
    b['columns']=['time','other']
    with pytest.raises(InputError):trajectory_difference(a,b)

def test_mesh_refinement_rejects_invalid_grid_before_native_execution():
    p=dict(model_path='unused',coordinates_path='unused',initial_time=0.,final_time=1.,no_external_loads=True)
    for grids in ([.1],[.1,.2],[.1,.1],[.1,float('nan')],[.1,.001]):
        with pytest.raises(InputError):run_convergence(None,'moco_inverse',p,grids)

def test_sensitivity_rejects_arbitrary_operators_paths_and_duplicate_labels():
    p=dict(model_path='unused',coordinates_path='unused',initial_time=0.,final_time=1.,no_external_loads=True)
    for v in ([{'label':'x','parameter_overrides':{'model_path':'other'}}],
              [{'label':'x','model_edits':[{'code':'print(1)'}]}],
              [{'label':'x','parameter_overrides':{'tracking_weight':1.}},{'label':'x','parameter_overrides':{'tracking_weight':2.}}]):
        with pytest.raises(InputError):run_sensitivity(None,'moco_inverse',p,v)
