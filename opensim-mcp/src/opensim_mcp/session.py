from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from .core import InputError, MAX_MODEL, Settings, bounded_read, external_properties, is_under, local_path, xml_model
from .process_tree import ProcessTree


def staged_model(data: bytes) -> bytes:
    from xml.etree import ElementTree as ET
    root, model = xml_model(data)
    for parent in list(model.iter()):
        for child in list(parent):
            if child.tag=='attached_geometry':
                for geometry in list(child):
                    if geometry.tag not in {'Sphere','Brick','Ellipsoid','Cylinder','Cone'}:child.remove(geometry)
                if not len(child):parent.remove(child)
            elif child.tag == "VisibleObject":
                parent.remove(child)
    if external_properties(model) or any(e.attrib.keys()-{"name"} for e in model.iter()):
        raise InputError("Native execution currently requires a self-contained model without external file/library attributes.")
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)


class ApiSession:
    def __init__(self,cfg:Settings):
        self.cfg=cfg
        self.process=None
        self.directory=None
        self.log=None
        self.tree=None
        self.lock=threading.RLock()
        from .recovery import Recovery
        self.recovery=Recovery(cfg,self);self.worker_session_id=None
        atexit.register(self.close)

    def _wait(self,path:Path,seconds:float) -> dict:
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if path.is_file():
                value=json.loads(bounded_read(path,1024*1024))
                path.unlink()
                return value
            if self.process is None or self.process.poll() is not None:
                raise InputError("OpenSim API worker exited; call get_api_session to restart. Session variables were lost.")
            if (self.directory/"native.log").stat().st_size>16*1024*1024:
                raise InputError("Native API log limit exceeded.")
            time.sleep(.025)
        raise TimeoutError("API operation timed out. Worker stopped; in-memory session variables were lost.")

    def start(self):
        if self.process and self.process.poll() is None:
            return
        self.close()
        value=os.environ.get("OPENSIM_MCP_API_PYTHON")
        if not value:
            raise InputError("Set OPENSIM_MCP_API_PYTHON to a Python interpreter with compatible OpenSim bindings.")
        interpreter=local_path(value)
        if not interpreter.is_file():
            raise InputError("Configured API Python executable does not exist.")
        self.directory=Path(tempfile.mkdtemp(prefix="api-session-",dir=self.cfg.temp_root))
        self.log=(self.directory/"native.log").open("wb")
        env=os.environ.copy()
        env.update(TEMP=str(self.directory),TMP=str(self.directory),PYTHONDONTWRITEBYTECODE="1",PYTHONIOENCODING='utf-8')
        # No inherited Python source tree, especially not the MCP venv's packages.
        env.pop("PYTHONPATH",None)
        try:
            self.tree=ProcessTree()
            self.worker_session_id=uuid.uuid4().hex
            revision_base=int(time.time()*1000000)
            self.process=self.tree.spawn([str(interpreter),"-B","-u",str(Path(__file__).with_name("worker.py")),
                                           "--directory",str(self.directory),"--parent-pid",str(os.getpid()),"--revision-base",str(revision_base)],cwd=self.directory,env=env,
                                           stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            ready=self._wait(self.directory/"ready.json",30)
            if not ready["ok"]:
                raise InputError(ready["error"])
        except BaseException:
            self.close(); raise

    def call(self,operation:str,arguments:dict|None=None,timeout:int|None=None) -> dict:
        with self.lock:
            self.start()
            if operation=='evaluate' and self.call('status').get('model_loaded'):
                self.recovery.capture('before trusted script')
            identifier=uuid.uuid4().hex
            log_start=(self.directory/"native.log").stat().st_size
            request={"id":identifier,"operation":operation,"arguments":arguments or {}}
            path=self.directory/"request.json"
            temporary=self.directory/"request.writing"
            temporary.write_text(json.dumps(request,allow_nan=False),encoding="utf-8")
            temporary.replace(path)
            try:
                response=self._wait(self.directory/"response.json",timeout or self.cfg.timeout)
            except BaseException:
                self.close(); raise
            if response.get("id")!=identifier:
                self.close(); raise InputError("Worker response identifier mismatch.")
            if not response["ok"]:
                raise InputError(response["error"])
            value=response["value"]
            value['worker_session_id']=self.worker_session_id
            changed=operation in {'load','change','pose','undo','redo','recovery_restore','topology_commit'} or (operation=='transaction' and not (arguments or {}).get('dry_run',True)) or (operation=='evaluate' and value.get('status')=='completed')
            if operation=='topology' and (arguments or {}).get('dry_run',True):changed=False
            if changed and os.environ.get('OPENSIM_MCP_AUTOSAVE_MODEL','1')=='1':value['recovery']=self.recovery.capture('after '+operation)
            if operation=='status':value['recovery_available']=bool(self.recovery.records())
            if operation in {"evaluate","load","change"}:
                log_path=self.directory/"native.log"
                with log_path.open("rb") as stream:
                    stream.seek(max(log_start,log_path.stat().st_size-24000))
                    value["native_log_tail"]=stream.read(24000).decode("utf-8",errors="replace")
            return value

    def load(self,model_path:str) -> dict:
        with self.lock:
            path=local_path(model_path)
            if path.suffix.lower()!=".osim" or not path.is_file() or not (is_under(path,self.cfg.results_root) or any(is_under(path,r) for r in self.cfg.allowed_roots)):
                raise InputError("Model must be an allowed input or saved result .osim file.")
            data=staged_model(bounded_read(path,MAX_MODEL))
            self.start()
            target=self.directory/"input-model.osim"
            target.write_bytes(data)
            return self.call("load",{"staged_path":str(target),"source_path":str(path)})

    def evaluate(self,code:str,filename:str="<mcp>",timeout:int|None=None) -> dict:
        if os.environ.get("OPENSIM_MCP_ENABLE_SCRIPTS")!="1":
            raise InputError("Arbitrary scripting is disabled. Enable OPENSIM_MCP_ENABLE_SCRIPTS=1 only for a trusted local client.")
        if not code or len(code.encode("utf-8"))>1024*1024:
            raise InputError("Code must be nonempty and at most 1 MiB.")
        if timeout is not None and (type(timeout) is not int or not 1<=timeout<=600):
            raise InputError("Script timeout must be 1..600 seconds.")
        return self.call("evaluate",{"code":code,"filename":filename},timeout)

    def run_script(self,script_path:str,timeout:int|None=None) -> dict:
        path=self.cfg.input_path(script_path,".py")
        return self.evaluate(bounded_read(path,1024*1024).decode("utf-8-sig"),str(path),timeout)

    def save(self) -> dict:
        self.cfg.results_root.mkdir(parents=True,exist_ok=True)
        directory=self.cfg.results_root/("model-"+uuid.uuid4().hex)
        directory.mkdir()
        try:
            result=self.call("save",{"destination":str(directory/"model.osim")})
            xml_model(bounded_read(Path(result["model_file"]),MAX_MODEL))
            (directory/"provenance.json").write_text(json.dumps({**result,"operation":"save_api_model"},indent=2),encoding="utf-8")
            return result
        except BaseException:
            shutil.rmtree(directory); raise

    def close(self):
        with self.lock:
            if self.process:
                if self.tree:self.tree.terminate()
                elif self.process.poll() is None:self.process.kill()
                self.process.wait(timeout=10)
                self.process=None
            if self.tree:self.tree.close();self.tree=None
            if self.log:
                self.log.close(); self.log=None
            if self.directory:
                shutil.rmtree(self.directory,ignore_errors=True)
                self.directory=None
