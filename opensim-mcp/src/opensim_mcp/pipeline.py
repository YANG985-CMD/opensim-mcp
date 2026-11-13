"""Durable verified stage checkpoints outside disposable job scratch space."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

from .core import InputError, bounded_read, environment, execute, local_path
from .process_tree import process_alive
from .projects import digest, json_bytes, prepare_submission, resolve, strict_json
from .progress import report
from .quality_report import metrics_for, write_reports


def now(): return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    # Journals are persistent state; replacements share their directory for atomicity.
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name('.' + uuid.uuid4().hex + '.writing')
    pending.write_bytes(json_bytes(value))
    try:
        for attempt in range(40):
            try: pending.replace(path); return
            except PermissionError:
                if attempt == 39: raise
                time.sleep(.025)
    finally: pending.unlink(missing_ok=True)


def source_hash():
    return digest(b''.join(p.name.encode() + p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py'))))


def canonical_parameters(value):
    if isinstance(value, str) and Path(value).is_absolute() and Path(value).is_file():
        return {'sha256': digest(bounded_read(Path(value), 64 * 1024**2)), 'suffix': Path(value).suffix.lower()}
    if isinstance(value, list): return [canonical_parameters(v) for v in value]
    if isinstance(value, dict): return {k:canonical_parameters(v) for k,v in value.items()}
    return value


def remap(value, old, new):
    if isinstance(value, str): return value.replace(str(old), str(new))
    if isinstance(value, list): return [remap(v, old, new) for v in value]
    if isinstance(value, dict): return {k:remap(v, old, new) for k,v in value.items()}
    return value


@contextmanager
def cache_lock(path):
    """Windows byte lock is automatically released when a cancelled/crashed worker exits."""
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size == 0: stream.write(b'0'); stream.flush()
        while True:
            try: stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1); break
            except OSError: report('waiting_for_stage_cache'); time.sleep(.1)
        try: yield
        finally: stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def inventory(folder):
    files = {}; size = 0
    for p in folder.rglob('*'):
        if p.is_symlink() or getattr(p, 'is_junction', lambda: False)() or not p.resolve().is_relative_to(folder.resolve()):
            raise InputError('Stage artifacts may not contain links.')
        if p.is_file():
            raw = bounded_read(p, 64 * 1024**2); size += len(raw)
            files[p.relative_to(folder).as_posix()] = {'sha256': digest(raw), 'bytes': len(raw)}
        if len(files) > 1000 or size > 256 * 1024**2: raise InputError('Stage artifact limits exceeded.')
    return files


def verified_cache(entry, key):
    if not entry.exists(): return None, 'not_found'
    try:
        metadata = strict_json(bounded_read(entry/'manifest.json', 2 * 1024**2))
        actual = inventory(entry)
        actual.pop('manifest.json', None)
        if metadata['key'] != key or actual != metadata['files']: raise InputError('Stage digest mismatch.')
        result = strict_json(bounded_read(entry/'result.json', 2 * 1024**2))
        return result, 'verified'
    except (OSError, ValueError, KeyError) as exc:
        return None, 'invalid_cache: ' + str(exc)[:300]


def aliases(workflow, result):
    files = result.get('files', [])
    def find(term):
        matches = [p for p in files if term in Path(p).name.lower()]
        if len(matches) != 1: raise InputError('Expected one output containing ' + term)
        return matches[0]
    if workflow=='rra':return {'model':result['model_file'],'motion':find('rra_coordinates.mot'),'forces':find('rra_forces.sto')}
    if workflow in {'scale','marker_placement','configure_actuators','prepare_moco_model'}: return {'model': result['model_file']}
    if workflow == 'ik': return {'motion': result['motion_file']}
    if workflow == 'id': return {'forces': find('inverse_dynamics.sto')}
    if workflow == 'static_optimization': return {'forces': find('_force.sto'), 'activations': find('_activation.sto')}
    if workflow == 'muscle_analysis': return {'lengths': find('_length.sto')}
    if workflow == 'joint_reaction': return {'reactions': find('reactionloads.sto')}
    if workflow in {'moco','moco_track','moco_inverse'}: return {k:find(n) for k,n in [('states','states.sto'),('controls','controls.sto'),('solution','solution.sto')]}
    return {}


def service_roots(cfg):
    root = local_path(os.environ.get('OPENSIM_MCP_SERVICE_RESULTS_ROOT', str(cfg.results_root)))
    if root != cfg.results_root and not any(root == p or root.is_relative_to(p) for p in cfg.allowed_roots):
        raise InputError('Pipeline service root is not server-authorized.')
    locks = local_path(os.environ.get('OPENSIM_MCP_SERVICE_TEMP_ROOT', str(cfg.temp_root))) / 'pipeline-locks'
    return root/'pipelines', locks


def update_run(root, identifier, status, **values):
    if not re.fullmatch('[0-9a-f]{32}', identifier): raise InputError('Invalid run identifier.')
    path = root/'runs'/identifier/'run.json'
    if path.exists():
        record = strict_json(bounded_read(path, 2*1024**2))
        record.update(status=status, updated_utc=now(), **values)
        atomic_json(path, record)


def get_run(cfg, run_id):
    root, _ = service_roots(cfg)
    if not re.fullmatch('[0-9a-f]{32}', run_id): raise InputError('Invalid run identifier.')
    path = root/'runs'/run_id/'run.json'
    record = strict_json(bounded_read(path, 2*1024**2))
    if record['status'] == 'running' and not process_alive(record['worker_pid']):
        update_run(root, run_id, 'interrupted'); record['status'] = 'interrupted'
    return record


def run_pipeline(cfg, project_path, resume=True, submission=None):
    from .jobs import dispatch
    from .media import plot_motion
    if type(resume) is not bool: raise InputError('resume must be boolean.')
    snapshot = submission or prepare_submission(cfg, project_path)
    if digest(bounded_read(cfg.input_path(project_path, '.json'), 1024**2)) != snapshot['project_sha256']:
        raise InputError('Project changed after submission; submit the updated project again.')
    project = snapshot['project']; root, locks = service_roots(cfg)
    identifier = os.environ.get('OPENSIM_MCP_JOB_ID', uuid.uuid4().hex)
    record = {'run_id':identifier, 'name':project['name'], 'status':'running', 'started_utc':now(),
              'worker_pid':os.getpid(), 'project_sha256':snapshot['project_sha256'], 'inputs':snapshot['inputs'], 'stages':{}}
    journal = root/'runs'/identifier/'run.json'; atomic_json(journal, record)
    try:
        with tempfile.TemporaryDirectory(prefix='pipeline-', dir=cfg.temp_root) as name:
            work = Path(name); inputs = {}
            for key, asset in snapshot['inputs'].items():
                source = cfg.input_path(asset['path'], Path(asset['path']).suffix.lower())
                raw = bounded_read(source, 64*1024**2)
                if digest(raw) != asset['sha256']: raise InputError('Input changed after submission: ' + key)
                target = work/(key + source.suffix); target.write_bytes(raw); inputs[key] = str(target)
            stage_cfg = replace(cfg, allowed_roots=(*cfg.allowed_roots, work, root), results_root=work/'outputs')
            stage_cfg.results_root.mkdir()
            runtime = environment(cfg)
            # API-only operations may coexist with CLI-driven IK/ID; record both engines.
            probe = work/'api-probe'; probe.mkdir()
            execute(cfg, ['--version'], probe, min(cfg.timeout,30), force_api=True)
            record['runtime'] = {'selected_backend':runtime['tool_backend'], 'selected_version':runtime['opensim_version'],
                                 'api_version':(probe/'cli.log').read_text(encoding='utf-8', errors='replace').strip(),
                                 'api_python':os.environ.get('OPENSIM_MCP_API_PYTHON'), 'source_sha256':source_hash()}
            outputs = {}
            for index, stage in enumerate(project['stages']):
                stage_id = stage['id']; parameters = resolve(stage['parameters'], inputs, outputs)
                canonical = canonical_parameters(parameters)
                residuals = [r for r in project['residuals'] if r['stage'] == stage_id]
                key = digest(json_bytes({'workflow':stage['workflow'], 'parameters':canonical, 'runtime':record['runtime'], 'residuals':residuals}))
                if not resume: key = digest(json_bytes({'base_key':key, 'forced_run':identifier}))
                entry = root/'cache'/key
                entry.parent.mkdir(parents=True, exist_ok=True)
                report('pipeline_stage', stage=stage_id, stage_index=index+1, stage_count=len(project['stages']))
                with cache_lock(locks/(key+'.lock')):
                    cached, reason = verified_cache(entry, key) if resume else (None, 'forced_execution')
                    reused = cached is not None
                    if cached is None:
                        result = dispatch(stage_cfg, stage['workflow'], parameters)
                        metrics = metrics_for(result, stage_id, parameters, project['residuals'])
                        with tempfile.TemporaryDirectory(prefix='cache-commit-', dir=cfg.temp_root) as commit_name:
                            pending = Path(commit_name)/'entry'; pending.mkdir()
                            # Each stage owns one generated output folder; quality runs also publish one.
                            paths = list({Path(p).parent for p in result.get('files', [])})
                            if stage['workflow'] == 'ik': paths = [Path(result['motion_file']).parent]
                            if len(paths) != 1: raise InputError('Stage output must have one artifact directory.')
                            inventory(paths[0]); shutil.copytree(paths[0], pending/'artifacts')
                            result = remap(result, paths[0], entry/'artifacts')
                            for p in (pending/'artifacts').glob('*.json'):
                                value = remap(strict_json(bounded_read(p,2*1024**2)), paths[0], entry/'artifacts')
                                p.write_bytes(json_bytes(value))
                            cached = {'result':result, 'metrics':metrics, 'outputs':aliases(stage['workflow'],result)}
                            (pending/'result.json').write_bytes(json_bytes(cached))
                            (pending/'manifest.json').write_bytes(json_bytes({'key':key,'files':inventory(pending)}))
                            if entry.exists():
                                # Invalid/forced old entry is replaced under the exclusive lock, retaining no partial cache.
                                backup = Path(commit_name)/'old'; entry.rename(backup)
                                try: pending.rename(entry)
                                except BaseException: backup.rename(entry); raise
                            else: pending.rename(entry)
                    outputs[stage_id] = cached['outputs']
                    record['stages'][stage_id] = {**cached, 'workflow':stage['workflow'], 'cache_key':key,
                                                 'reused':reused, 'cache_reason':reason, 'parameters':canonical, 'completed_utc':now()}
                    atomic_json(journal, record)
            report('building_quality_report')
            folder = cfg.results_root/('project-'+identifier); folder.mkdir(parents=True)
            plots = []
            for index, spec in enumerate(project['plots']):
                source = outputs[spec['stage']][spec['output']]
                curve = plot_motion(stage_cfg, source, spec['columns'], spec['stage'], spec['ylabel'])
                for field, suffix in [('image_file','.png'),('svg_file','.svg')]:
                    target = folder/('curve-'+str(index+1)+suffix); shutil.copyfile(curve[field],target); curve[field] = str(target)
                plots.append({**curve, 'title':spec['stage']})
            record.update(status='completed', finished_utc=now())
            reports = write_reports(folder, record, project['checks'], plots)
            atomic_json(journal, {**record, **reports})
            return {'run_id':identifier, 'run_file':str(journal), 'computed_stages':sum(not s['reused'] for s in record['stages'].values()),
                    'reused_stages':sum(s['reused'] for s in record['stages'].values()), **reports}
    except BaseException as exc:
        update_run(root, identifier, 'failed', error=str(exc)[-4000:]); raise
