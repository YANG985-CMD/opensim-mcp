import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from opensim_mcp.core import InputError,Settings
from opensim_mcp.diagnostics import check_code
from opensim_mcp.jobs import JobManager,validate_submission
from opensim_mcp.process_tree import ProcessTree,process_alive
from opensim_mcp.workflows import run_scale,run_moco,run_joint_reaction

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


@pytest.fixture
def cfg(tmp_path):
    scratch=tmp_path/'scratch';scratch.mkdir()
    return Settings((EXAMPLES,),tmp_path/'results',scratch,None,10)


def test_code_check_never_executes_and_locates_syntax(tmp_path):
    victim=tmp_path/'must-remain';victim.write_text('original')
    assert check_code('import os\nos.remove('+repr(str(victim))+')')['executed'] is False
    assert victim.read_text()=='original'
    result=check_code('a=1\nif :\n pass','study.py')
    assert not result['valid_syntax'] and result['diagnostics'][0]['line']==2
    assert result['diagnostics'][0]['filename']=='study.py'
    assert check_code('osim.MissingClass()')['symbols'][0]['symbol']=='MissingClass'


@pytest.mark.parametrize('args',[('shell',{}),('ik',{}),('id',{'model_path':'x','coordinates_path':'y','unknown':1})])
def test_job_submission_rejects_unknown_shape(args):
    with pytest.raises((InputError,TypeError)):validate_submission(*args)


def test_queued_cancellation_and_durable_history(cfg):
    jobs=JobManager(cfg);jobs.slots.acquire();jobs.slots.acquire()
    try:
        queued=jobs.submit('ik',dict(model_path=str(EXAMPLES/'slider.osim'),marker_path=str(EXAMPLES/'slider.trc')))
        cancelled=jobs.cancel(queued['job_id'])
        assert cancelled['cancelled'] and cancelled['process_tree_stopped']
        assert not (jobs.path(queued['job_id']).parent/'artifacts').exists()
    finally:
        jobs.slots.release();jobs.slots.release();jobs.close()
    reader=JobManager(cfg)
    try:assert reader.list()['jobs'][0]['status']=='cancelled'
    finally:reader.close()


def test_exited_owner_is_interrupted_not_success(cfg):
    jobs=JobManager(cfg);identifier='a'*32;jobs.path(identifier).parent.mkdir()
    jobs._write({'job_id':identifier,'workflow':'ik','status':'running','created_utc':'2026-10-28','owner_pid':2147483647})
    try:assert jobs.get(identifier)['status']=='interrupted'
    finally:jobs.close()


def test_failed_worker_is_preserved_in_history(cfg):
    jobs=JobManager(cfg)
    try:
        submitted=jobs.submit('ik',dict(model_path=str(EXAMPLES/'missing.osim'),marker_path=str(EXAMPLES/'slider.trc')))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=jobs.get(submitted['job_id'])
            if result['status']=='failed':break
            time.sleep(.05)
        assert result['status']=='failed' and result['process_tree_stopped']
        assert 'error' in result and not (jobs.path(submitted['job_id']).parent/'artifacts').exists()
    finally:jobs.close()


@pytest.mark.skipif(os.name!='nt',reason='Windows Job Object test')
def test_owner_crash_kills_descendant_processes(tmp_path):
    metadata=tmp_path/'owner.json';script=tmp_path/'owner.py'
    script.write_text('import os,sys,json,time\nfrom pathlib import Path\n'
        'from opensim_mcp.process_tree import ProcessTree\n'
        'tree=ProcessTree()\np=tree.spawn([sys.executable,"-B","-c","import time;time.sleep(30)"],creationflags=0x08000000)\n'
        'Path(sys.argv[1]).write_text(json.dumps({"owner":os.getpid(),"child":p.pid}))\ntime.sleep(15)\n')
    process=subprocess.Popen([sys.executable,'-B',str(script),str(metadata)],creationflags=0x08000000)
    owner=None
    try:
        deadline=time.monotonic()+5
        while not metadata.exists() and time.monotonic()<deadline:time.sleep(.02)
        assert metadata.exists();record=json.loads(metadata.read_text());owner=record['owner']
        assert process_alive(record['child'])
        os.kill(owner,15)
        deadline=time.monotonic()+5
        while process_alive(record['child']) and time.monotonic()<deadline:time.sleep(.02)
        assert not process_alive(record['child'])
    finally:
        if owner and process_alive(owner):os.kill(owner,15)
        process.wait(timeout=20)


@pytest.mark.skipif(os.name!='nt',reason='Windows Job Object test')
def test_cancel_really_stops_descendants_before_side_effect(tmp_path):
    gate=tmp_path/'go';child_pid=tmp_path/'child.pid';late=tmp_path/'late'
    script=tmp_path/'tree.py'
    script.write_text('import subprocess,sys,time\nfrom pathlib import Path\n'
        'while not Path(sys.argv[1]).exists():time.sleep(.01)\n'
        'p=subprocess.Popen([sys.executable,"-B","-c",'+repr('import time;from pathlib import Path;time.sleep(3);Path('+repr(str(late))+').write_text("late")')+'])\n'
        'Path(sys.argv[2]).write_text(str(p.pid))\ntime.sleep(30)\n')
    tree=ProcessTree();process=tree.spawn([sys.executable,'-B',str(script),str(gate),str(child_pid)],creationflags=0x08000000)
    try:
        gate.touch();deadline=time.monotonic()+5
        while not child_pid.exists() and time.monotonic()<deadline:time.sleep(.02)
        assert child_pid.exists();pid=int(child_pid.read_text())
        assert process_alive(pid)
        tree.terminate();process.wait(timeout=5)
        assert tree.active_count()==0 and not process_alive(pid)
        assert not late.exists()
    finally:
        tree.close();process.wait(timeout=5)


