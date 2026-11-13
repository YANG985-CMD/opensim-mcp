"""Kill an owned native worker and recover full muscle/coordinate state; no GUI writes."""
import argparse,json,os
from pathlib import Path
from opensim_mcp.core import Settings,InputError
from opensim_mcp.session import ApiSession

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    cfg=Settings.from_env();api=ApiSession(cfg);model=Path(__file__).resolve().parents[1]/'examples/muscle_slider_dynamic.osim'
    try:
        loaded=api.load(str(model));assert loaded['recovery']['status']=='saved',loaded
        changed=api.evaluate("model.getCoordinateSet().get('slider_tx').setValue(state,0.03,False)\nmodel.getCoordinateSet().get('slider_tx').setSpeedValue(state,0.12)\nmodel.setStateVariableValue(state,'/forceset/puller/activation',0.37)\nstate.setTime(0.25)\nsentinel=7\nresult=True")
        assert changed['status']=='completed',changed
        assert changed['recovery']['status']=='saved',changed
        identifier=changed['recovery']['snapshot_id'];old_revision=changed['revision'];old_worker=changed['worker_session_id']
        api.tree.terminate();status=api.call('status');assert not status['model_loaded'] and status['worker_session_id']!=old_worker
        restored=api.recovery.restore(identifier);assert restored['api']['restored_state_count']>=3
        assert restored['api']['revision']!=old_revision and restored['api']['max_native_state_restore_error']<1e-12
        values=api.evaluate("result={'q':model.getCoordinateSet().get('slider_tx').getValue(state),'u':model.getCoordinateSet().get('slider_tx').getSpeedValue(state),'activation':model.getMuscles().get('puller').getActivation(state),'time':state.getTime(),'python_variable_restored':'sentinel' in globals()}")['result']
        assert abs(values['q']-.03)<1e-12 and abs(values['u']-.12)<1e-12 and abs(values['activation']-.37)<1e-12 and values['time']==.25 and not values['python_variable_restored'],values
        try:api.recovery.restore(identifier)
        except InputError:pass
        else:raise AssertionError('Live model replacement requires explicit discard_current.')
        try:api.evaluate('while True: pass',timeout=1)
        except TimeoutError:pass
        else:raise AssertionError('Script should time out.')
        available=api.recovery.status();assert available['snapshots']
        second=ApiSession(cfg)
        try:
            persisted=second.recovery.restore(identifier);assert persisted['api']['max_native_state_restore_error']<1e-12
        finally:second.close()
        evidence=dict(passed=True,worker_kill_recovered=True,full_native_state=values,script_timeout_snapshot_preserved=True,
            fresh_api_manager_recovers_durable_snapshot=True,stale_worker_revision_not_reused=True,scope='Native model/states/time only; no Python variable or external-effect recovery.')
        a.report.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))
    finally:api.close()

if __name__=='__main__':main()
