import json
from pathlib import Path
from dataclasses import replace
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.gui import GuiBridge
from opensim_mcp.recovery import Recovery

def test_gui_queue_recreation_preserves_private_identity_and_roots(tmp_path):
    c=Settings((tmp_path,),tmp_path/'results',tmp_path/'temporary',None)
    g=GuiBridge(c);g.prepare();identity=json.loads((g.folder/'bridge_config.json').read_text(encoding='utf-8'))
    (g.folder/'bridge_config.json').unlink();g.prepare()
    assert json.loads((g.folder/'bridge_config.json').read_text(encoding='utf-8'))==identity
    assert (c.results_root/'bridge-state/identity.json').is_file()
    with pytest.raises(InputError,match='roots changed'):GuiBridge(replace(c,allowed_roots=(tmp_path/'other',))).prepare()

def test_recovery_hash_tampering_is_rejected_before_worker_start(tmp_path):
    c=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    class API:
        def call(self,*args,**kwargs):raise AssertionError('Worker should not be called')
    recovery=Recovery(c,API());folder=recovery.root/('a'*32);folder.mkdir(parents=True)
    (folder/'model.osim').write_bytes(b'tampered');(folder/'state.json').write_text('{}')
    (folder/'snapshot.json').write_text(json.dumps(dict(model_sha256='bad',state_sha256='bad')))
    with pytest.raises(InputError,match='hash'):recovery.restore('a'*32)

def test_recovery_corrupt_history_is_skipped_and_explicit_id_required(tmp_path):
    c=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None);r=Recovery(c,None)
    p=r.root/'broken/snapshot.json';p.parent.mkdir(parents=True);p.write_text('broken')
    assert r.status()['snapshots']==[]
    with pytest.raises(InputError):r.restore('../outside')

def test_gui_reconfiguration_is_explicit_and_uses_server_roots(tmp_path):
    from opensim_mcp.gui_lifecycle import reconfigure_gui
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    gui=GuiBridge(cfg);gui.prepare()
    before=json.loads((gui.folder/'bridge_config.json').read_text(encoding='utf-8'))
    changed=replace(cfg,allowed_roots=(tmp_path/'new',));gui=GuiBridge(changed)
    preview=reconfigure_gui(changed,gui)
    assert preview['changed'] and preview['dry_run']
    assert json.loads((gui.folder/'bridge_config.json').read_text(encoding='utf-8'))==before
    result=reconfigure_gui(changed,gui,False)
    assert result['applied'] and not result['restart_gui_required']
    after=json.loads((gui.folder/'bridge_config.json').read_text(encoding='utf-8'))
    assert after['token']==before['token'] and after['bridge_id']==before['bridge_id']
    assert after['allowed_roots']==[str(tmp_path/'new')]

def test_stale_gui_roots_do_not_prevent_mcp_server_creation(tmp_path):
    from opensim_mcp.server import create_server
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    GuiBridge(cfg).prepare()
    server=create_server(replace(cfg,allowed_roots=(tmp_path/'changed',)))
    assert 'reconfigure_gui_bridge' in server._tool_manager._tools
    assert 'inspect_model' in server._tool_manager._tools
