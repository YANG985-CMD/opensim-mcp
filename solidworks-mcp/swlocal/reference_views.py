"""Release saved referenced-part windows without unloading assembly geometry."""
from pathlib import Path
from . import cad as n
from .resources import memory_margins


def reference_view_plan(snapshot,components):
    if not isinstance(components,list) or not 1<=len(components)<=80 or any(not isinstance(x,str) for x in components) or len(set(components))!=len(components):raise ValueError('Use 1..80 distinct exact top-level component names')
    known={row['name']:row for row in snapshot['components']}
    if set(components)-set(known):raise ValueError('Unknown component; no windows closed')
    result=[];seen=set()
    for name in components:
        path=known[name]['path']
        if not path or Path(path).suffix.lower()!='.sldprt':raise ValueError('Only saved referenced native parts are supported')
        key=Path(path).resolve()
        if key not in seen:result.append((name,path));seen.add(key)
    return result


class ReferenceViewTools:
    def close_reference_views(self,document_id,state,components):
        # This releases resources and must remain available below edit margins.
        model,before=self._edit(document_id,state)
        if before['kind']!=2:raise n.Failure('DOCUMENT_TYPE','Expected an explicit parent assembly',edit_may_be_partial=False)
        try:plan=reference_view_plan(before,components)
        except ValueError as error:raise n.Failure('VIEW_ARGUMENT',str(error),edit_may_be_partial=False) from error
        prepared=[];skipped=[];assembly_dirty=bool(n.member(model,'GetSaveFlag'));resources_before=memory_margins()
        for name,path in plan:
            part=n.member(self._component(model,name),'GetModelDoc2')
            if part is None or str(n.member(part,'GetPathName'))!=path:raise n.Failure('REFERENCE_VIEW_SCOPE','Referenced part unavailable',edit_may_be_partial=False)
            if bool(n.member(part,'GetSaveFlag')):skipped.append({'path':path,'reason':'unsaved_changes_preserved'})
            elif not bool(n.member(part,'Visible')):skipped.append({'path':path,'reason':'already_without_visible_window'})
            else:prepared.append((part,path))
        # CloseDoc may also clean hidden documents. Do not call it if a hidden
        # unsaved document could be affected, even outside this parent.
        for doc in n.member(self.sw,'GetDocuments') or []:
            if not bool(n.member(doc,'Visible')) and bool(n.member(doc,'GetSaveFlag')):raise n.Failure('UNSAVED_HIDDEN_DOCUMENT','A hidden unsaved document exists; no resource windows were closed',edit_may_be_partial=False)
        closed=[]
        try:
            for part,path in prepared:
                if n.member(part,'GetSaveFlag'):raise RuntimeError('Part changed before closing its saved window')
                self.sw.CloseDoc(path)
                retained=self.sw.GetOpenDocumentByName(path)
                if retained is None or bool(n.member(retained,'Visible')):raise RuntimeError('Expected the reference to remain loaded with its window closed')
                closed.append(path)
            self._activate(model);after=self.snapshot(document_id)
            if before['components']!=after['components'] or before['mates']!=after['mates'] or bool(n.member(model,'GetSaveFlag'))!=assembly_dirty:raise RuntimeError('Assembly state changed during reference-window cleanup')
        except Exception as error:raise n.Failure('REFERENCE_VIEW_PARTIAL',str(error),closed_windows=closed,edit_may_be_partial=True,retry_automatically=False) from error
        return {**after,'closed_reference_windows':closed,'skipped_reference_windows':skipped,'reference_geometry_remains_loaded':True,'assembly_geometry_mates_and_unsaved_flag_unchanged':True,'resources_before':resources_before,'resources_after':memory_margins(),'scope':'Close only selected saved referenced-part windows with native CloseDoc, retaining parent assembly data. Skip unsaved parts; never save/discard edits, suppress/delete components, or close the parent.'}
