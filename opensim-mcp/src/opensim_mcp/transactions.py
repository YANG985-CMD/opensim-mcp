"""Preview and commit bounded parameter batches with persistent recovery checkpoints."""
import re
import uuid
from .core import InputError, bounded_read
from .pipeline import atomic_json, now
from .projects import strict_json


def validate_edits(edits,expected_revision):
    if type(expected_revision) is not int or expected_revision<0:raise InputError('expected_revision must be the observed nonnegative revision.')
    if not isinstance(edits,list) or not 1<=len(edits)<=50:raise InputError('Provide 1..50 structured parameter edits.')
    required={'component_type','component_name','property_name','value'}
    for edit in edits:
        if not isinstance(edit,dict) or set(edit)!=required:raise InputError('Each edit requires component_type, component_name, property_name and value.')
        if any(not isinstance(edit[k],str) or not edit[k] or len(edit[k])>200 for k in required-{'value'}):raise InputError('Invalid edit identity.')


class Transactions:
    def __init__(self,cfg,api,checkpoints):self.cfg=cfg;self.api=api;self.checkpoints=checkpoints;self.root=cfg.results_root/'edit-journal'

    def apply(self,edits,expected_revision,dry_run=True,label=''):
        validate_edits(edits,expected_revision)
        if type(dry_run) is not bool or not isinstance(label,str) or len(label)>200:raise InputError('Invalid dry_run or label.')
        with self.api.lock:
            preview=self.api.call('transaction',dict(edits=edits,expected_revision=expected_revision,dry_run=True))
            if dry_run:return dict(preview,dry_run=True,committed=False)
            identifier=uuid.uuid4().hex;self.root.mkdir(parents=True,exist_ok=True)
            recovery=self.checkpoints.create('Before transaction '+identifier)
            record={'transaction_id':identifier,'label':label,'created_utc':now(),'status':'prepared',
                    'expected_revision':expected_revision,'edits':edits,'before_checkpoint':recovery['checkpoint_id']}
            atomic_json(self.root/(identifier+'.json'),record)
            try:
                result=self.api.call('transaction',dict(edits=edits,expected_revision=expected_revision,dry_run=False))
                record.update(status='committed',result=result,finished_utc=now())
                atomic_json(self.root/(identifier+'.json'),record)
                return {**result,'transaction_id':identifier,'before_checkpoint':recovery['checkpoint_id'],'journal_file':str(self.root/(identifier+'.json'))}
            except BaseException as exc:
                # The native batch itself is atomic; a save/log failure after commit is recoverable via the stored checkpoint.
                record.update(status='attention_required',error=str(exc)[-2000:]);atomic_json(self.root/(identifier+'.json'),record);raise

    def list(self,limit=50):
        if type(limit) is not int or not 1<=limit<=100:raise InputError('limit must be 1..100.')
        records=[]
        for path in self.root.glob('*.json'):
            record=strict_json(bounded_read(path,1024**2));records.append({k:record.get(k) for k in ('transaction_id','label','status','created_utc','before_checkpoint')})
        return {'transactions':sorted(records,key=lambda r:r['created_utc'],reverse=True)[:limit]}

    def rollback(self,identifier,expected_revision):
        if type(expected_revision) is not int or expected_revision<0:raise InputError('Expected a nonnegative integer revision.')
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise InputError('Invalid transaction identifier.')
        path=self.root/(identifier+'.json');record=strict_json(bounded_read(path,1024**2))
        with self.api.lock:
            if self.api.call('status')['revision']!=expected_revision:raise InputError('Revision changed; refresh before rollback.')
            result=self.checkpoints.restore(record['before_checkpoint'],False)
            record.update(status='rolled_back',rollback_utc=now());atomic_json(path,record)
        return {'transaction_id':identifier,'status':'rolled_back','restore':result}
