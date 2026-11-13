"""Observed GUI lifecycle without closing another user's unsaved model."""
import json,os,subprocess,time
from pathlib import Path
from .core import InputError,local_path,bounded_read

def reconfigure_gui(cfg,gui,dry_run=True,allow_legacy_stop=False):
    if type(dry_run) is not bool or type(allow_legacy_stop) is not bool:
        raise InputError('GUI configuration flags must be booleans.')
    from .pipeline import atomic_json
    import secrets,uuid
    with gui.lock,gui.process_lock.held():
        path=gui.folder/'bridge_config.json'
        identity=cfg.results_root/'bridge-state/identity.json'
        old=json.loads(bounded_read(path,1024*1024)) if path.is_file() else json.loads(bounded_read(identity,1024*1024)) if identity.is_file() else None
        new=dict(old or {},allowed_roots=list(map(str,cfg.allowed_roots)),results_root=str(cfg.results_root))
        if old is None:new.update(bridge_id=uuid.uuid4().hex,token=secrets.token_hex(32))
        if not isinstance(new.get('bridge_id'),str) or not isinstance(new.get('token'),str):raise InputError('Invalid persisted bridge identity.')
        connected=gui.connected()
        result=dict(dry_run=dry_run,connected=connected,changed=old!=new,
            previous_roots={k:old.get(k) for k in ('allowed_roots','results_root')} if old else None,
            configured_roots={k:new[k] for k in ('allowed_roots','results_root')},
            scope='Uses only server-configured roots. GUI model and process remain open.')
        if dry_run:return result
        restart=False
        if connected:
            status=gui.call('status',_skip_prepare=True)
            if 'configuration_reload' in status.get('capabilities',[]):
                result['gui']=gui.call('reload_configuration',{'configuration':new},_skip_prepare=True)['gui']
            elif not allow_legacy_stop:
                return dict(result,applied=False,action_required='Legacy bridge cannot reload. Preserve unsaved work, then use allow_legacy_stop=true and restart the GUI when ready.')
            else:
                gui.call('stop',_skip_prepare=True,_allow_legacy_stop=True);restart=True
        atomic_json(path,new);atomic_json(identity,new)
        gui.prepare();gui.startup_error=None
        return dict(result,applied=True,restart_gui_required=restart)

def ensure_gui(cfg,gui,launch_if_closed=False,wait_seconds=30):
    if type(launch_if_closed) is not bool or type(wait_seconds) is not int or not 0<=wait_seconds<=120:raise InputError('Invalid GUI launch/wait settings.')
    prepared=gui.prepare();launched=False;existing=[]
    if not gui.connected() and launch_if_closed:
        query=subprocess.run(['powershell.exe','-NoProfile','-Command',"Get-Process -Name OpenSim64 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }"],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=10,creationflags=0x08000000)
        existing=[int(line) for line in query.stdout.decode(errors='replace').splitlines() if line.strip().isdigit()]
        if existing:return dict(connected=False,launched=False,existing_gui_processes=existing,action_required='An existing GUI is not attached to this bridge. Preserve unsaved work and restart it with the startup plugin or run the bootstrap explicitly.',bootstrap_script=prepared['bootstrap_script'])
        root=os.environ.get('OPENSIM_MCP_INSTALL_DIR')
        if not root or not (local_path(root)/'bin/OpenSim64.exe').is_file():raise InputError('Configure an installed OpenSim GUI root before launching it.')
        script=Path(__file__).resolve().parents[2]/'scripts/start-gui.ps1'
        process=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-OpenSimRoot',root,'-TempRoot',str(cfg.temp_root),'-BootstrapScript',prepared['bootstrap_script']],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=20,creationflags=0x08000000)
        if process.returncode:raise InputError('GUI launcher failed: '+process.stderr.decode(errors='replace')[-2000:])
        launched=True
    deadline=time.monotonic()+wait_seconds
    while not gui.connected() and time.monotonic()<deadline:time.sleep(.2)
    result=dict(connected=gui.connected(),launched=launched,bootstrap_script=prepared['bootstrap_script'],
        persistent_identity=str(cfg.results_root/'bridge-state/identity.json'),scope='GUI attachment only; no API/GUI model merge or automatic closure of an existing GUI.')
    if result['connected']:
        status=gui.call('status');result['gui']=status
        if status.get('bridge_version') not in {'0.4.0','1.0.0','1.1.0'}:result['compatibility_warning']='Unvalidated bridge version.'
    else:
        error=gui.folder/'startup_error.txt'
        if error.is_file():result['startup_error']=bounded_read(error,16384).decode('utf-8',errors='replace')
    return result
