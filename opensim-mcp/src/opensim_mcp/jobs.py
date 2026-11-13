"""Durable asynchronous native workflows, Windows process-tree cancellation."""
from __future__ import annotations

import atexit
from datetime import datetime,timezone
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from .core import InputError,Settings,bounded_read
from .diagnostics import diagnose_error
from .process_tree import ProcessTree,process_alive

TERMINAL={'completed','failed','cancelled','interrupted'}


def now():return datetime.now(timezone.utc).isoformat()


def dispatch(cfg,workflow,parameters,submission=None):
    if workflow in {'muscle_force_study','wearable_muscle_comparison','muscle_volumes'}:
        from .muscle_forces import force_study,compare_studies,estimate_volumes
        return {'muscle_force_study':force_study,'wearable_muscle_comparison':compare_studies,'muscle_volumes':estimate_volumes}[workflow](cfg,**parameters)
    if workflow=='prepare_moco_model':
        from .moco_model import prepare_moco_model
        return prepare_moco_model(cfg,**parameters)
    if workflow in {'moco_convergence','moco_sensitivity'}:
        from .studies import run_convergence,run_sensitivity
        return {'moco_convergence':run_convergence,'moco_sensitivity':run_sensitivity}[workflow](cfg,**parameters)
    if workflow=='rra':
        from .rra import run_rra
        return run_rra(cfg,**parameters)
    if workflow in {'moco_track','moco_inverse'}:
        from .tracking import moco_track,moco_inverse
        return {'moco_track':moco_track,'moco_inverse':moco_inverse}[workflow](cfg,**parameters)
    if workflow=='pipeline':
        from .pipeline import run_pipeline
        return run_pipeline(cfg,**parameters,submission=submission)
    if workflow in {'marker_placement','configure_actuators','actuator_usage'}:
        from .structured import place_markers,configure_actuators,assess_actuator_usage
        return {'marker_placement':place_markers,'configure_actuators':configure_actuators,'actuator_usage':assess_actuator_usage}[workflow](cfg,**parameters)
    from .core import run_ik
    from .analysis import run_analysis
    from .workflows import run_scale,run_joint_reaction,run_moco,assess_ik_quality
    if workflow=='ik':return run_ik(cfg,**parameters)
    if workflow in {'id','muscle_analysis','static_optimization'}:return run_analysis(cfg,workflow,**parameters)
    return {'scale':run_scale,'joint_reaction':run_joint_reaction,'moco':run_moco,'ik_quality':assess_ik_quality}[workflow](cfg,**parameters)


def validate_submission(workflow,parameters):
    from .core import run_ik
    from .analysis import run_analysis
    from .workflows import run_scale,run_joint_reaction,run_moco,assess_ik_quality
    if not isinstance(parameters,dict):raise InputError('parameters must be an object.')
    if len(json.dumps(parameters,allow_nan=False).encode())>1024*1024:raise InputError('Parameters exceed 1 MiB.')
    if workflow=='pipeline':
        if set(parameters)-{'project_path','resume'} or not isinstance(parameters.get('project_path'),str) or type(parameters.get('resume',True)) is not bool:
            raise InputError('pipeline accepts project_path and boolean resume only.')
        return
    if workflow=='prepare_moco_model':
        from .moco_model import prepare_moco_model
        function=prepare_moco_model;prefix=(None,)
    elif workflow in {'moco_convergence','moco_sensitivity'}:
        from .studies import run_convergence,run_sensitivity
        function={'moco_convergence':run_convergence,'moco_sensitivity':run_sensitivity}[workflow];prefix=(None,)
    elif workflow=='rra':
        from .rra import run_rra
        function=run_rra;prefix=(None,)
    elif workflow in {'moco_track','moco_inverse'}:
        from .tracking import moco_track,moco_inverse
        function={'moco_track':moco_track,'moco_inverse':moco_inverse}[workflow];prefix=(None,)
    elif workflow in {'marker_placement','configure_actuators','actuator_usage'}:
        from .structured import place_markers,configure_actuators,assess_actuator_usage
        function={'marker_placement':place_markers,'configure_actuators':configure_actuators,'actuator_usage':assess_actuator_usage}[workflow];prefix=(None,)
    elif workflow in {'muscle_force_study','wearable_muscle_comparison','muscle_volumes'}:
        from .muscle_forces import force_study,compare_studies,estimate_volumes
        function={'muscle_force_study':force_study,'wearable_muscle_comparison':compare_studies,'muscle_volumes':estimate_volumes}[workflow];prefix=(None,)
    elif workflow=='ik':function=run_ik;prefix=(None,)
    elif workflow in {'id','muscle_analysis','static_optimization'}:function=run_analysis;prefix=(None,workflow)
    elif workflow in {'scale','joint_reaction','moco','ik_quality'}:function={'scale':run_scale,'joint_reaction':run_joint_reaction,'moco':run_moco,'ik_quality':assess_ik_quality}[workflow];prefix=(None,)
    else:raise InputError('workflow must be ik, id, muscle_analysis, static_optimization, scale, joint_reaction or moco.')
    try:inspect.signature(function).bind(*prefix,**parameters)
    except TypeError as exc:raise InputError(str(exc)) from exc


