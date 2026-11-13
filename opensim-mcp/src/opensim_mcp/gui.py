from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid

from .core import InputError, MAX_MODEL, Settings, bounded_read, is_under, local_path, read_motion, xml_model


class GuiBridge:
    def __init__(self,cfg:Settings):
        self.cfg=cfg
        self.folder=cfg.temp_root/"gui-bridge"
        self.lock=threading.RLock()
        from .file_lock import FileLock
        self.process_lock=FileLock(self.folder/'coordination.lock')
        self.observed_state_token=None
        self.client_id=uuid.uuid4().hex

    def prepare(self) -> dict:
        with self.lock,self.process_lock.held():
            self.folder.mkdir(parents=True,exist_ok=True)
            path=self.folder/"bridge_config.json"
            identity=self.cfg.results_root/'bridge-state'/'identity.json'
            if not path.exists():
                settings=json.loads(bounded_read(identity,1024*1024)) if identity.is_file() else {"bridge_id":uuid.uuid4().hex,"token":secrets.token_hex(32),
                          "allowed_roots":list(map(str,self.cfg.allowed_roots)),"results_root":str(self.cfg.results_root)}
                if settings['allowed_roots']!=list(map(str,self.cfg.allowed_roots)) or settings['results_root']!=str(self.cfg.results_root):raise InputError('GUI bridge roots changed; stop and explicitly reconfigure the bridge identity.')
                path.write_text(json.dumps(settings,indent=2),encoding="utf-8")
            else:
                settings=json.loads(bounded_read(path,1024*1024))
                if settings["allowed_roots"]!=list(map(str,self.cfg.allowed_roots)) or settings["results_root"]!=str(self.cfg.results_root):
                    raise InputError("GUI bridge roots changed. Stop the GUI bridge and remove its old temporary folder before reconnecting.")
            from .pipeline import atomic_json
            if not identity.exists():atomic_json(identity,settings)
            bootstrap=self.folder/"start_gui_bridge.py"
            bridge=Path(__file__).with_name("gui_bridge.py")
            # ASCII source and explicit Unicode literals also work in Jython 2.5
            # when the user's project or scratch folder contains Chinese text.
            literal=lambda value:"u"+ascii(str(value))
            source="# Generated local MCP bootstrap; launched by the GUI startup plugin.\nbridge_config_path = "+literal(path)+"\ntry:\n    execfile("+literal(bridge)+")\nexcept:\n    import traceback\n    open("+literal(self.folder/"startup_error.txt")+", 'w').write(traceback.format_exc())\n    raise\n"
            if not bootstrap.exists() or bootstrap.read_text(encoding="utf-8")!=source:
                writing=self.folder/("bootstrap-"+uuid.uuid4().hex+".writing")
                writing.write_text(source,encoding="utf-8")
                writing.replace(bootstrap)
            root=os.environ.get("OPENSIM_MCP_INSTALL_DIR")
            installed=bool(root and (Path(root)/"opensim/config/Modules/org-opensim-mcp-autobridge.xml").is_file())
            return {"bootstrap_script":str(bootstrap),"connected":self.connected(),
                    "autostart_plugin_installed":installed,
                    "instructions":"With the startup plugin installed, GUI startup automatically runs this bootstrap. Otherwise use Scripts > Run... once per GUI launch. Reinstall the plugin if the configured temporary folder changes.",
                    "bridge_id":settings["bridge_id"]}

    def connected(self) -> bool:
        path=self.folder/"heartbeat.json"
        if not path.is_file():return False
        try:
            heartbeat=json.loads(bounded_read(path,4096))
            config=json.loads(bounded_read(self.folder/"bridge_config.json",1024*1024))
            if heartbeat.get('gui_process'):
                from .process_tree import process_alive
                if not process_alive(int(heartbeat['gui_process'].split('@',1)[0])):return False
            return heartbeat.get("bridge_id")==config["bridge_id"] and 0<=time.time()-heartbeat["time"]<10
        except (OSError,ValueError,KeyError):return False

    def call(self,operation:str,arguments:dict|None=None,timeout:int=30,_skip_prepare=False,_allow_legacy_stop=False) -> dict:
        with self.lock,self.process_lock.held():
            setup={'connected':self.connected(),'bootstrap_script':str(self.folder/'start_gui_bridge.py')} if _skip_prepare else self.prepare()
            if not setup["connected"]:
                raise InputError("GUI bridge is not connected. Start/restart OpenSim with the startup plugin, or run this bootstrap manually: "+setup["bootstrap_script"])
            config=json.loads(bounded_read(self.folder/"bridge_config.json",1024*1024))
            arguments=dict(arguments or {})
            writes={'open_model','load_motion','set_coordinate','undo_pose','select_component','reload_configuration','stop'}
            if operation in writes:
                if self.observed_state_token=='uncertain':
                    raise InputError('Previous GUI operation timed out; refresh GUI status before editing.')
                if self.observed_state_token is None:
                    self.call('status',timeout=timeout,_skip_prepare=True)
                if self.observed_state_token is None and not (operation=='stop' and _allow_legacy_stop):
                    raise InputError('Save GUI work and restart it to load the v1.1 atomic state guard before GUI writes.')
                arguments['_expected_state_token']=self.observed_state_token
                arguments['_client_id']=self.client_id
            identifier=uuid.uuid4().hex
            request={"id":identifier,"token":config["token"],"operation":operation,"arguments":arguments}
            temp=self.folder/(identifier+".writing")
            target=self.folder/(identifier+".request.json")
            response=self.folder/(identifier+".response.json")
            temp.write_text(json.dumps(request,allow_nan=False),encoding="utf-8")
            temp.replace(target)
            deadline=time.monotonic()+timeout
            try:
                while time.monotonic()<deadline:
                    if response.is_file():
                        value=json.loads(bounded_read(response,1024*1024))
                        if value.get("id")!=identifier:raise InputError("GUI response identifier mismatch.")
                        if not value["ok"]:raise InputError(value["error"])
                        result=value['value']
                        token=result.get('state_token') or result.get('gui',{}).get('state_token') if isinstance(result,dict) else None
                        if token:self.observed_state_token=token
                        return value["value"]
                    time.sleep(.05)
                self.observed_state_token='uncertain'
                raise TimeoutError("GUI operation timed out; completion may still occur. Read GUI status before retrying a write.")
            finally:
                # Removing a queued request cancels it only if the GUI has not consumed it.
                target.unlink(missing_ok=True)
                response.unlink(missing_ok=True)

    def input(self,value:str,suffix:str) -> Path:
        path=local_path(value)
        if path.suffix.lower()!=suffix or not path.is_file() or not (is_under(path,self.cfg.results_root) or any(is_under(path,r) for r in self.cfg.allowed_roots)):
            raise InputError("GUI input must be an allowed input/result file with the expected extension.")
        return path

    def open_model(self,model_path:str) -> dict:
        path=self.input(model_path,".osim")
        xml_model(bounded_read(path,MAX_MODEL))
        # Unlike batch execution, opening a trusted GUI model retains its visual
        # geometry. OpenSim may resolve its declared dependencies as usual.
        result=self.call("open_model",{"path":str(path)})
        result["dependency_policy"]="trusted_gui_model_original_dependencies"
        return result

    def load_motion(self,motion_path:str) -> dict:
        path=self.input(motion_path,".mot")
        read_motion(path)
        return self.call("load_motion",{"path":str(path)})

    def snapshot(self) -> dict:
        directory=self.cfg.results_root/("gui-snapshot-"+uuid.uuid4().hex)
        directory.mkdir(parents=True)
        try:
            result=self.call("snapshot",{"destination":str(directory/"model.osim")})
            xml_model(bounded_read(Path(result["model_file"]),MAX_MODEL))
            (directory/"gui_state.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            return result
        except BaseException:
            # On a timeout a GUI write may complete later; retain the folder.
            raise
