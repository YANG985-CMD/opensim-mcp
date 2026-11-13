"""Bounded native assembly operations; no arbitrary command dispatch.

All native mutations are state-guarded. Movement uses the mate solver rather
than overwriting Transform2. The public result distinguishes attempted motion
from achieved motion; it never labels an assembly as a dynamic simulation.
"""
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from . import cad as n
from .geometry import incremental_transform, validate_mate_values,relative_component_pose


class MechanismTools:
    def _reference_planes(self, child):
        rows=[];feature=n.member(child,'FirstFeature')
        for _ in range(2000):
            if feature is None:break
            if n.member(feature,'GetTypeName2')=='RefPlane':
                plane=self.binding.cast(n.member(feature,'GetSpecificFeature2'),'IRefPlane')
                t=n.member(n.member(plane,'Transform'),'ArrayData')
                rows.append({'plane_name':str(n.member(feature,'Name')),
                  'point_mm':n.rounded(t[9:12],1000),'normal':n.rounded(t[6:9])})
            feature=n.member(feature,'GetNextFeature')
        return rows

    def _mate_rows(self,model,with_objects=False):
        rows=[];objects={};seen=set()
        def walk(feature,sub=False,depth=0):
            steps=0
            while feature is not None and steps<2000 and len(rows)<1000:
                steps+=1;name=str(n.member(feature,'Name'));kind=str(n.member(feature,'GetTypeName2'))
                key=(name,kind)
                if key not in seen:
                    seen.add(key)
                    if kind.startswith('Mate') and kind!='MateGroup':
                        raw=n.member(feature,'GetSpecificFeature2')
                        if raw is not None:
                            mate=self.binding.cast(raw,'IMate2')
                            error=n.member(feature,'GetErrorCode2',False)
                            error_code=int(error[0]) if isinstance(error,tuple) else int(error)
                            warning=bool(error[1]) if isinstance(error,tuple) and len(error)>1 else False
                            refs=[]
                            for i in range(int(n.member(mate,'GetMateEntityCount'))):
                                ent=n.member(mate,'MateEntity',i);comp=n.member(ent,'ReferenceComponent')
                                refs.append({'component':str(n.member(comp,'Name2')) if comp is not None else None,
                                  'reference_type':int(n.member(ent,'ReferenceType2'))})
                            row={'name':name,'feature_type':kind,'mate_type':int(n.member(mate,'Type')),
                              'alignment':int(n.member(mate,'Alignment')),'references':refs,
                              'native_error':error_code,'native_warning':warning}
                            row['can_flip']=bool(n.member(mate,'CanBeFlipped'))
                            row['flipped']=bool(n.member(mate,'Flipped')) if row['can_flip'] else None
                            suppression=n.member(feature,'IsSuppressed2',1,None)
                            row['suppressed']=bool(suppression[0]) if isinstance(suppression,(tuple,list)) and suppression else bool(suppression)
                            dtype={5:'IDistanceMateFeatureData',6:'IAngleMateFeatureData',1:'IConcentricMateFeatureData'}.get(row['mate_type'])
                            if dtype:
                                definition=self.binding.cast(n.member(feature,'GetDefinition'),dtype)
                                if row['mate_type'] in (5,6):
                                    is_angle=row['mate_type']==6;factor=180/math.pi if is_angle else 1000
                                    stem='Angle' if is_angle else 'Distance'
                                    row.update(is_limit=bool(n.member(definition,'IsAdvancedMate')),
                                      value=float(n.member(definition,stem))*factor,
                                      minimum=float(n.member(definition,'Minimum'+stem))*factor,
                                      maximum=float(n.member(definition,'Maximum'+stem))*factor,
                                      unit='deg' if is_angle else 'mm')
                                    display=n.member(mate,'DisplayDimension')
                                    row['dimension_driven_state']=int(n.member(n.member(display,'GetDimension2',0),'DrivenState')) if display is not None else None
                                else:row['lock_rotation']=bool(n.member(definition,'LockRotation'))
                            rows.append(row);objects[name]=(feature,mate)
                    if depth<8 and kind!='Reference':walk(n.optional(feature,'GetFirstSubFeature'),True,depth+1)
                feature=n.optional(feature,'GetNextSubFeature' if sub else 'GetNextFeature')
        walk(n.member(model,'FirstFeature'))
        return (rows,objects) if with_objects else rows

    def _dof(self,comp):
        status=int(n.member(comp,'GetConstrainedStatus'))
        result={'native_constraint_status':status,'constraint_status':{1:'unknown',2:'under_constrained',3:'fully_constrained',4:'over_constrained',5:'no_solution',6:'invalid_solution',7:'autosolve_off'}.get(status,'unknown'),
          'fixed':bool(n.member(comp,'IsFixed'))}
        try:
            raw=n.member(comp,'GetRemainingDOFs',0,None,0,None,0,None,0,None,0,None,0,None)
            if not isinstance(raw,tuple) or len(raw)!=13:raise ValueError('Unexpected native DOF output shape')
            return_code=int(raw[0]);details={}
            for name,offset,interface,scale in [('rotation_point_1',1,'IMathPoint',1000),('rotation_axis_1',3,'IMathVector',1),('rotation_point_2',5,'IMathPoint',1000),('rotation_axis_2',7,'IMathVector',1),('translation_axis_1',9,'IMathVector',1),('translation_axis_2',11,'IMathVector',1)]:
                obj=raw[offset+1]
                details[name]={'native_status':int(raw[offset]),'value':n.rounded(n.member(self.binding.cast(obj,interface),'ArrayData'),scale) if obj is not None else None}
            result.update(remaining_dof_count=0 if result['fixed'] else None,
              native_dof_return_code=return_code,
              native_dof_availability={0:'restricted',1:'unrestricted',2:'unavailable',3:'failed',4:'root_component'}.get(return_code,'unknown'),
              native_dof_details=details,dof_source='IComponent2.GetRemainingDOFs',
              dof_count_note='The native return code is swRemainingDofs_e, not a count. No unconstrained-axis count is invented from it; verify motion with the mate solver.')
        except Exception as error:
            result.update(remaining_dof_count=None,dof_unavailable_reason=type(error).__name__+': '+str(error)[:300])
        return result

    def assembly_status(self,document_id):
        model=self._doc(document_id)['model']
        if int(n.member(model,'GetType'))!=2:raise n.Failure('DOCUMENT_TYPE','Expected assembly',edit_may_be_partial=False)
        snapshot=self.snapshot(document_id);mates=snapshot['mates']
        components=[{'name':str(n.member(c,'Name2')),**self._dof(c)} for c in n.member(model,'GetComponents',True) or []]
        bad=[r for r in mates if not r['suppressed'] and r['native_error'] and not r['native_warning']]
        return {'document_id':document_id,'state':snapshot['state'],'mates':mates,'components':components,
          'module_folders':self._folder_rows(model),
          'position_drivers':[{'mate_name':r['name'],'value':r['value'],'minimum':r['minimum'],'maximum':r['maximum'],'unit':r['unit'],'is_limit':r['is_limit']} for r in mates if r['mate_type'] in (5,6) and not r['suppressed']],
          'native_mate_error_count':len(bad),'invalid_components':[c['name'] for c in components if c['native_constraint_status'] in (4,5,6)],
          'scope':'Native current-configuration kinematics. Use position drivers for native distance/angle mates; constraint status alone does not prove manual drag or a correct connected mechanism.'}

    def _assembly_status_for_snapshot(self,document_id,snapshot):
        model=self._doc(document_id)['model'];mates=snapshot['mates'];fixed={r['name']:r['fixed'] for r in snapshot['components']};components=[]
        for comp in n.member(model,'GetComponents',True) or []:
            name=str(n.member(comp,'Name2'));status=int(n.member(comp,'GetConstrainedStatus'))
            components.append({'name':name,'native_constraint_status':status,'fixed':fixed[name]})
        return {'document_id':document_id,'state':snapshot['state'],'components':components,
          'native_mate_error_count':sum(bool(r['native_error'] and not r['native_warning']) for r in mates if not r['suppressed']),
          'invalid_components':[r['name'] for r in components if r['native_constraint_status'] in (4,5,6)]}

    def _mate_objects_for_snapshot(self,document_id,snapshot):
        cached=getattr(self,'_mate_object_snapshots',{}).get(document_id)
        if cached and cached[0]==snapshot['state']:return cached[1]
        return self._mate_rows(self._doc(document_id)['model'],True)[1]

    def set_component_fixed(self,document_id,state,component_name,fixed):
        model,before=self._edit(document_id,state,2)
        if type(fixed)!=bool:raise n.Failure('ARGUMENT','fixed must be a boolean',edit_may_be_partial=False)
        comp=self._component(model,component_name)
        if bool(n.member(comp,'IsFixed'))!=fixed:
            if not comp.Select4(False,None,False):raise n.Failure('COMPONENT_SELECTION','Could not select the exact component',edit_may_be_partial=False)
            try:n.member(model,'FixComponent' if fixed else 'UnfixComponent')
            finally:model.ClearSelection2(True)
        after=self._finish(document_id)
        if bool(n.member(comp,'IsFixed'))!=fixed:raise n.Failure('COMPONENT_READBACK','Native fixed/float readback differs',edit_may_be_partial=True)
        return {**after,'component_name':component_name,'fixed':fixed,'constraint':self._dof(comp)}

    def set_mate_suppressed(self,document_id,state,mate_name,suppressed):
        model,before=self._edit(document_id,state,2)
        if type(suppressed)!=bool:raise n.Failure('ARGUMENT','suppressed must be boolean',edit_may_be_partial=False)
        matches=[r for r in before['mates'] if r['name']==mate_name]
        if len(matches)!=1:raise n.Failure('MATE_NAME','Choose an exact mate name from the current inspection',edit_may_be_partial=False)
        objects=self._mate_objects_for_snapshot(document_id,before);feature,_=objects[mate_name]
        if matches[0]['suppressed']!=suppressed:
            if not n.member(feature,'SetSuppression2',0 if suppressed else 1,1,None):raise n.Failure('MATE_SUPPRESSION','Native suppression call failed',edit_may_be_partial=True)
        after=self._finish(document_id);row=next(r for r in after['mates'] if r['name']==mate_name)
        if row['suppressed']!=suppressed:raise n.Failure('MATE_SUPPRESSION_READBACK','Suppression state differs',edit_may_be_partial=True)
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['native_mate_error_count'] or status['invalid_components']:raise n.Failure('ASSEMBLY_INVALID','Suppression changed but active constraints remain invalid',status=status,edit_may_be_partial=True)
        return {**after,'changed_mate':row,'scope':'Current native assembly configuration only; retained feature can be restored by exact name. No dependency-wide suppression or geometry deletion.'}

    def set_mate_flips(self,document_id,state,flips):
        model,before=self._edit(document_id,state,2)
        if not isinstance(flips,list) or not 1<=len(flips)<=16:raise n.Failure('ARGUMENT','Provide 1..16 exact mate flips',edit_may_be_partial=False)
        known={r['name']:r for r in before['mates']};objects=self._mate_objects_for_snapshot(document_id,before);prepared=[];seen=set()
        for item in flips:
            if not isinstance(item,dict) or set(item)!={'mate_name','flipped'} or type(item['flipped'])!=bool or item['mate_name'] in seen:raise n.Failure('ARGUMENT','Use distinct {mate_name,flipped:bool} rows',edit_may_be_partial=False)
            r=known.get(item['mate_name'])
            if r is None or r['mate_type'] not in (5,6) or r['suppressed'] or not r['can_flip']:raise n.Failure('MATE_FLIP','Choose an active flippable distance/angle mate',edit_may_be_partial=False)
            seen.add(r['name']);prepared.append((r,item['flipped']))
        for r,value in prepared:objects[r['name']][1].Flipped=value
        after=self._finish(document_id);self._verify_rigid_connections(before,after);new={r['name']:r for r in after['mates']}
        for r,value in prepared:
            if new[r['name']]['flipped']!=value:raise n.Failure('MATE_FLIP_READBACK','Native flip differs',mate=new[r['name']],edit_may_be_partial=True)
            for key in ('value','minimum','maximum'):
                if abs(new[r['name']][key]-r[key])>1e-5:raise n.Failure('MATE_FLIP_READBACK','Flipping unexpectedly changed a position magnitude/bound',mate=new[r['name']],edit_may_be_partial=True)
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['native_mate_error_count'] or status['invalid_components']:raise n.Failure('ASSEMBLY_INVALID','Mate side changes left invalid constraints',status=status,edit_may_be_partial=True)
        return {**after,'flipped_mates':[new[r['name']] for r,_ in prepared],'scope':'Native distance/angle side selection. Verify actual component positions; positive magnitudes alone do not specify the intended mirrored side.'}

    def set_mate_position(self,document_id,state,mate_name,value):
        model,before=self._edit(document_id,state,2)
        value=float(value)
        rows=before['mates'];objects=self._mate_objects_for_snapshot(document_id,before);matches=[r for r in rows if r['name']==mate_name]
        if len(matches)!=1 or matches[0]['mate_type'] not in (5,6):raise n.Failure('MATE_NAME','Choose an exact native distance/angle mate from sw_assembly_status',edit_may_be_partial=False)
        row=matches[0];cap=180 if row['mate_type']==6 else 5000
        if row['suppressed']:raise n.Failure('MATE_SUPPRESSED','Unsuppress the intended mate in SOLIDWORKS before driving it',edit_may_be_partial=False)
        if row['dimension_driven_state']!=2:raise n.Failure('MATE_REFERENCE_DIMENSION','This mate position is a reference/driven dimension; this version only commands native driving dimensions',edit_may_be_partial=False)
        if not math.isfinite(value) or not 0<=value<=cap:raise n.Failure('MATE_VALUE','Position must be finite and within the native reference range',edit_may_be_partial=False)
        if row.get('is_limit') and not row['minimum']-1e-8<=value<=row['maximum']+1e-8:raise n.Failure('MATE_LIMIT','Requested position is outside the unchanged native mate limits',minimum=row['minimum'],maximum=row['maximum'],unit=row['unit'],edit_may_be_partial=False)
        # The native maximum can read back as175.99999999999997mm. Passing
        # rounded176mm can be silently refused by the native limit solver.
        # Clamp only the already-validated roundoff band, never a real excess.
        if row.get('is_limit'):value=max(row['minimum'],min(row['maximum'],value))
        feature,mate=objects[mate_name]
        display=n.member(mate,'DisplayDimension')
        if display is None:raise n.Failure('MATE_DIMENSION','Native mate has no driving display dimension',edit_may_be_partial=False)
        dim=n.member(display,'GetDimension2',0)
        previous=float(n.member(dim,'SystemValue'))
        dim.SystemValue=value*(math.pi/180 if row['mate_type']==6 else .001)
        after=self._finish(document_id);new=next(r for r in after['mates'] if r['name']==mate_name)
        self._verify_rigid_connections(before,after)
        if abs(new['value']-value)>1e-5:raise n.Failure('MATE_POSITION_READBACK','Native mate position differs after solving',mate=new,edit_may_be_partial=True)
        if row.get('is_limit') and (abs(new['minimum']-row['minimum'])>1e-5 or abs(new['maximum']-row['maximum'])>1e-5):raise n.Failure('MATE_LIMIT_READBACK','Driving the position changed a native limit',mate=new,edit_may_be_partial=True)
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['native_mate_error_count'] or status['invalid_components']:raise n.Failure('ASSEMBLY_INVALID','Native pose command left invalid mates',status=status,edit_may_be_partial=True)
        return {**after,'driven_mate':new,'previous_value_si':previous,'constraint_status':status['components'],'scope':'Native mate-parameter-driven assembly pose, not dynamics or a proof of manual drag behavior.'}

    def _verify_rigid_connections(self,before,after):
        old={c['name']:c['transform'] for c in before['components']};new={c['name']:c['transform'] for c in after['components']}
        for mate in before.get('mates',[]):
            if mate.get('suppressed') or not (mate['mate_type']==16 or mate['mate_type']==1 and mate.get('lock_rotation')):continue
            names=[r['component'] for r in mate['references']]
            if len(names)!=2 or any(name not in old or name not in new for name in names):continue
            a=relative_component_pose(old[names[0]],old[names[1]]);b=relative_component_pose(new[names[0]],new[names[1]])
            rotation=max(abs(a[i]-b[i]) for i in range(9));translation=max(abs(a[i]-b[i]) for i in range(9,12))
            if rotation>1e-6 or mate['mate_type']==16 and translation>1e-7:
                raise n.Failure('MATE_GEOMETRY','Native solve did not preserve a rigid/rotation-locked connection. Inspect the partial pose; do not blindly repeat the move.',mate=mate['name'],relative_rotation_error=rotation,relative_position_error_m=translation,edit_may_be_partial=True)

    def set_mate_positions(self,document_id,state,positions):
        model,before=self._edit(document_id,state,2)
        if not isinstance(positions,list) or not 1<=len(positions)<=16:raise n.Failure('ARGUMENT','Provide 1..16 explicit mate positions',edit_may_be_partial=False)
        rows=before['mates'];objects=self._mate_objects_for_snapshot(document_id,before);known={r['name']:r for r in rows};prepared=[];seen=set()
        for item in positions:
            if not isinstance(item,dict) or set(item)!={'mate_name','value'} or item['mate_name'] in seen:raise n.Failure('ARGUMENT','Use distinct {mate_name,value} rows',edit_may_be_partial=False)
            name=item['mate_name'];seen.add(name);r=known.get(name)
            if r is None or r['mate_type'] not in (5,6) or r['suppressed'] or r['dimension_driven_state']!=2:raise n.Failure('MATE_NAME','Choose an active native driving distance/angle mate',mate_name=name,edit_may_be_partial=False)
            value=float(item['value']);cap=180 if r['mate_type']==6 else 5000
            if not math.isfinite(value) or not 0<=value<=cap:raise n.Failure('MATE_VALUE','Invalid reference position',edit_may_be_partial=False)
            if r['is_limit'] and not r['minimum']-1e-8<=value<=r['maximum']+1e-8:raise n.Failure('MATE_LIMIT','A target is outside unchanged native bounds; no positions were written',mate_name=name,edit_may_be_partial=False)
            if r['is_limit']:value=max(r['minimum'],min(r['maximum'],value))
            prepared.append((r,value))
        dims=[]
        for r,value in prepared:
            display=n.member(objects[r['name']][1],'DisplayDimension')
            if display is None:raise n.Failure('MATE_DIMENSION','A requested mate has no native dimension',edit_may_be_partial=False)
            dims.append((n.member(display,'GetDimension2',0),r,value))
        for dim,r,value in dims:dim.SystemValue=value*(math.pi/180 if r['mate_type']==6 else .001)
        after=self._finish(document_id);self._verify_rigid_connections(before,after);new={r['name']:r for r in after['mates']}
        for r,value in prepared:
            actual=new[r['name']]
            if abs(actual['value']-value)>1e-5 or r['is_limit'] and max(abs(actual[k]-r[k]) for k in ('minimum','maximum'))>1e-5:raise n.Failure('MATE_POSITION_READBACK','Position/bounds changed unexpectedly',mate=actual,edit_may_be_partial=True)
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['native_mate_error_count'] or status['invalid_components']:raise n.Failure('ASSEMBLY_INVALID','Combined pose left invalid constraints',status=status,edit_may_be_partial=True)
        return {**after,'driven_mates':[new[r['name']] for r,_ in prepared],'scope':'Combined native CAD pose command. Input bounds are checked before any write; not transactional rollback, dynamics, or manual drag validation.'}

    def scan_motion(self,document_id,state,trajectory,restore_start=True):
        model,before=self._edit(document_id,state,2)
        if type(restore_start)!=bool or not isinstance(trajectory,list) or not 1<=len(trajectory)<=8:raise n.Failure('ARGUMENT','Use 1..8 sampled poses per call and a boolean restore_start',edit_may_be_partial=False)
        known={r['name']:r for r in before['mates']};names=None
        for pose in trajectory:
            if not isinstance(pose,list) or not 1<=len(pose)<=16:raise n.Failure('ARGUMENT','Each pose needs 1..16 {mate_name,value} rows',edit_may_be_partial=False)
            current=set()
            for item in pose:
                if not isinstance(item,dict) or set(item)!={'mate_name','value'} or item['mate_name'] in current:raise n.Failure('ARGUMENT','Invalid or duplicate pose driver',edit_may_be_partial=False)
                name=item['mate_name'];r=known.get(name);current.add(name)
                if r is None or r['mate_type'] not in (5,6) or r['suppressed'] or r['dimension_driven_state']!=2:raise n.Failure('MATE_NAME','Every sampled driver must be active and driving',edit_may_be_partial=False)
                value=float(item['value']);cap=180 if r['mate_type']==6 else 5000
                if not math.isfinite(value) or not 0<=value<=cap or r['is_limit'] and not r['minimum']-1e-8<=value<=r['maximum']+1e-8:raise n.Failure('MATE_LIMIT','A sampled target is outside native bounds; scan was not started',edit_may_be_partial=False)
            if names is None:names=current
            elif names!=current:raise n.Failure('ARGUMENT','All sampled poses must name the same drivers',edit_may_be_partial=False)
        samples=[];after=before
        try:
            for index,pose in enumerate(trajectory):
                after=self.set_mate_positions(document_id,after['state'],pose)
                interference=self._check_interference_pose(document_id,after)
                samples.append({'index':index,'positions':pose,'components':after['components'],'interference':interference})
            if restore_start:after=self.set_mate_positions(document_id,after['state'],[{'mate_name':name,'value':known[name]['value']} for name in sorted(names)])
        except Exception as error:raise n.Failure('MOTION_SCAN_PARTIAL',str(error),completed_samples=samples,edit_may_be_partial=True,retry_automatically=False) from error
        return {**after,'samples':samples,'restored_start_pose':restore_start,'scope':'Discrete native kinematic poses and interference samples only. No continuous swept-volume guarantee, dynamics, force or energy calculation. Source-part dimensions remain unchanged during this scan.'}

    def _resolve_reference(self,model,reference):
        if not isinstance(reference,dict) or set(reference)-{'component','face_id','plane_name'}:raise n.Failure('MATE_REFERENCE','Use component plus one face_id or exact plane_name',edit_may_be_partial=False)
        comp=self._component(model,reference.get('component',''))
        kinds=[k for k in ('face_id','plane_name') if k in reference]
        if len(kinds)!=1:raise n.Failure('MATE_REFERENCE','Choose exactly one face or reference plane',edit_may_be_partial=False)
        child=n.member(comp,'GetModelDoc2')
        if child is None:raise n.Failure('UNRESOLVED_COMPONENT','Resolve the component before adding mates',edit_may_be_partial=False)
        if 'face_id' in reference:
            geo,_,faces,_=self._part_geometry(child,True);i=reference['face_id']
            if type(i)!=int or i<0 or i>=len(faces):raise n.Failure('MATE_FACE','Invalid fresh face ID',edit_may_be_partial=False)
            data=geo['faces'][i];entity=comp.GetCorrespondingEntity(faces[i])
            if entity is None:raise n.Failure('ASSEMBLY_CONTEXT','Could not map face into assembly context',edit_may_be_partial=False)
            return {'component':comp,'entity':entity,'kind':data['kind'],'geometry':data}
        matches=[p for p in self._reference_planes(child) if p['plane_name']==reference['plane_name']]
        if len(matches)!=1:raise n.Failure('MATE_PLANE','Use an exact reference plane returned in component geometry',edit_may_be_partial=False)
        return {'component':comp,'plane_select_name':reference['plane_name']+'@'+str(n.member(comp,'GetSelectByIDString')),'kind':'plane','geometry':matches[0]}

    def _select_mate_reference(self,model,ref,append):
        if 'entity' in ref:
            data=model.SelectionManager.CreateSelectData();data.Mark=1
            ok=ref['entity'].Select4(append,data)
        else:ok=model.Extension.SelectByID2(ref['plane_select_name'],'PLANE',0.,0.,0.,append,1,None,0)
        if not ok:raise n.Failure('MATE_SELECTION','Could not select the exact reference in assembly context',edit_may_be_partial=False)

    def add_mate(self,document_id,state,mate_type,reference_a,reference_b,value=0.,minimum=0.,maximum=0.,alignment='closest',lock_rotation=False,flip=False,name=''):
        model,before=self._edit(document_id,state,2)
        try:spec=validate_mate_values(mate_type,value,minimum,maximum,alignment,lock_rotation,flip,name)
        except ValueError as error:raise n.Failure('MATE_ARGUMENT',str(error),edit_may_be_partial=False) from error
        if reference_a.get('component')==reference_b.get('component'):raise n.Failure('MATE_SELECTION','Choose two different components',edit_may_be_partial=False)
        old_names={r['name'] for r in before['mates']}
        if name and name in {f['name'] for f in self._features(model)}:raise n.Failure('FEATURE_NAME','Mate name already exists',edit_may_be_partial=False)
        if mate_type=='lock':
            if set(reference_a)!={'component'} or set(reference_b)!={'component'}:raise n.Failure('MATE_REFERENCE','Lock mate requires two component-only references',edit_may_be_partial=False)
            refs=[self._component(model,r['component']) for r in [reference_a,reference_b]]
            if all(n.member(c,'IsFixed') for c in refs):raise n.Failure('MATE_FIXED','At least one component must be floating',edit_may_be_partial=False)
            for i,c in enumerate(refs):
                selection=model.SelectionManager.CreateSelectData();selection.Mark=1
                if not c.Select4(i>0,selection,False):raise n.Failure('MATE_SELECTION','Could not select component',edit_may_be_partial=False)
        else:
            refs=[self._resolve_reference(model,r) for r in [reference_a,reference_b]]
            if mate_type=='concentric' and (any(r['kind'] not in ('cylinder','sphere') for r in refs) or len({r['kind'] for r in refs})!=1):raise n.Failure('MATE_FACE','Concentric mate requires two cylinders or two spheres',edit_may_be_partial=False)
            if mate_type=='concentric' and refs[0]['kind']=='sphere' and lock_rotation:raise n.Failure('MATE_FACE','Spherical center connection must retain rotational freedom',edit_may_be_partial=False)
            if mate_type!='concentric' and any(r['kind']!='plane' for r in refs):raise n.Failure('MATE_FACE','This mate requires two planar references',edit_may_be_partial=False)
            if all(n.member(r['component'],'IsFixed') for r in refs):raise n.Failure('MATE_FIXED','At least one component must be floating',edit_may_be_partial=False)
            for i,ref in enumerate(refs):self._select_mate_reference(model,ref,i>0)
        try:
            mate,error=n.out_call(model,'AddMate5',(spec['native_type'],spec['native_alignment'],flip,spec['distance'],spec['distance_max'],spec['distance_min'],0.,0.,spec['angle'],spec['angle_max'],spec['angle_min'],False,lock_rotation,0),1)
        finally:model.ClearSelection2(True)
        if mate is None or error!=1:raise n.Failure('MATE_FAILED','Native mate creation failed; inspect assembly before further edits',native_error=error,edit_may_be_partial=True)
        feature=self.binding.cast(n.member(model.Extension,'GetLastFeatureAdded'),'IFeature')
        native=self.binding.cast(n.member(feature,'GetSpecificFeature2'),'IMate2')
        if int(n.member(native,'Type'))!=spec['native_type']:raise n.Failure('MATE_READBACK','Last native feature is not the intended mate',edit_may_be_partial=True)
        if name:
            feature.Name=name
            if str(n.member(feature,'Name'))!=name:raise n.Failure('MATE_READBACK','Mate name differs after assignment',edit_may_be_partial=True)
        after=self._finish(document_id);rows=after['mates']
        new=[r for r in rows if r['name'] not in old_names]
        if len(new)!=1:raise n.Failure('MATE_READBACK','Could not identify exactly one new native mate',edit_may_be_partial=True)
        row=new[0]
        if row['native_error'] and not row['native_warning']:raise n.Failure('MATE_INVALID','New native mate has a feature error',mate=row,edit_may_be_partial=True)
        if row['mate_type']!=spec['native_type']:raise n.Failure('MATE_READBACK','Native mate type differs',mate=row,edit_may_be_partial=True)
        if mate_type.startswith('limit_'):
            if not row.get('is_limit') or max(abs(row['minimum']-minimum),abs(row['maximum']-maximum))>1e-5:raise n.Failure('MATE_LIMIT_READBACK','Native advanced-mate limits differ',mate=row,edit_may_be_partial=True)
        elif mate_type in ('angle','distance') and abs(row['value']-value)>1e-5:raise n.Failure('MATE_VALUE_READBACK','Native mate value differs',mate=row,edit_may_be_partial=True)
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['invalid_components'] or status['native_mate_error_count']:raise n.Failure('ASSEMBLY_INVALID','Assembly solver reports an invalid constraint set',status=status,edit_may_be_partial=True)
        return {**after,'created_mate':row,'native_error':int(error),'constraint_status':status['components']}

    def move_component(self,document_id,state,component_name,translation_mm=None,axis_world=None,angle_deg=0.,pivot_mm=None):
        model,before=self._edit(document_id,state,2);comp=self._component(model,component_name)
        if n.member(comp,'IsFixed'):raise n.Failure('COMPONENT_FIXED','Float the exact component before attempting a mate-solved move',edit_may_be_partial=False)
        current=list(n.member(n.member(comp,'Transform2'),'ArrayData'))
        try:requested=incremental_transform(current,translation_mm,axis_world,angle_deg,pivot_mm)
        except ValueError as error:raise n.Failure('TRANSFORM_ARGUMENT',str(error),edit_may_be_partial=False) from error
        xform=self.sw.GetMathUtility().CreateTransform(n.double_array(requested))
        solved=bool(n.member(comp,'SetTransformAndSolve3',xform,True))
        after=self._finish(document_id);actual=list(n.member(n.member(comp,'Transform2'),'ArrayData'))
        self._verify_rigid_connections(before,after)
        position_error=math.sqrt(sum((actual[i]-requested[i])**2 for i in (9,10,11)))*1000
        rotation_error=max(abs(actual[i]-requested[i]) for i in range(9))
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['invalid_components'] or status['native_mate_error_count']:raise n.Failure('ASSEMBLY_INVALID','Native move left an invalid constraint state; inspect before further edits',status=status,edit_may_be_partial=True)
        return {**after,'component_name':component_name,'native_solver_return':solved,
          'requested_transform':requested,'achieved_transform':actual,
          'requested_position_error_mm':position_error,'requested_rotation_matrix_error':rotation_error,
          'request_achieved':position_error<1e-4 and rotation_error<1e-6,
          'before_transform':current,'constraint_status':status['components'],
          'solver':'IComponent2.SetTransformAndSolve3','scope':'Incremental mate-solved kinematic move. A rejected or projected target is reported without forcing the component through its constraints. For limit mates use sw_set_mate_position to drive the native pose dimension; this generic move may solve back to that dimension.'}

    def check_interference(self,document_id):
        return self._check_interference_pose(document_id)

    def _check_interference_pose(self,document_id,inspected_pose=None):
        model=self._doc(document_id)['model']
        if int(n.member(model,'GetType'))!=2:raise n.Failure('DOCUMENT_TYPE','Expected assembly',edit_may_be_partial=False)
        self._activate(model);model.ClearSelection2(True)
        before=inspected_pose if inspected_pose is not None else self.snapshot(document_id)
        manager=n.member(model,'InterferenceDetectionManager')
        if manager is None:raise n.Failure('INTERFERENCE_UNAVAILABLE','Native interference manager unavailable',edit_may_be_partial=False)
        settings={k:n.member(manager,k) for k in ('TreatCoincidenceAsInterference','TreatSubAssembliesAsComponents','IncludeMultibodyPartInterferences','IgnoreHiddenBodies','MakeInterferingPartsTransparent','ShowIgnoredInterferences')}
        try:
            for k,v in {'TreatCoincidenceAsInterference':False,'TreatSubAssembliesAsComponents':False,'IncludeMultibodyPartInterferences':True,'IgnoreHiddenBodies':False,'MakeInterferingPartsTransparent':False,'ShowIgnoredInterferences':True}.items():setattr(manager,k,v)
            interferences=n.member(manager,'GetInterferences') or [];rows=[]
            for item in interferences:
                volume=float(n.member(item,'Volume'))*1e9
                rows.append({'components':[str(n.member(c,'Name2')) for c in n.member(item,'Components') or []],
                  'volume_mm3':volume,'possible_interference':bool(n.member(item,'IsPossibleInterference'))})
        finally:
            for k,v in settings.items():setattr(manager,k,v)
            n.member(manager,'Done')
        after=self.snapshot(document_id)
        if before['state']!=after['state']:raise n.Failure('INSPECTION_CHANGED_STATE','Interference inspection changed model state; inspect again',edit_may_be_partial=True)
        return {'document_id':document_id,'state':after['state'],'interferences':rows,'count':len(rows),'scope':'Native solid interference at this pose; touching faces are excluded. Not a swept-volume, minimum-clearance or stress analysis.'}

    def _material_identity(self,model,configuration=''):
        if int(n.member(model,'GetType'))!=1:return None
        result=n.member(model,'GetMaterialPropertyName2',configuration, '')
        if not isinstance(result,tuple) or len(result)!=2:raise n.Failure('MATERIAL_READBACK','Unexpected native material identity output')
        identifier=str(result[1] or '');resolved=None
        if identifier:
            if Path(identifier).is_file():resolved=str(Path(identifier).resolve())
            else:
                databases=getattr(self,'_material_databases_cache',None)
                if databases is None:
                    databases=list(n.member(self._app(),'GetMaterialDatabases') or []);self._material_databases_cache=databases
                candidates=[Path(p).resolve() for p in databases if Path(p).stem.casefold()==Path(identifier).stem.casefold()]
                if len(candidates)==1:resolved=str(candidates[0])
        return {'material_name':str(result[0] or ''),'database_identifier':identifier,
          'database_path':resolved,'assigned':bool(result[0])}

    def mass_properties(self,document_id):
        model=self._doc(document_id)['model'];before=self.snapshot(document_id)
        self._activate(model);model.ClearSelection2(True)
        prop=n.member(model.Extension,'CreateMassProperty');prop.UseSystemUnits=True
        materials=[]
        if before['kind']==1:materials=[{'part':before['path'] or before['title'],**self._material_identity(model)}]
        else:
            for c in n.member(model,'GetComponents',True) or []:
                child=n.member(c,'GetModelDoc2')
                if child is None:raise n.Failure('UNRESOLVED_COMPONENT','Resolve all components before mass calculation',edit_may_be_partial=False)
                if int(n.member(child,'GetType'))!=1:raise n.Failure('MODEL_SCOPE','Mass material audit currently supports top-level parts',edit_may_be_partial=False)
                materials.append({'component':str(n.member(c,'Name2')),**self._material_identity(child,str(n.member(c,'ReferencedConfiguration')))})
        result={'document_id':document_id,'state':before['state'],'mass_kg':float(n.member(prop,'Mass')),
          'volume_m3':float(n.member(prop,'Volume')),'surface_area_m2':float(n.member(prop,'SurfaceArea')),
          'center_of_mass_m':[float(v) for v in n.member(prop,'CenterOfMass')],
          'inertia_about_com_kg_m2':[float(v) for v in n.member(prop,'GetMomentOfInertia',0)],
          'native_mass_override':bool(n.member(prop,'OverrideMass')),'materials':materials,
          'all_parts_have_assigned_materials':bool(materials) and all(r['assigned'] for r in materials),
          'scope':'Native geometry/material calculation, including native overrides. Material assignment does not verify real purchased hardware, manufacturing details or measured mass.'}
        if any(not math.isfinite(v) for v in [result['mass_kg'],result['volume_m3'],*result['center_of_mass_m'],*result['inertia_about_com_kg_m2']]):raise n.Failure('MEASUREMENT_FAILED','Nonfinite native mass data')
        return result

    def materials(self,query='',maximum=80):
        if not isinstance(query,str) or len(query)>200 or type(maximum)!=int or not 1<=maximum<=200:raise n.Failure('ARGUMENT','Material query is limited to 200 characters and 1..200 results',edit_may_be_partial=False)
        databases=list(n.member(self._app(),'GetMaterialDatabases') or []);rows=[];matches=0
        self._material_databases_cache=databases
        for database in databases:
            path=Path(database)
            if not path.is_file() or path.suffix.lower()!='.sldmat':continue
            for mat in ET.parse(path).getroot().iter('material'):
                name=mat.get('name','')
                if query.casefold() not in name.casefold():continue
                matches+=1
                if len(rows)<maximum:rows.append({'material_name':name,'database_path':str(path)})
        return {'materials':rows,'total_matches':matches,'truncated':matches>maximum,'databases':[str(p) for p in databases]}

    def set_material(self,document_id,state,database_path,material_name):
        model,before=self._edit(document_id,state,1)
        available={Path(p).resolve() for p in n.member(self._app(),'GetMaterialDatabases') or []}
        path=Path(database_path).resolve(strict=True)
        if path not in available or path.suffix.lower()!='.sldmat':raise n.Failure('MATERIAL_DATABASE','Use an installed database returned by sw_materials',edit_may_be_partial=False)
        if material_name not in {m.get('name') for m in ET.parse(path).getroot().iter('material')}:raise n.Failure('MATERIAL_NAME','Exact material name not found in the database',edit_may_be_partial=False)
        n.member(model,'SetMaterialPropertyName2','',str(path),material_name)
        after=self._finish(document_id);identity=self._material_identity(model)
        if identity['material_name']!=material_name:raise n.Failure('MATERIAL_READBACK','Native material differs after assignment',actual=identity,edit_may_be_partial=True)
        if identity['database_path'] and Path(identity['database_path']).resolve()!=path:raise n.Failure('MATERIAL_READBACK','Native material database differs after assignment',actual=identity,edit_may_be_partial=True)
        return {**after,'material':identity,'mass_properties':self.mass_properties(document_id)}
