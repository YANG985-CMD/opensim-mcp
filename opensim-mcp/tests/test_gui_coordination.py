import json,os,subprocess,sys,threading,time,uuid
from pathlib import Path
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.file_lock import FileLock
from opensim_mcp.gui import GuiBridge
from opensim_mcp.pipeline import atomic_json

def test_cross_process_lock_blocks_and_is_released_on_owner_death(tmp_path):
    path=tmp_path/'shared.lock';ready=tmp_path/'ready'
    code='from pathlib import Path; import sys,time; from opensim_mcp.file_lock import FileLock;\nwith FileLock(Path(sys.argv[1])).held():\n Path(sys.argv[2]).touch();time.sleep(60)'
    process=subprocess.Popen([sys.executable,'-B','-c',code,str(path),str(ready)],env=dict(os.environ),cwd=tmp_path)
    try:
        deadline=time.monotonic()+10
        while not ready.exists():
            assert process.poll() is None
            if time.monotonic()>deadline:raise TimeoutError('Lock owner did not start')
            time.sleep(.02)
        with pytest.raises(InputError,match='busy'):
            with FileLock(path,timeout=.1).held():pass
    finally:process.kill();process.wait(timeout=10)
    with FileLock(path,timeout=.2).held():pass

def test_lock_is_reentrant_on_same_thread(tmp_path):
    lock=FileLock(tmp_path/'lock',timeout=.1)
    with lock.held():
        with lock.held():pass

def test_gui_writes_use_last_observed_token_and_timeout_requires_refresh(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'runtime',None);gui=GuiBridge(cfg);gui.prepare()
    current=['epoch:1'];requests=[];stop=threading.Event()
    config=json.loads((gui.folder/'bridge_config.json').read_text(encoding='utf-8'))
    def server():
        while not stop.is_set():
            atomic_json(gui.folder/'heartbeat.json',{'bridge_id':config['bridge_id'],'time':time.time()})
            for file in gui.folder.glob('*.request.json'):
                request=json.loads(file.read_text(encoding='utf-8'));file.unlink();requests.append(request)
                if request['operation']=='status':response={'id':request['id'],'ok':True,'value':{'state_token':current[0]}}
                elif request['arguments'].get('_expected_state_token')!=current[0]:response={'id':request['id'],'ok':False,'error':'GUI_CONFLICT'}
                else:
                    current[0]='epoch:2';response={'id':request['id'],'ok':True,'value':{'state_token':current[0]}}
                atomic_json(gui.folder/(request['id']+'.response.json'),response)
            time.sleep(.01)
    thread=threading.Thread(target=server);thread.start()
    try:
        deadline=time.monotonic()+2
        while not gui.connected() and time.monotonic()<deadline:time.sleep(.01)
        gui.call('status');current[0]='another:2'
        with pytest.raises(InputError,match='GUI_CONFLICT'):gui.call('set_coordinate',{'name':'q','value':0.})
        assert requests[-1]['arguments']['_expected_state_token']=='epoch:1'
        gui.call('status');assert gui.call('set_coordinate',{'name':'q','value':0.})['state_token']=='epoch:2'
        gui.observed_state_token='uncertain'
        with pytest.raises(InputError,match='timed out'):gui.call('stop')
        gui.call('status');gui.call('stop')
    finally:stop.set();thread.join(timeout=3)
