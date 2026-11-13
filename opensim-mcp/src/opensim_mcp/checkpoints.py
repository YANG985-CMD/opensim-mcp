from __future__ import annotations

from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

from .core import InputError,MAX_MODEL,bounded_read,xml_model,local_path,is_under


class Checkpoints:
    def __init__(self,cfg,api):
        self.cfg,self.api=cfg,api
        self.root=cfg.results_root/'checkpoints'

    def create(self,label=''):
        if not isinstance(label,str) or len(label)>200:raise InputError('label must be at most 200 characters.')
        identifier=uuid.uuid4().hex;folder=self.root/identifier;folder.mkdir(parents=True)
        with self.api.lock:
            saved=self.api.call('save',{'destination':str(folder/'model.osim')})
            self.api.call('recovery_save',{'folder':str(folder)})
            from .session import staged_model
            data=staged_model(bounded_read(folder/'model.osim',MAX_MODEL));(folder/'model.osim').write_bytes(data)
            saved['sha256']=hashlib.sha256(data).hexdigest()
        record={**saved,'checkpoint_id':identifier,'label':label,'created_utc':datetime.now(timezone.utc).isoformat(),
                'native_state_file':'state.json','native_state_sha256':hashlib.sha256((folder/'state.json').read_bytes()).hexdigest(),
                'scope':'Model definition, all named native state variables and time; arbitrary Python variables/files and GUI are not saved.'}
        (folder/'checkpoint.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        return record

    def get(self,identifier):
        if not re.fullmatch('[0-9a-f]{32}',identifier):raise InputError('Invalid checkpoint identifier.')
        path=self.root/identifier/'checkpoint.json'
        if not is_under(local_path(path),self.cfg.results_root):raise InputError('Checkpoint resolves outside the configured result root.')
        if not path.is_file():raise InputError('Checkpoint not found.')
        return json.loads(bounded_read(path,1024*1024))

    def list(self,limit=50):
        if type(limit) is not int or not 1<=limit<=100:raise InputError('limit must be 1..100.')
        records=[]
        if self.root.is_dir():
            for path in self.root.glob('*/checkpoint.json'):
                item=self.get(path.parent.name)
                records.append({k:item[k] for k in ('checkpoint_id','label','created_utc','opensim_version','revision')})
        return {'checkpoints':sorted(records,key=lambda r:r['created_utc'],reverse=True)[:limit]}

    def restore(self,identifier,allow_version_mismatch=False):
        record=self.get(identifier);path=self.root/identifier/'model.osim'
        data=bounded_read(path,MAX_MODEL);xml_model(data)
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise InputError('Checkpoint model hash mismatch.')
        pose=record['coordinate_values']
        if not isinstance(pose,dict) or any(not isinstance(v,(float,int)) or isinstance(v,bool) or not math.isfinite(v) for v in pose.values()):
            raise InputError('Checkpoint pose is invalid.')
        value=record.get('time')
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):raise InputError('Checkpoint time is invalid.')
        with self.api.lock:
            actual=self.api.call('status')['opensim_version']
            if actual!=record['opensim_version'] and not allow_version_mismatch:
                raise InputError('Checkpoint runtime differs; explicitly allow_version_mismatch only after checking compatibility.')
            # Save a recoverable point before replacing the current model.
            status=self.api.call('status')
            previous=self.create('Before restore '+identifier) if status['model_loaded'] else None
            try:
                if record.get('native_state_file')=='state.json':
                    state_file=path.parent/'state.json'
                    if not state_file.resolve().is_relative_to(path.parent.resolve()) or hashlib.sha256(bounded_read(state_file,2*1024**2)).hexdigest()!=record['native_state_sha256']:raise InputError('Checkpoint native state hash mismatch.')
                    from .projects import strict_json
                    states=strict_json(bounded_read(state_file,2*1024**2))
                    if not isinstance(states.get('state_variables'),dict) or any(type(v) not in {int,float} or not math.isfinite(v) for v in states['state_variables'].values()):raise InputError('Invalid checkpoint native state.')
                    restored=self.api.call('recovery_restore',dict(model_file=str(path),state_file=str(state_file),source_path=str(path)))
                else:
                    self.api.load(str(path))
                    restored=self.api.call('pose',{'coordinates':pose,'time':record['time']})
            except BaseException:
                if previous:
                    if previous.get('native_state_file')=='state.json':
                        self.api.call('recovery_restore',dict(model_file=previous['model_file'],state_file=str(self.root/previous['checkpoint_id']/'state.json'),source_path=previous['model_file']))
                    else:
                        self.api.load(previous['model_file'])
                        self.api.call('pose',{'coordinates':previous['coordinate_values'],'time':previous['time']})
                raise
        return {'checkpoint_id':identifier,'api':restored,'recovery_checkpoint':previous,
                'runtime_changed':actual!=record['opensim_version'],'scope':record['scope']}
