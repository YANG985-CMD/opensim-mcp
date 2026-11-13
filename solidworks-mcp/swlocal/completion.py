"""Close one completed saved part window without discarding other work."""
import hashlib
from pathlib import Path
from . import cad as n
from .resources import memory_margins


class CompletionTools:
    def _completion_parent_states(self,path):
        """Reference/pose/mate readback, deliberately avoiding mass tessellation."""
        result={}
        for model in n.member(self.sw,'GetDocuments') or []:
            if int(n.member(model,'GetType'))!=2:continue
            components=list(n.member(model,'GetComponents',False) or [])
            if not any(str(n.member(c,'GetPathName')).casefold()==path.casefold() for c in components):continue
            key=(str(n.member(model,'GetPathName') or ''),str(n.member(model,'GetTitle')))
            result[key]={
                'configuration':str(n.member(n.member(n.member(model,'ConfigurationManager'),'ActiveConfiguration'),'Name')),
                'modified':bool(n.member(model,'GetSaveFlag')),
                'components':{str(n.member(c,'Name2')):{
                    'path':str(n.member(c,'GetPathName')),
                    'configuration':str(n.member(c,'ReferencedConfiguration')),
                    'fixed':bool(n.member(c,'IsFixed')),
                    'transform':n.rounded(n.member(n.member(c,'Transform2'),'ArrayData')),
                    'reference_loaded':n.member(c,'GetModelDoc2') is not None,
                } for c in components},
                'mates':self._mate_rows(model),
            }
        return result

    def _finish_saved_part_window(self,document_id,saved):
        """Save has succeeded. Cleanup failure must never pretend it did not."""
        status={'requested':True,'window_closed':False,'document_unloaded':False,
                'discarded_changes':False,'scope':'Only the explicitly completed saved part window.'}
        result={**saved,'window_cleanup':status}
        if saved['kind']!=1:
            status.update(status='kept_open',reason='assembly_kept_open_use_explicit_close_when_finished')
            return result
        rec=self._doc(document_id);model=rec['model'];path=str(saved['saved_path'])
        if str(n.member(model,'GetPathName'))!=path or bool(n.member(model,'GetSaveFlag')):
            status.update(status='kept_open',reason='document_changed_after_save')
            return result
        hidden=[str(n.member(m,'GetPathName') or n.member(m,'GetTitle'))
                for m in n.member(self.sw,'GetDocuments') or []
                if not bool(n.member(m,'Visible')) and bool(n.member(m,'GetSaveFlag'))]
        if hidden:
            status.update(status='kept_open',reason='hidden_unsaved_documents_preserved',blocking_documents=hidden)
            return result
        before=self.snapshot(document_id)
        if before['state']!=saved['state']:
            status.update(status='kept_open',reason='document_changed_after_save')
            return result
        parents=self._completion_parent_states(path);resources=memory_margins()
        # Recheck flags immediately before native CloseDoc; no discard or retry.
        if bool(n.member(model,'GetSaveFlag')):
            status.update(status='kept_open',reason='document_changed_before_close')
            return result
        try:
            self.sw.CloseDoc(path)
            retained=self.sw.GetOpenDocumentByName(path)
            if retained is not None:
                if bool(n.member(retained,'Visible')) or bool(n.member(retained,'GetSaveFlag')):
                    raise RuntimeError('Completed part window remains visible or became modified')
                if self.snapshot(document_id)['state']!=before['state']:
                    raise RuntimeError('Retained part geometry changed while closing its window')
            if self._completion_parent_states(path)!=parents:
                raise RuntimeError('Parent references, poses, mates or unsaved flags changed')
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=saved['sha256']:
                raise RuntimeError('Saved file changed during completion cleanup')
        except Exception as error:
            raise n.Failure('FINISH_WINDOW_PARTIAL',str(error),native_save_succeeded=True,
                            saved_path=path,saved_sha256=saved['sha256'],edit_may_be_partial=True,
                            retry_automatically=False) from error
        status.update(status='closed',window_closed=True,document_unloaded=retained is None,
                      parent_assemblies_verified=len(parents),parent_references_and_mates_unchanged=True,
                      resources_before=resources,resources_after=memory_margins())
        if retained is None:
            self.documents.pop(document_id,None);self._part_fingerprints={}
            getattr(self,'_mate_object_snapshots',{}).pop(document_id,None)
            self._component_map_cache=None
            result.update(saved_state=saved['state'],state=None,document_handle_valid=False)
        else:
            result.update(document_handle_valid=True,reference_geometry_remains_loaded=True)
        return result
