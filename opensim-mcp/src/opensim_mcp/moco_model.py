"""Explicit, auditable muscle conversion for Moco-compatible model copies."""
from .core import InputError
from .structured import run_native,actuator_definitions

def prepare_moco_model(cfg,model_path,replace_muscles_with_degroote=True,ignore_tendon_compliance=False,ignore_passive_fiber_force=False,reserve_definitions=None):
    for v in (replace_muscles_with_degroote,ignore_tendon_compliance,ignore_passive_fiber_force):
        if type(v) is not bool:raise InputError('Muscle transformation choices must be explicit booleans.')
    definitions=actuator_definitions(reserve_definitions) if reserve_definitions else []
    return run_native(cfg,'prepare_moco_model',model_path,dict(replace_muscles=replace_muscles_with_degroote,
        ignore_tendon_compliance=ignore_tendon_compliance,ignore_passive=ignore_passive_fiber_force,definitions=definitions))
