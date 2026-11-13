"""A serialized JSON RPC pipe to a process whose main thread owns COM STA."""
import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


class CadError(RuntimeError):
    def __init__(self, payload):
        self.payload=payload
        super().__init__(json.dumps(payload,ensure_ascii=False))


class Broker:
    def __init__(self, command=None, timeout=None):
        self.command=command or [sys.executable,"-B","-u","-m","swlocal.worker"]
        self.timeout=timeout or float(os.environ.get("SWLOCAL_TIMEOUT","120"))
        self.lock=threading.Lock()
        self.process=None
        self.messages=None
        self.log_handle=None
        self.sequence=0
        self.runtime=Path(os.environ.get("SWLOCAL_TEMP",r"E:\simulink\_codex_tmp\solidworks_local_runtime"))/uuid.uuid4().hex
        self.runtime.mkdir(parents=True,exist_ok=True)
        atexit.register(self.close)

    def _start(self):
        self.messages=queue.Queue()
        self.log_handle=(self.runtime/"worker.log").open("a",encoding="utf-8")
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", TEMP=str(self.runtime), TMP=str(self.runtime))
        env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
        self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log_handle,text=True,encoding="utf-8",bufsize=1,env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        output=self.process.stdout
        inbox=self.messages
        def pump():
            try:
                for line in output:
                    try: inbox.put(json.loads(line))
                    except ValueError: inbox.put({'protocol_error':line[:300]})
            finally: inbox.put({'eof':True})
        threading.Thread(target=pump,name="swlocal-worker-output",daemon=True).start()

    def close(self):
        proc,self.process=self.process,None
        if proc:
            try:
                if proc.stdin: proc.stdin.close()
                proc.wait(timeout=.7)
            except (OSError,subprocess.TimeoutExpired):
                proc.kill()
                try: proc.wait(timeout=2)
                except subprocess.TimeoutExpired: pass
            for stream in (proc.stdout,proc.stderr):
                if stream:
                    try: stream.close()
                    except OSError: pass
        if self.log_handle:
            self.log_handle.close()
            self.log_handle=None
        lease=self.runtime/'native_batch.json'
        if not lease.exists():lease=self.runtime/'pose_display_lease.json'
        if not lease.exists():lease=self.runtime/'stl_preferences.json'
        if lease.exists():
            # Never leave the native application's API batch flag behind when
            # stopping a timed-out bridge. Restore display flags too. This
            # helper cannot move CAD geometry or change part dimensions.
            env=dict(os.environ,TEMP=str(self.runtime),TMP=str(self.runtime),PYTHONDONTWRITEBYTECODE='1')
            try:
                with (self.runtime/'batch_recovery.log').open('a',encoding='utf-8') as log:
                    subprocess.run([sys.executable,'-B','-m','swlocal.recover_batch',str(lease)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=5)
            except (OSError,subprocess.TimeoutExpired):pass

    def request(self, operation, arguments, mutating=False):
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self.close()
                self._start()
            self.sequence+=1
            request_id=self.sequence
            started=time.monotonic()
            record={'id':request_id,'operation':operation,'arguments':arguments}
            try:
                self.process.stdin.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n')
                self.process.stdin.flush()
                response=self.messages.get(timeout=self.timeout)
            except queue.Empty:
                self.close()
                raise CadError({'ok':False,'code':'CAD_TIMEOUT','operation':operation,'outcome_unknown':mutating,'retry_automatically':False,'message':'CAD did not respond in time. The bridge worker was stopped; SOLIDWORKS was left running. Inspect the application and reconnect/re-list documents before any further edit.'})
            except (OSError,ValueError) as e:
                self.close()
                raise CadError({'ok':False,'code':'BRIDGE_IO','message':str(e),'outcome_unknown':mutating,'retry_automatically':False}) from e
            if response.get('id')!=request_id:
                self.close()
                raise CadError({'ok':False,'code':'WORKER_PROTOCOL','message':'Worker disconnected or returned an unexpected response','outcome_unknown':mutating,'retry_automatically':False})
            with (self.runtime/'trace.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'id':request_id,'operation':operation,'ok':response.get('ok'),'seconds':round(time.monotonic()-started,3),'code':response.get('code')})+'\n')
            if not response.get('ok'):
                raise CadError(response)
            return response
