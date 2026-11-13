"""Non-destructive tree folders and reference-aware delivery packaging."""
import hashlib,re
from pathlib import Path
import pythoncom
import win32com.client
from . import cad as n


def validate_groups(groups,component_names):
    if not isinstance(groups,list) or not 1<=len(groups)<=16:raise ValueError('Use 1..16 module folders')
    seen=set();names=set();result=[]
    for row in groups:
        if not isinstance(row,dict) or set(row)!={'name','components'}:raise ValueError('Each module needs name and components')
        name=row['name'];members=row['components']
        if not isinstance(name,str) or not name or len(name)>70 or any(c in name for c in '@\\/\r\n'):raise ValueError('Invalid folder name')
        if name.casefold() in names:raise ValueError('Folder names must be unique')
        if not isinstance(members,list) or not members or any(not isinstance(c,str) or c not in component_names or c in seen for c in members) or len(set(members))!=len(members):raise ValueError('Every exact component must occur in one folder only')
        names.add(name.casefold());seen.update(members);result.append((name,members))
    if seen!=set(component_names):raise ValueError('The folder plan must cover every component exactly once')
    return result


class OrganizationTools:
    def _folder_rows(self,model):
        rows=[];feature=n.member(model,'FirstFeature')
        for _ in range(3000):
            if feature is None:break
            kind=str(n.member(feature,'GetTypeName2'));name=str(n.member(feature,'Name'))
            if kind=='FtrFolder' and not name.endswith('___EndTag___'):
                raw=n.member(feature,'GetSpecificFeature2')
                if raw is not None:
                    folder=self.binding.cast(raw,'IFeatureFolder');count=int(n.member(folder,'GetFeatureCount'))
                    children=n.member(folder,'GetFeatures') or []
                    rows.append({'name':name,'feature_count':count,'members':[str(n.member(f,'Name')) for f in children]})
            feature=n.member(feature,'GetNextFeature')
        return rows

    def organize_assembly(self,document_id,state,groups,collapse=True):
        model,before=self._edit(document_id,state,2)
        if type(collapse)!=bool:raise n.Failure('ARGUMENT','collapse must be boolean',edit_may_be_partial=False)
        try:plan=validate_groups(groups,{r['name'] for r in before['components']})
        except ValueError as error:raise n.Failure('ORGANIZATION_ARGUMENT',str(error),edit_may_be_partial=False)
        if self._folder_rows(model):raise n.Failure('EXISTING_FOLDERS','Existing folders require explicit inspection; this helper does not flatten or move their contents automatically',edit_may_be_partial=False)
        proposed={name for name,_ in plan}
        if proposed.intersection(r['name'] for r in self._features(model)):raise n.Failure('FEATURE_NAME','Folder name conflicts with an existing feature',edit_may_be_partial=False)
        completed=[]
        try:
            for name,members in plan:
                components=[self._component(model,c) for c in members]
                model.ClearSelection2(True)
                if not components[0].Select4(False,None,False):raise RuntimeError('Could not select the first component')
                folder=n.member(model.FeatureManager,'InsertFeatureTreeFolder2',1)
                if folder is None:raise RuntimeError('Native component folder was not created')
                folder.Name=name;model.ClearSelection2(True)
                source=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_DISPATCH,tuple(c._raw for c in components))
                if not n.member(model,'ReorderComponents',source,folder,3):raise RuntimeError('Native component reorder failed')
                completed.append(name)
        except Exception as error:raise n.Failure('ORGANIZATION_PARTIAL',str(error),completed_folders=completed,edit_may_be_partial=True) from error
        finally:model.ClearSelection2(True)
        after=self._finish(document_id);old={r['name']:r for r in before['components']};new={r['name']:r for r in after['components']}
        if old!=new or before['mates']!=after['mates']:raise n.Failure('ORGANIZATION_CHANGED_MODEL','Tree organization changed geometry, references, fixed states or mates',edit_may_be_partial=True)
        folders=self._folder_rows(model)
        for name,members in plan:
            matches=[f for f in folders if f['name']==name]
            if len(matches)!=1 or set(matches[0]['members'])!=set(members):raise n.Failure('FOLDER_READBACK','Native folder membership differs',folder=name,actual=matches,edit_may_be_partial=True)
        if collapse:
            root=n.member(model.FeatureManager,'GetFeatureTreeRootItem2',1)
            if root is None:raise n.Failure('TREE_UNAVAILABLE','Folder organization succeeded but tree view was unavailable',edit_may_be_partial=True)
            child=n.member(root,'GetFirstChild')
            while child is not None:
                child.Expanded=False;child=n.member(child,'GetNext')
            root.Expanded=True
        return {**after,'folders':folders,'collapsed':collapse,'geometry_references_and_mates_unchanged':True,'scope':'Native FeatureManager folders only. No part merging, hierarchy change, suppression, deletion or file rename. STL shape is unchanged; compare exports when delivering.'}

    def package_assembly(self,document_id,state,destination,names,include_unsaved_assembly=False):
        model,before=self._edit(document_id,state,2)
        if type(include_unsaved_assembly) is not bool:raise n.Failure('ARGUMENT','include_unsaved_assembly must be boolean',edit_may_be_partial=False)
        source_modified=bool(n.member(model,'GetSaveFlag'))
        if not before['path'] or source_modified and not include_unsaved_assembly:raise n.Failure('UNSAVED_DOCUMENT','Source assembly has unsaved changes. Explicit include_unsaved_assembly=True copies its current state without saving the source; referenced parts must remain saved.',edit_may_be_partial=False)
        source_paths={Path(before['path']).resolve()}|{Path(c['path']).resolve() for c in before['components']}
        if any(int(n.member(n.member(c,'GetModelDoc2'),'GetType'))!=1 for c in n.member(model,'GetComponents',True)):raise n.Failure('MODEL_SCOPE','Packaging is limited to resolved top-level parts',edit_may_be_partial=False)
        for comp in n.member(model,'GetComponents',True):
            if n.member(n.member(comp,'GetModelDoc2'),'GetSaveFlag'):raise n.Failure('UNSAVED_DOCUMENT','Save all referenced parts before packaging',edit_may_be_partial=False)
        dest=Path(destination).resolve()
        self._output_path(dest/'scope_check.SLDASM',{'.sldasm'},False)
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):raise n.Failure('OUTPUT_NOT_EMPTY','Package destination must be absent or empty; no overwrite',edit_may_be_partial=False)
        if not isinstance(names,list) or len(names)!=len(source_paths):raise n.Failure('ARGUMENT','Provide one source_path/file_name row for the assembly and every referenced part',edit_may_be_partial=False)
        mapping={};used=set()
        for row in names:
            if not isinstance(row,dict) or set(row)-{'source_path','file_name','subfolder'} or not {'source_path','file_name'}<=set(row):raise n.Failure('ARGUMENT','Use source_path, file_name and optional single-level subfolder',edit_may_be_partial=False)
            source=Path(row['source_path']).resolve();name=row['file_name']
            folder=row.get('subfolder','')
            if not isinstance(folder,str) or folder and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,40}',folder):raise n.Failure('NAMING_ARGUMENT','Subfolder must be one ASCII directory name without paths',edit_may_be_partial=False)
            if source not in source_paths or source in mapping or not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{2,90}\.(?:SLDPRT|SLDASM)',name,re.I) or Path(name).suffix.lower()!=source.suffix.lower() or name.casefold() in used:raise n.Failure('NAMING_ARGUMENT','Use unique ASCII part-number/description names with matching native extensions',edit_may_be_partial=False)
            self._check_name_collision(dest/folder/name);mapping[source]=str(dest/folder/name);used.add(name.casefold())
        if set(mapping)!=source_paths:raise n.Failure('PACK_REFERENCES','Naming map must cover all native references exactly once',edit_may_be_partial=False)
        # The installed GetPackAndGo raises DISP_E_PARAMNOTOPTIONAL before
        # returning an object. Use the supported advanced reference-save API
        # explicitly; never fall back after a partial file-save operation.
        advanced=n.member(model.Extension,'GetAdvancedSaveAsOptions',3)
        if advanced is None:raise n.Failure('PACK_API','Advanced reference-save interface unavailable',edit_may_be_partial=False)
        advanced=self.binding.cast(advanced,'IAdvancedSaveAsOptions');advanced.SaveAllAsCopy=True
        advanced.SetPrefixSuffixToAll('','')
        ids,old_names,old_dirs=n.member(advanced,'GetItemsNameAndPath',None,None,None)
        paths=[Path(parent)/name for parent,name in zip(old_dirs,old_names)]
        if len(ids)!=len(paths) or len(set(paths))!=len(paths) or {p.resolve() for p in paths}!=source_paths:raise n.Failure('PACK_REFERENCES','Native advanced-save reference list differs from inspected assembly',edit_may_be_partial=False)
        targets=[mapping[p.resolve()] for p in paths]
        native=lambda vt,values:win32com.client.VARIANT(pythoncom.VT_ARRAY|vt,tuple(values))
        status=int(advanced.ModifyItemsNameAndPath(native(pythoncom.VT_I4,ids),native(pythoncom.VT_BSTR,(Path(t).name for t in targets)),native(pythoncom.VT_BSTR,(str(Path(t).parent) for t in targets))))
        if status:raise n.Failure('PACK_NAMING','Advanced reference-name assignment failed',native_status=status,edit_may_be_partial=False)
        new_ids,new_names,new_dirs=advanced.GetItemsNameAndPath(None,None,None)
        if list(new_ids)!=list(ids) or [str(Path(parent)/name) for parent,name in zip(new_dirs,new_names)]!=targets:raise n.Failure('PACK_NAMING_READBACK','Native planned names differ',edit_may_be_partial=False)
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
        dest.mkdir(parents=True,exist_ok=True)
        for target in targets:Path(target).parent.mkdir(parents=True,exist_ok=True)
        success,errors,warnings=n.out_call(model.Extension,'SaveAs3',(mapping[Path(before['path']).resolve()],0,3,None,advanced),2)
        result={'success':bool(success),'errors':errors,'warnings':warnings,'modify_names_status':status}
        # Save-as-copy can clear a native dirty flag on some versions. Restore
        # only an originally dirty flag; never save/discard the user's work.
        restored_dirty=False
        if source_modified and not bool(n.member(model,'GetSaveFlag')):
            n.member(model,'SetSaveFlag');restored_dirty=True
        modified_after=bool(n.member(model,'GetSaveFlag'))
        if not success or errors:raise n.Failure('PACK_SAVE_PARTIAL','Native advanced copy-save failed; inspect partial output before any retry',native_status=result,edit_may_be_partial=True)
        files=[]
        for source,target in mapping.items():
            p=Path(target)
            if not p.is_file() or p.stat().st_size<100:raise n.Failure('PACK_SAVE_READBACK','Expected package document is missing or empty',path=target,edit_may_be_partial=True)
            files.append({'source_path':str(source),'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        after=self.snapshot(document_id)
        if before['state']!=after['state'] or source_modified!=modified_after or any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in source_hashes.items()):raise n.Failure('PACK_CHANGED_SOURCE','Source assembly state, dirty flag or source-file hashes changed while copy-saving',edit_may_be_partial=True)
        return {'document_id':document_id,'state':after['state'],'package_assembly':mapping[Path(before['path']).resolve()],'files':files,'native_status':result,'method':'SaveAs3 / IAdvancedSaveAsOptions / SaveAllAsCopy','source_file_hashes_unchanged':True,'source_unsaved_flag_unchanged':True,'source_unsaved_flag_restored':restored_dirty,'unsaved_assembly_state_included':source_modified,'requires_reopen_reference_verification':True,'scope':'Native reference-aware renamed copied package. Source files retained and hashes verified unchanged. Reopen and verify references, poses, mates, folders and STL before delivery acceptance.'}
