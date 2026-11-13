"""Own two synthetic GUI launches in a dedicated profile/bridge directory.

Uses Windows Job Objects for the test GUI and its browser processes. Existing
user GUI instances use another profile/bridge folder and are not terminated.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import replace

from opensim_mcp.core import Settings
from opensim_mcp.gui import GuiBridge
from opensim_mcp.process_tree import ProcessTree


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--opensim-root',type=Path,required=True)
    parser.add_argument('--examples',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--resources-root',type=Path,required=True,help='Already installed official resource folder; prevents first-use resource dialogs in the isolated test profile.')
    args=parser.parse_args();cfg=Settings.from_env();gui=GuiBridge(cfg);prepared=gui.prepare()
    assert not prepared['connected'],'Use a dedicated, currently unconnected test bridge folder.'
    profile=cfg.temp_root/'lifecycle-gui';profile.mkdir(exist_ok=True)
    if not (args.resources_root/'Models').is_dir() or not (args.resources_root/'Code/GUI').is_dir():
        raise RuntimeError('Install the GUI example resources once before unattended GUI regression.')
    (profile/'user').mkdir(exist_ok=True)
    # OpenSim Installer.restorePrefs tests this marker before scheduling the
    # interactive resource installer. Real resources have been verified above.
    (profile/'user/first_launch.text').touch(exist_ok=True)
    command=[str(args.opensim_root/'bin/OpenSim64.exe'),'--userdir',str(profile/'user'),
             '--cachedir',str(profile/'cache'),'-J-Djava.io.tmpdir='+str(profile),
             '-J-Dopensim.mcp.gui.bootstrap='+prepared['bootstrap_script']]
    report={'manual_bootstrap_run':False,'existing_user_gui_modified':False,'processes':[]}
    previous=None
    for iteration in range(2):
        tree=ProcessTree()
        with (profile/('launch-'+str(iteration)+'.log')).open('wb') as log:
            process=tree.spawn(command,env=dict(os.environ,TEMP=str(profile),TMP=str(profile)),
                               cwd=args.opensim_root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+90
                while not gui.connected():
                    if process.poll() is not None:raise RuntimeError('Test GUI exited before automatic bridge startup.')
                    if time.monotonic()>deadline:raise TimeoutError('Automatic GUI attachment timed out.')
                    time.sleep(.5)
                status=gui.call('status');assert status['bridge_version']=='1.1.0' and not status['model_loaded']
                identity=json.loads((gui.folder/'bridge_config.json').read_text(encoding='utf-8'))
                (gui.folder/'bridge_config.json').unlink()
                gui.prepare()
                assert json.loads((gui.folder/'bridge_config.json').read_text(encoding='utf-8'))==identity
                assert gui.call('status')['bridge_version']=='1.1.0'
                pid=status['gui_process'].split('@')[0];assert pid!=previous
                previous=pid;report['processes'].append(pid)
                if iteration==0:
                    # Reload changed server roots in place, preserving a loaded model.
                    gui.open_model(str(args.examples/'slider.osim'))
                    prior=gui.call('status')
                    modified=replace(cfg,allowed_roots=cfg.allowed_roots+(profile,))
                    changed=GuiBridge(modified)
                    from opensim_mcp.gui_lifecycle import reconfigure_gui
                    assert reconfigure_gui(modified,changed)['dry_run']
                    assert reconfigure_gui(modified,changed,False)['applied']
                    after=changed.call('status')
                    assert after['signature']==prior['signature'] and after['gui_process']==prior['gui_process']
                    assert reconfigure_gui(cfg,gui,False)['applied']
                    report['configuration_reload_preserved_current_model_and_process']=True
                    # A second independent process observes the same GUI, then
                    # rejects a stale edit and another session's undo.
                    command_path=profile/'peer-command.json';reply_path=profile/'peer-reply.json'
                    peer_code='''import json,sys,time
from pathlib import Path
from opensim_mcp.core import Settings,InputError
from opensim_mcp.gui import GuiBridge
g=GuiBridge(Settings.from_env());g.call('status');Path(sys.argv[2]).write_text('ready')
while not Path(sys.argv[1]).exists():time.sleep(.02)
try:g.call('set_coordinate',{'name':'slider_tx','value':.08})
except InputError as e:assert 'GUI_CONFLICT' in str(e)
else:raise AssertionError('Stale peer edit was accepted')
g.call('status');g.call('set_coordinate',{'name':'slider_tx','value':.08})
Path(sys.argv[2]).write_text('passed')
'''
                    peer=subprocess.Popen([sys.executable,'-B','-c',peer_code,str(command_path),str(reply_path)],cwd=profile,env=dict(os.environ))
                    try:
                        deadline=time.monotonic()+20
                        while not reply_path.exists():
                            if peer.poll() is not None:raise RuntimeError('GUI peer exited')
                            if time.monotonic()>deadline:raise TimeoutError('Peer GUI status timed out')
                            time.sleep(.05)
                        gui.call('status');gui.call('set_coordinate',{'name':'slider_tx','value':.04});command_path.write_text('go')
                        assert peer.wait(timeout=30)==0
                        assert reply_path.read_text()=='passed'
                        gui.call('status')
                        try:gui.call('undo_pose')
                        except Exception as exc:assert 'GUI_OWNER_CONFLICT' in str(exc)
                        else:raise AssertionError('A session undid the peer session edit')
                        report['cross_process_stale_gui_write_rejected']=True
                        report['cross_session_undo_rejected']=True
                    finally:
                        if peer.poll() is None:peer.kill();peer.wait(timeout=10)
                    smoke_report=args.report.with_name('stdio-gui-v04.json')
                    outcome=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('smoke_v04.py')),
                        '--examples',str(args.examples),'--report',str(smoke_report),'--gui'],
                        env=dict(os.environ),cwd=Path(__file__).resolve().parents[1],timeout=180)
                    assert outcome.returncode==0,'GUI stdio integration failed.'
                    report['full_gui_stdio_report']=str(smoke_report)
            finally:
                tree.terminate();process.wait(timeout=10);tree.close()
        deadline=time.monotonic()+12
        while gui.connected() and time.monotonic()<deadline:time.sleep(.5)
        assert not gui.connected(),'Stopped GUI heartbeat must expire.'
    report.update(passed=True,restarted_into_new_process=True,stale_heartbeat_rejected=True,persistent_identity_recreated_queue_configuration=True)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'automatic_launches':2,'restart_and_stale_heartbeat':True}))


if __name__=='__main__':main()
