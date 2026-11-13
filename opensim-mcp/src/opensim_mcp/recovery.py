"""Durable named native-state snapshots, explicit recovery and bounded retention."""
import json,math,os,re,uuid
from pathlib import Path
from .core import InputError,MAX_MODEL,bounded_read,local_path
from .projects import digest,strict_json
from .pipeline import atomic_json,now

class Recovery:
    def __init__(self,cfg,api):
        self.cfg,self.api=cfg,api;self.root=cfg.results_root/'session-recovery';self.owner_id=uuid.uuid4().hex;self.latest=None

    def capture(self,reason):
        identifier=uuid.uuid4().hex;folder=self.root/identifier;folder.mkdir(parents=True)
        try:
            saved=self.api.call('recovery_save',dict(folder=str(folder)))
            from .session import staged_model
            model=staged_model(bounded_read(folder/'model.osim',MAX_MODEL));(folder/'model.osim').write_bytes(model)
            state=bounded_read(folder/'state.json',2*1024**2);states=strict_json(state)
            if states['state_count']!=len(states['state_variables']):raise InputError('Incomplete recovery state.')
            record=dict(saved,snapshot_id=identifier,owner_id=self.owner_id,owner_pid=os.getpid(),reason=reason,created_utc=now(),
                model_sha256=digest(model),state_sha256=digest(state),model_file=str(folder/'model.osim'),state_file=str(folder/'state.json'),
                scope='Model definition, all named native state variables and time. Python variables, files, GUI state and external effects are not restored.')
            atomic_json(folder/'snapshot.json',record);self.latest=identifier;self.prune()
            return dict(status='saved',snapshot_id=identifier,state_count=states['state_count'])
        except Exception as exc:
            # A failed snapshot must not turn a successful native edit into a
            # false edit failure. Older verified snapshots remain recoverable.
            return dict(status='failed',reason=str(exc)[-1000:])

    def records(self):
        rows=[]
        for path in self.root.glob('*/snapshot.json'):
            try:
                if not path.resolve().is_relative_to(self.root.resolve()):continue
                rows.append(strict_json(bounded_read(path,1024**2)))
            except (OSError,ValueError):continue
        return sorted(rows,key=lambda r:r.get('created_utc',''),reverse=True)

    def status(self,limit=20):
        if type(limit) is not int or not 1<=limit<=100:raise InputError('Recovery list limit must be 1..100.')
        return dict(current_owner_id=self.owner_id,current_owner_latest=self.latest,
            snapshots=[{k:r.get(k) for k in ('snapshot_id','created_utc','reason','model_name','state_count','opensim_version','owner_id','owner_pid')} for r in self.records()[:limit]],
            restoration_requires_explicit_snapshot_id=True,scope='No automatic cross-chat model selection or arbitrary Python replay.')

    def prune(self):
        own=[r for r in self.records() if r.get('owner_id')==self.owner_id]
        for record in own[10:]:
            folder=self.root/record['snapshot_id']
            if folder.is_symlink() or not folder.resolve().is_relative_to(self.root.resolve()):continue
            # Remove only our exact managed files; unexpected contents block
            # pruning instead of recursively deleting a user-added directory.
            if set(p.name for p in folder.iterdir())-{'model.osim','state.json','snapshot.json'}:continue
            try:
                for name in ('model.osim','state.json','snapshot.json'):(folder/name).unlink(missing_ok=True)
                folder.rmdir()
            except OSError:pass

    def restore(self,identifier,discard_current=False):
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier) or type(discard_current) is not bool:raise InputError('Explicit snapshot identifier and boolean discard_current required.')
        folder=self.root/identifier
        if folder.is_symlink() or not folder.resolve().is_relative_to(self.root.resolve()):raise InputError('Recovery path resolves outside state root.')
        if any(not (folder/n).resolve().is_relative_to(folder.resolve()) for n in ('snapshot.json','model.osim','state.json')):raise InputError('Recovery files resolve outside their snapshot.')
        record=strict_json(bounded_read(folder/'snapshot.json',1024**2));model=bounded_read(folder/'model.osim',MAX_MODEL);state=bounded_read(folder/'state.json',2*1024**2)
        if digest(model)!=record['model_sha256'] or digest(state)!=record['state_sha256']:raise InputError('Recovery model/state hash mismatch.')
        state_data=strict_json(state)
        if not isinstance(state_data.get('state_variables'),dict) or len(state_data['state_variables'])!=state_data.get('state_count') or any(type(v) not in {int,float} or not math.isfinite(v) for v in state_data['state_variables'].values()):raise InputError('Invalid recovery native state values.')
        with self.api.lock:
            status=self.api.call('status')
            if status['opensim_version']!=record['opensim_version']:raise InputError('Recovery native runtime differs; use an explicitly validated migration instead.')
            if status['model_loaded'] and not discard_current:raise InputError('Current API model exists; explicitly set discard_current=true to replace it.')
            previous=self.capture('before explicit recovery') if status['model_loaded'] else None
            result=self.api.call('recovery_restore',dict(model_file=str(folder/'model.osim'),state_file=str(folder/'state.json'),source_path=record.get('source_path')))
            return dict(snapshot_id=identifier,api=result,previous_recovery=previous,scope=record['scope'])