class JobManager:
    def __init__(self,cfg:Settings):
        self.cfg=cfg;self.root=cfg.results_root/'jobs';self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.slots=threading.Semaphore(2);self.active={};self.closed=False
        atexit.register(self.close)

    def path(self,identifier):
        if not re.fullmatch('[0-9a-f]{32}',identifier):raise InputError('Invalid job identifier.')
        return self.root/identifier/'job.json'

    def _write(self,record):
        path=self.path(record['job_id']);temp=path.with_name(uuid.uuid4().hex+'.writing')
        temp.write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf-8')
        try:
            for attempt in range(20):
                try:temp.replace(path);return
                except PermissionError:
                    if attempt==19:raise
                    time.sleep(.05)
        finally:temp.unlink(missing_ok=True)

    def get(self,identifier):
        with self.lock:
            path=self.path(identifier)
            if not path.is_file():raise InputError('Job not found.')
            record=json.loads(bounded_read(path,2*1024*1024))
            if record['status'] not in TERMINAL and identifier not in self.active and not process_alive(record['owner_pid']):
                record.update(status='interrupted',finished_utc=now(),phase='owner_exited',
                              error={'message':'Owning MCP process exited. Its Windows Job Object terminates the native process tree.'})
                self._write(record)
            if identifier in self.active:
                work=self.active[identifier]['work'];progress=work/'progress.json'
                try:
                    actual=json.loads(bounded_read(progress,24000));record['progress']={k:v for k,v in actual.items() if k!='log_path'}
                    log=Path(actual.get('log_path',''))
                    if log.is_file() and log.resolve().is_relative_to(work.resolve()):
                        with log.open('rb') as stream:
                            stream.seek(max(0,log.stat().st_size-4000));record['native_log_tail']=stream.read(4000).decode('utf-8',errors='replace')
                except (OSError,ValueError):pass
            return record

    def list(self,limit=50,status=None):
        if type(limit) is not int or not 1<=limit<=100:raise InputError('limit must be 1..100.')
        if status and status not in TERMINAL|{'queued','preparing','running','publishing','cancelling'}:raise InputError('Unknown job status.')
        records=[]
        for path in self.root.glob('*/job.json'):
            record=self.get(path.parent.name)
            if not status or record['status']==status:
                records.append({k:record.get(k) for k in ('job_id','workflow','status','created_utc','finished_utc','phase')})
        return {'jobs':sorted(records,key=lambda r:r['created_utc'],reverse=True)[:limit]}

    def submit(self,workflow,parameters,timeout_seconds=None):
        validate_submission(workflow,parameters)
        submission=None
        if workflow=='pipeline':
            from .projects import prepare_submission
            submission=prepare_submission(self.cfg,parameters['project_path'])
        timeout=self.cfg.timeout if timeout_seconds is None else timeout_seconds
        if type(timeout) is not int or not 1<=timeout<=600:raise InputError('timeout_seconds must be 1..600.')
        with self.lock:
            if self.closed:raise InputError('Job manager is shutting down.')
            if sum(not x['done'].is_set() for x in self.active.values())>=20:raise InputError('At most 20 live/queued jobs allowed.')
            identifier=uuid.uuid4().hex;self.path(identifier).parent.mkdir()
            work=self.cfg.temp_root/('job-'+identifier);work.mkdir()
            record={'job_id':identifier,'workflow':workflow,'parameters':parameters,'status':'queued','phase':'queued',
                    'created_utc':now(),'owner_pid':os.getpid(),'timeout_seconds':timeout,
                    'progress_note':'Actual phases and native log; solver completion fraction is unknown.'}
            self._write(record)
            control={'work':work,'cancel':threading.Event(),'done':threading.Event(),'submission':submission}
            self.active[identifier]=control
            thread=threading.Thread(target=self._run,args=(record,control),daemon=True)
            control['thread']=thread;thread.start()
            return {'job_id':identifier,'status':'queued','history_file':str(self.path(identifier))}

    def cancel(self,identifier):
        with self.lock:
            record=self.get(identifier)
            if record['status'] in TERMINAL:return {'job_id':identifier,'status':record['status'],'cancelled':record['status']=='cancelled'}
            if identifier not in self.active:raise InputError('This job is owned by another live MCP process; cancel it through that connection.')
            control=self.active[identifier];control['cancel'].set()
        # Do not hold the state lock while waiting for process-tree termination.
        control['done'].wait(15)
        result=self.get(identifier)
        return {'job_id':identifier,'status':result['status'],'cancelled':result['status']=='cancelled',
                'process_tree_stopped':result.get('process_tree_stopped',False)}

    def _state(self,record,**values):
        with self.lock:record.update(**values,updated_utc=now());self._write(record)

    def _run(self,record,control):
        tree=None;process=None;acquired=False;work=control['work'];pending=self.path(record['job_id']).parent/'artifacts.pending'
        try:
            while not control['cancel'].is_set():
                if self.slots.acquire(timeout=.1):acquired=True;break
            if control['cancel'].is_set():raise InterruptedError('Cancelled before execution.')
            self._state(record,status='preparing',phase='starting_worker')
            published=work/'published';temporary=work/'scratch';temporary.mkdir();published.mkdir()
            env=dict(os.environ,TEMP=str(work),TMP=str(work),PYTHONDONTWRITEBYTECODE='1',
                     OPENSIM_MCP_ALLOWED_ROOTS=json.dumps([str(x) for x in (*self.cfg.allowed_roots,self.cfg.results_root)]),
                     OPENSIM_MCP_RESULTS_ROOT=str(published),OPENSIM_MCP_TEMP_ROOT=str(temporary),
                     OPENSIM_MCP_SERVICE_RESULTS_ROOT=str(self.cfg.results_root),OPENSIM_MCP_SERVICE_TEMP_ROOT=str(self.cfg.temp_root),
                     OPENSIM_MCP_JOB_ID=record['job_id'],
                     OPENSIM_MCP_TIMEOUT_SEC=str(record['timeout_seconds']),OPENSIM_MCP_PROGRESS_FILE=str(work/'progress.json'))
            (work/'request.json').write_text(json.dumps({'workflow':record['workflow'],'parameters':record['parameters'],'submission':control['submission']}),encoding='utf-8')
            tree=ProcessTree()
            with (work/'worker.log').open('wb') as log:
                process=tree.spawn([sys.executable,'-B','-m','opensim_mcp.job_worker',str(work)],
                                         cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                (work/'go').touch()  # No descendants may be spawned before assignment.
                self._state(record,status='running',phase='workflow_running',started_utc=now())
                started=time.monotonic()
                while process.poll() is None:
                    if control['cancel'].is_set():raise InterruptedError('Cancellation requested.')
                    if time.monotonic()-started>record['timeout_seconds']:raise TimeoutError('Whole workflow timeout exceeded.')
                    if (work/'worker.log').stat().st_size>16*1024*1024:raise InputError('Workflow log limit exceeded.')
                    time.sleep(.1)
                process.wait()
                # Stop any stray descendants before validating or publishing results.
                tree.terminate()
            if control['cancel'].is_set():raise InterruptedError('Cancelled before publication.')
            result=json.loads(bounded_read(work/'result.json',1024*1024))
            if process.returncode!=0 or not result['ok']:raise RuntimeError(result.get('error','Workflow worker failed.'))
            self._state(record,status='publishing',phase='publishing_verified_results')
            files=[p for p in published.rglob('*') if p.is_file()]
            if len(files)>1000 or sum(p.stat().st_size for p in files)>512*1024*1024:raise InputError('Published artifact limit exceeded.')
            if any(p.is_symlink() or not p.resolve().is_relative_to(published.resolve()) for p in published.rglob('*')):
                raise InputError('Artifact links are not allowed.')
            shutil.copytree(published,pending)
            destination=pending.with_name('artifacts')
            def replace(value):
                if isinstance(value,str):return value.replace(str(published),str(destination))
                if isinstance(value,list):return [replace(v) for v in value]
                if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
                return value
            for path in pending.rglob('*.json'):
                value=json.loads(bounded_read(path,1024*1024));path.write_text(json.dumps(replace(value),indent=2),encoding='utf-8')
            with self.lock:
                if control['cancel'].is_set():raise InterruptedError('Cancelled before publication commit.')
                pending.replace(destination)
                self._state(record,status='completed',phase='completed',finished_utc=now(),result=replace(result['value']),process_tree_stopped=True)
        except BaseException as exc:
            stopped=process is None
            if tree:
                try:tree.terminate();stopped=True
                except BaseException as stop_error:exc=RuntimeError(str(exc)+'; termination unconfirmed: '+str(stop_error));stopped=False
            if process:
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:stopped=False
            status='cancelled' if isinstance(exc,InterruptedError) and stopped else 'failed'
            self._state(record,status=status,phase=status,finished_utc=now(),process_tree_stopped=stopped,error=diagnose_error(str(exc)))
        finally:
            if tree:tree.close()
            if record['workflow']=='pipeline':
                from .pipeline import update_run
                try:
                    update_run(self.cfg.results_root/'pipelines',record['job_id'],record['status'],
                               **(record.get('result') or {}),job_error=record.get('error'))
                except (OSError,ValueError):pass  # A journal write must not prevent tree/scratch/slot cleanup.
            shutil.rmtree(pending,ignore_errors=True)
            shutil.rmtree(work,ignore_errors=True)
            if acquired:self.slots.release()
            control['done'].set()
            with self.lock:self.active.pop(record['job_id'],None)

    def close(self):
        with self.lock:
            self.closed=True
            controls=list(self.active.values())
            for control in controls:control['cancel'].set()
        for control in controls:control['done'].wait(15)
