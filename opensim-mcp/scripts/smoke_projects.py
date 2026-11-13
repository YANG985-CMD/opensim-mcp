"""Execute native projects twice, test threshold reuse, failed-stage recovery and cache tampering."""
import argparse
import json
import os
from pathlib import Path
import time
from opensim_mcp.core import Settings
from opensim_mcp.jobs import JobManager, TERMINAL
from opensim_mcp.projects import create_project
from opensim_mcp.pipeline import get_run


def wait(jobs, identifier):
    deadline=time.monotonic()+610
    while time.monotonic()<deadline:
        record=jobs.get(identifier)
        if record['status'] in TERMINAL:return record
        time.sleep(.2)
    raise TimeoutError('Project test exceeded deadline')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    cfg=Settings.from_env();examples=Path(__file__).resolve().parents[1]/'examples'
    config=json.loads((examples/'project.json').read_text(encoding='utf-8'))
    for a in config['inputs'].values():a['path']=str(examples/a['path'])
    project=create_project(cfg,config);jobs=JobManager(cfg);report={}
    def run(path):return wait(jobs,jobs.submit('pipeline',{'project_path':path,'resume':True},600)['job_id'])
    try:
        first=run(project['project_path']);assert first['status']=='completed',first
        second=run(project['project_path']);assert second['status']=='completed',second
        assert first['result']['computed_stages']==7 and second['result']['reused_stages']==7
        report['first']=first['result'];report['repeat']=second['result']
        config['checks'][0]['limit']=.00001
        changed=create_project(cfg,config);third=run(changed['project_path']);assert third['result']['reused_stages']==7,third
        report['threshold_change_reused_all']=True
        # Native failure occurs after a valid cached prefix; fixing the final stage resumes it.
        config['stages']=config['stages'][:2]+[{'id':'bad','workflow':'scale','parameters':{'model_path':'${inputs.model}', 'subject_mass_kg':1.,'body_scales':{'missing_body':[1.,1.,1.]}}}]
        config['checks']=[];config['plots']=[]
        bad=create_project(cfg,config);failed=run(bad['project_path']);assert failed['status']=='failed',failed
        partial=get_run(cfg,failed['job_id']);assert len(partial['stages'])==2
        config['stages'][-1]['parameters']['body_scales']={'block':[1.,1.,1.]}
        fixed=create_project(cfg,config);recovered=run(fixed['project_path']);assert recovered['status']=='completed',recovered
        assert recovered['result']['reused_stages']==2 and recovered['result']['computed_stages']==1
        report['failed_stage_resume']=True
        run_record=get_run(cfg,first['job_id']);ik=run_record['stages']['ik']
        target=Path(ik['outputs']['motion']);target.write_text(target.read_text()+'\n',encoding='utf-8')
        repaired=run(project['project_path']);assert repaired['status']=='completed',repaired
        assert repaired['result']['computed_stages']==1 and repaired['result']['reused_stages']==6
        report['tampered_cache_recomputed']=True
        report['passed']=True
    finally:jobs.close()
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'computed':7,'reused':7,'resume':True,'tamper_detected':True}))


if __name__=='__main__':main()
