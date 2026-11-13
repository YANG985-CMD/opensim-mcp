"""Actual isolated topology, all-state preservation and undo/rollback regression."""
import argparse,json
from pathlib import Path
from opensim_mcp.core import Settings,InputError
from opensim_mcp.session import ApiSession
from opensim_mcp.checkpoints import Checkpoints
from opensim_mcp.transactions import Transactions
from opensim_mcp.topology import apply_topology

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    cfg=Settings.from_env();api=ApiSession(cfg);points=Checkpoints(cfg,api);journal=Transactions(cfg,api,points)
    model=Path(__file__).resolve().parents[1]/'examples/muscle_slider_dynamic.osim'
    def state():return {x['path']:x['value'] for x in api.call('native_state')['states']}
    try:
        api.load(str(model));changed=api.evaluate("model.getCoordinateSet().get('slider_tx').setValue(state,.03,False)\nmodel.getCoordinateSet().get('slider_tx').setSpeedValue(state,.12)\nmodel.setStateVariableValue(state,'/forceset/puller/activation',.37)\nstate.setTime(.25)")
        assert changed['status']=='completed';original=state()
        mass=api.call('change',dict(component_type='body',component_name='block',property_name='mass',value=3.))
        assert state()==original and api.call('status')['time']==.25
        api.call('undo',dict(expected_revision=mass['revision']));assert state()==original
        operations=[dict(op='add_body',name='link',mass=1.,mass_center=[0.,0.,0.],inertia=[.01,.01,.01,0.,0.,0.],geometry={'type':'brick','half_lengths':[.03,.15,.03],'color':[.8,.3,.2]}),
            dict(op='add_joint',name='hinge',joint_type='PinJoint',parent_frame='/bodyset/block',child_body='link',location_in_parent=[0.,.25,0.],coordinate={'name':'link_angle','range':[-1.,1.],'default_value':.2}),
            dict(op='add_marker',name='Tip',parent_frame='/bodyset/link',location=[0.,.15,0.])]
        revision=api.call('status')['revision'];preview=apply_topology(cfg,api,points,operations,revision,True)
        assert not preview['committed'] and api.call('status')['counts']['bodies']==1 and state()==original
        committed=apply_topology(cfg,api,points,operations,revision,False,'Add connected visualized body')
        assert committed['api']['counts']['bodies']==2 and committed['api']['new_state_count']==2
        for name,value in original.items():assert abs(state()[name]-value)<1e-12
        undone=api.call('undo',dict(expected_revision=committed['revision']));assert undone['counts']['bodies']==1 and state()==original
        redone=api.call('redo',dict(expected_revision=undone['revision']));assert redone['counts']['bodies']==2
        renamed=apply_topology(cfg,api,points,[dict(op='rename_component',component_path='/bodyset/link',new_name='link2'),dict(op='rename_component',component_path='/jointset/hinge',new_name='hinge2')],redone['revision'],False)
        assert '/jointset/hinge2/link_angle/value' in state() and abs(state()['/forceset/puller/activation']-.37)<1e-12
        before_revision=api.call('status')['revision']
        try:apply_topology(cfg,api,points,[dict(op='remove_component',component_path='/bodyset/block')],before_revision,False)
        except InputError:pass
        else:raise AssertionError('Dangling references must be rejected outside user worker.')
        assert api.call('status')['revision']==before_revision and api.call('status')['counts']['bodies']==2
        rolled=journal.rollback(committed['transaction_id'],before_revision)
        assert rolled['restore']['api']['counts']['bodies']==1 and state()==original and api.call('status')['time']==.25
        saved=api.save()
        result=dict(passed=True,native_preview_atomic=True,full_state_preserved_through_parameter_edit=True,one_step_undo_redo=True,
            rename_updates_references_and_native_state_paths=True,dangling_body_rejected_without_losing_live_model=True,durable_full_state_rollback=True,
            preview_model=committed['preview_model_file'],saved_original_model=saved['model_file'])
        a.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:api.close()

if __name__=='__main__':main()
