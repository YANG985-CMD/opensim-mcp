"""Complete assembly/part pose updates with frozen display and bounded recovery."""
import json,math
from pathlib import Path
from . import cad as n
from .native_batch import process_id


class PoseUpdateTools:
    def set_assembly_pose(self,document_id,state,positions,part_dimensions):
        model,before=self._edit(document_id,state,2)
        if not isinstance(positions,list) or not 1<=len(positions)<=16 or not isinstance(part_dimensions,list) or len(part_dimensions)>8:raise n.Failure('ARGUMENT','Use 1..16 positions and at most 8 explicit part-dimension requests',edit_may_be_partial=False)
        mates={r['name']:r for r in before['mates']};objects=self._mate_objects_for_snapshot(document_id,before);pose_dims=[];seen=set()
        for item in positions:
            if not isinstance(item,dict) or set(item)!={'mate_name','value'} or item['mate_name'] in seen:raise n.Failure('ARGUMENT','Invalid or duplicate pose driver',edit_may_be_partial=False)
            r=mates.get(item['mate_name']);v=float(item['value'])
            if r is None or r['mate_type'] not in (5,6) or r['suppressed'] or r['dimension_driven_state']!=2:raise n.Failure('MATE_NAME','Choose active native driving mates',edit_may_be_partial=False)
            if not math.isfinite(v) or not 0<=v<=(180 if r['mate_type']==6 else 5000) or r['is_limit'] and not r['minimum']-1e-8<=v<=r['maximum']+1e-8:raise n.Failure('MATE_LIMIT','A target is outside native bounds; update not started',edit_may_be_partial=False)
            dim=n.member(n.member(objects[r['name']][1],'DisplayDimension'),'GetDimension2',0);pose_dims.append((dim,float(n.member(dim,'SystemValue'))));seen.add(r['name'])
        referenced={Path(r['path']).resolve() for r in before['components']};prepared=[];part_ids=set()
        for item in part_dimensions:
            if not isinstance(item,dict) or set(item)!={'document_id','state','dimensions'} or item['document_id'] in part_ids:raise n.Failure('ARGUMENT','Use distinct part requests with document_id, state and dimensions',edit_may_be_partial=False)
            part,old=self._edit(item['document_id'],item['state'],1)
            if not old['path'] or Path(old['path']).resolve() not in referenced:raise n.Failure('POSE_PART_SCOPE','Only saved parts directly referenced by this assembly may be updated',edit_may_be_partial=False)
            allowed={d['name'] for f in self._features(part,True) for d in f.get('dimensions',[])};values=item['dimensions'];used=set();dims=[]
            if not isinstance(values,list) or not 1<=len(values)<=16:raise n.Failure('ARGUMENT','Use 1..16 dimensions per referenced part',edit_may_be_partial=False)
            for value in values:
                if not isinstance(value,dict) or set(value)!={'dimension_name','value_si'} or value['dimension_name'] not in allowed or value['dimension_name'] in used:raise n.Failure('DIMENSION_NAME','Use distinct exact current dimension names',edit_may_be_partial=False)
                v=float(value['value_si']);name=value['dimension_name']
                if not math.isfinite(v) or not 0<v<=100:raise n.Failure('DIMENSION_VALUE','Invalid native SI dimension',edit_may_be_partial=False)
                dim=part.Parameter(name)
                if dim is None:raise n.Failure('DIMENSION_MISSING','Native dimension unavailable',edit_may_be_partial=False)
                dims.append((dim,float(n.member(dim,'SystemValue'))));used.add(name)
            prepared.append((item,part,old,dims));part_ids.add(item['document_id'])
        views=[];lease=self.scratch/'pose_display_lease.json'
        if lease.exists():raise n.Failure('POSE_DISPLAY_RECOVERY','A previous display recovery is pending; reconnect before editing',edit_may_be_partial=False)
        for doc in [model]+[p for _,p,_,_ in prepared]:
            raw=n.member(doc,'ActiveView')
            if raw is not None:
                view=self.binding.cast(raw,'IModelView');views.append((doc,view,bool(n.member(view,'EnableGraphicsUpdate'))))
        lease.write_text(json.dumps({'pid':process_id(self.sw),'views':[{'path':str(n.member(doc,'GetPathName')),'enabled':enabled} for doc,view,enabled in views]}),encoding='utf-8')
        changed=[];started=False
        try:
            for doc,view,enabled in views:view.EnableGraphicsUpdate=False
            self._activate(model);started=True
            self.set_mate_positions(document_id,before['state'],positions)
            for item,part,old,dims in prepared:changed.append(self.set_dimensions(item['document_id'],item['state'],item['dimensions']))
            self._activate(model);after=self._finish(document_id);self._verify_rigid_connections(before,after)
            result={**after,'changed_parts':changed,'complete_pose_update':True,'scope':'Referenced-part dimensions and assembly drivers updated within one tool call; display is refreshed only after completion. Not dynamics. Ordinary native failures attempt bounded restoration of captured parameters; a timeout still requires explicit inspection/recovery.'}
        except Exception as error:
            rolled_back=False;recovery_error=None
            if started:
                try:
                    for item,part,old,dims in prepared:
                        for dim,value in dims:dim.SystemValue=value
                        if not part.ForceRebuild3(False):raise RuntimeError('Part restoration rebuild failed')
                    for dim,value in pose_dims:dim.SystemValue=value
                    self._activate(model);restored=self._finish(document_id);oldposes={r['name']:r['transform'] for r in before['components']}
                    if not all(max(abs(a-b) for a,b in zip(oldposes[r['name']],r['transform']))<1e-7 for r in restored['components']):raise RuntimeError('Restored component positions differ')
                    if any(abs(float(n.member(dim,'SystemValue'))-v)>1e-9 for item,part,old,dims in prepared for dim,v in dims):raise RuntimeError('Restored part dimensions differ')
                    if any(abs(float(n.member(dim,'SystemValue'))-v)>1e-9 for dim,v in pose_dims):raise RuntimeError('Restored assembly positions differ')
                    rolled_back=True
                except Exception as failure:recovery_error=str(failure)
            raise n.Failure('POSE_UPDATE_FAILED',str(error),restored_captured_parameters=rolled_back,recovery_error=recovery_error,edit_may_be_partial=started and not rolled_back,retry_automatically=False) from error
        finally:
            restored_display=True
            for doc,view,enabled in views:
                try:view.EnableGraphicsUpdate=enabled
                except Exception:restored_display=False
            try:self._activate(model);model.GraphicsRedraw2()
            except Exception:restored_display=False
            if restored_display:lease.unlink(missing_ok=True)
        if not restored_display:raise n.Failure('POSE_DISPLAY_RECOVERY','Geometry was updated, but a display flag/redraw could not be restored. Inspect the model and reconnect to restore recorded view flags.',geometry_updated=True,edit_may_be_partial=True,retry_automatically=False)
        return result
