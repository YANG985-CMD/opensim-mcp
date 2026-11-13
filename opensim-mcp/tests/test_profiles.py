from pathlib import Path
import pytest
from opensim_mcp.core import InputError,Settings
from opensim_mcp.structured import actuator_definitions,assess_actuator_usage,place_markers
from opensim_mcp.projects import validate_shape


def definition():return dict(name='reserve_tx',coordinate='slider_tx',role='reserve',unit='N',optimal_force=1.,min_control=-1.,max_control=1.)


@pytest.mark.parametrize('change',[{'optimal_force':0.},{'min_control':2.},{'optimal_force':float('nan')},{'unit':'kg'},{'role':'automatic'},{'name':'../x'},{'file':'evil'}])
def test_explicit_actuator_physics_rejects_ambiguity(change):
    with pytest.raises(InputError):actuator_definitions([dict(definition(),**change)])


def test_duplicate_coordinate_or_name_rejected():
    with pytest.raises(InputError):actuator_definitions([definition(),dict(definition(),name='second')])


def test_usage_requires_each_explicit_reference_column():
    d=dict(name='reserve_tx',role='reserve',unit='N',force_column='reserve_tx')
    with pytest.raises(InputError,match='reference column'):assess_actuator_usage(None,'model.osim','forces.sto',[d],'ref.sto')


def test_marker_movement_requires_explicit_names():
    with pytest.raises(InputError):place_markers(None,'model.osim','trial.trc',[],{'M1':1.})
    with pytest.raises(InputError):place_markers(None,'model.osim','trial.trc',['M1'],{'M1':0.})


def test_calibration_and_reserve_workflows_can_be_staged():
    p={'schema_version':1,'name':'test','inputs':{'model':{'path':'model.osim','kind':'model'},'markers':{'path':'static.trc','kind':'markers','length_unit':'m'}},
       'stages':[{'id':'place','workflow':'marker_placement','parameters':{'model_path':'${inputs.model}','static_marker_path':'${inputs.markers}','movable_markers':['M1'],'marker_weights':{'M1':1.}}},
                 {'id':'reserve','workflow':'configure_actuators','parameters':{'model_path':'${stages.place.model}','definitions':[definition()]}}]}
    assert len(validate_shape(p).stages)==2
