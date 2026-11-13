"""Isolated native validation and atomic adoption of bounded topology operations."""
import re,uuid
from .core import InputError,bounded_read
from .pipeline import atomic_json,now
from .structured import run_native

def validate_operations(operations):
    if not isinstance(operations,list) or not 1<=len(operations)<=30:raise InputError('Provide 1..30 explicit topology operations.')
    schema={
        'add_body':({'op','name','mass','mass_center','inertia'},{'geometry'}),
        'add_joint':({'op','name','joint_type','parent_frame','child_body'},{'location_in_parent','orientation_in_parent','location_in_child','orientation_in_child','coordinate'}),
        'add_marker':({'op','name','parent_frame','location'},set()),
        'add_coordinate_actuator':({'op','name','coordinate','optimal_force','min_control','max_control'},set()),
        'remove_component':({'op','component_path'},set()),
        'rename_component':({'op','component_path','new_name'},set()),
        'reconnect_joint':({'op','joint_name','parent_frame'},{'child_body'})}
    for item in operations:
        if not isinstance(item,dict) or item.get('op') not in schema:raise InputError('Unsupported topology operation.')
        required,optional=schema[item['op']]
        if not required<=item.keys() or set(item)-required-optional:raise InputError('Unexpected/missing topology operation fields.')
        for key in ('name','new_name','joint_name','child_body','coordinate'):
            if key in item and isinstance(item[key],str) and not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',item[key]):raise InputError('New component identities must be bounded ASCII identifiers.')
        if item['op']=='add_joint' and item['joint_type'] not in {'PinJoint','SliderJoint','WeldJoint'}:raise InputError('Supported joint types are PinJoint/SliderJoint/WeldJoint.')
        for key in ('parent_frame','component_path'):
            if key in item and (not isinstance(item[key],str) or not item[key].startswith('/') or '..' in item[key] or len(item[key])>500):raise InputError('Use explicit absolute component paths.')

def apply_topology(cfg,api,checkpoints,operations,expected_revision,dry_run=True,label=''):
    validate_operations(operations)
    if type(expected_revision) is not int or expected_revision<0 or type(dry_run) is not bool or not isinstance(label,str) or len(label)>200:raise InputError('Invalid topology revision/preview/label.')
    with api.lock:
        before=api.call('status')
        if before['revision']!=expected_revision or not before['model_loaded']:raise InputError('Refresh the loaded model revision before topology editing.')
        checkpoint=checkpoints.create('Before topology validation')
        preview=run_native(cfg,'topology_preview',checkpoint['model_file'],dict(operations=operations))
        result=dict(preview,expected_revision=expected_revision,dry_run=dry_run,committed=False,before_checkpoint=checkpoint['checkpoint_id'],
            preview_model_file=preview['model_file'],scope='Structured sets and Pin/Slider/Weld connections; candidate native validation runs outside the user worker. Arbitrary component types/plugins are not synthesized.')
        if dry_run:return result
        identifier=uuid.uuid4().hex;root=cfg.results_root/'edit-journal';path=root/(identifier+'.json')
        record=dict(transaction_id=identifier,label=label,created_utc=now(),status='prepared',kind='topology',expected_revision=expected_revision,
            operations=operations,before_checkpoint=checkpoint['checkpoint_id'],preview_model_file=preview['model_file'])
        atomic_json(path,record)
        try:
            adopted=api.call('topology_commit',dict(model_file=preview['model_file'],state_file=str(checkpoints.root/checkpoint['checkpoint_id']/'state.json'),
                renames=preview['renames'],expected_revision=expected_revision))
            record.update(status='committed',result=adopted,finished_utc=now());atomic_json(path,record)
            result.update(api=adopted,revision=adopted['revision'],committed=True,transaction_id=identifier,journal_file=str(path));return result
        except BaseException as exc:
            record.update(status='attention_required',error=str(exc)[-2000:]);atomic_json(path,record);raise