@pytest.mark.parametrize('kwargs',[
    {'subject_mass_kg':-1,'body_scales':{'block':[1,1,1]}},
    {'subject_mass_kg':2,'body_scales':{'block':[1,float('nan'),1]}},
    {'subject_mass_kg':2,'body_scales':{'block':[1,10,1]}},
    {'subject_mass_kg':2},
    {'subject_mass_kg':2,'static_marker_path':'unpaired.trc'},
])
def test_scale_rejects_invalid_requests_before_native(cfg,monkeypatch,kwargs):
    import opensim_mcp.workflows as module
    monkeypatch.setattr(module,'_run',lambda *a,**k:pytest.fail('Invalid request reached native code'))
    with pytest.raises(InputError):run_scale(cfg,str(EXAMPLES/'slider.osim'),**kwargs)


@pytest.mark.parametrize('change',[
    {'final_time':0}, {'mesh_intervals':1000}, {'constraint_tolerance':0},
    {'state_bounds':{'/x':{'bounds':[1,-1]}}},
    {'state_bounds':{'/x':{'bounds':[0,1],'initial':[2]}}}, {'control_effort_weight':0}
])
def test_moco_rejects_invalid_requests_before_native(cfg,monkeypatch,change):
    import opensim_mcp.workflows as module
    monkeypatch.setattr(module,'_run',lambda *a,**k:pytest.fail('Invalid request reached native code'))
    request=json.loads((EXAMPLES/'moco_problem.json').read_text());request.update(change)
    with pytest.raises(InputError):run_moco(cfg,str(EXAMPLES/'moco_slider.osim'),**request)


def test_joint_reaction_requires_actuator_force_assumption(cfg,monkeypatch):
    import opensim_mcp.analysis as module
    monkeypatch.setattr(module,'execute',lambda *a,**k:pytest.fail('Missing forces reached native code'))
    with pytest.raises(InputError,match='forces_path'):
        run_joint_reaction(cfg,str(EXAMPLES/'muscle_slider.osim'),str(EXAMPLES/'muscle_slider_static.mot'),no_external_loads=True)


def test_pipeline_can_read_generated_results_but_not_neighbor(cfg,tmp_path):
    cfg.results_root.mkdir();saved=cfg.results_root/'saved.osim';saved.write_bytes((EXAMPLES/'slider.osim').read_bytes())
    assert cfg.input_path(str(saved),'.osim')==saved
    outside=tmp_path/'neighbor.osim';outside.write_bytes(saved.read_bytes())
    with pytest.raises(InputError):cfg.input_path(str(outside),'.osim')


def test_native_filter_time_rounding_is_bounded_without_losing_samples():
    from opensim_mcp.analysis import validate_sample_times
    expected=[.4+i/60 for i in range(73)]
    rounded=[t-2.4e-7-i*6.7e-9 for i,t in enumerate(expected)]
    assert validate_sample_times(rounded,expected,1.6e-6)<1e-6
    with pytest.raises(InputError):validate_sample_times(rounded[1:],expected,1.6e-6)
    with pytest.raises(InputError):validate_sample_times([t+.001 for t in rounded],expected,1.6e-6)


def test_quality_interpolation_requires_opt_in_and_has_correct_sample_values(cfg,monkeypatch):
    import opensim_mcp.workflows as module
    cfg.results_root.mkdir();motion=cfg.results_root/'shifted.mot'
    motion.write_text('shifted\ninDegrees=no\nendheader\ntime slider_tx\n0.05 0.005\n0.15 0.015\n')
    def capture(*args,**kwargs):return args[3]
    monkeypatch.setattr(module,'_run',capture)
    with pytest.raises(InputError,match='interpolation=linear'):
        module.assess_ik_quality(cfg,str(EXAMPLES/'slider.osim'),str(motion),str(EXAMPLES/'slider.trc'))
    result=module.assess_ik_quality(cfg,str(EXAMPLES/'slider.osim'),str(motion),str(EXAMPLES/'slider.trc'),interpolation='linear')
    assert result['interpolated_frames']==2
    assert result['frames'][0]['markers']['M1'][0]==pytest.approx(.005)
    assert result['frames'][1]['markers']['M1'][0]==pytest.approx(.015)
    assert '0.05 0.005' in motion.read_text()


def test_corrupted_checkpoint_rejected_before_native_restore(cfg):
    from opensim_mcp.checkpoints import Checkpoints
    class NoNative:
        def call(self,*args,**kwargs):pytest.fail('Corrupt checkpoint reached the API')
    checkpoints=Checkpoints(cfg,NoNative());identifier='b'*32;folder=checkpoints.root/identifier;folder.mkdir(parents=True)
    (folder/'model.osim').write_bytes((EXAMPLES/'slider.osim').read_bytes())
    (folder/'checkpoint.json').write_text(json.dumps({'sha256':'0'*64}))
    with pytest.raises(InputError,match='hash mismatch'):checkpoints.restore(identifier)


@pytest.mark.skipif(os.name!='nt',reason='Windows file sharing behavior')
def test_progress_reader_lock_does_not_abort_workflow(tmp_path,monkeypatch):
    from opensim_mcp.progress import report
    path=tmp_path/'progress.json';path.write_text('{"phase":"previous"}')
    monkeypatch.setenv('OPENSIM_MCP_PROGRESS_FILE',str(path))
    with path.open('rb'):
        report('next')
        assert json.loads(path.read_text())['phase']=='previous'
    report('next')
    assert json.loads(path.read_text())['phase']=='next'
