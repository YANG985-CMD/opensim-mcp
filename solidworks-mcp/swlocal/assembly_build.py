"""Bounded assembly construction helpers built on real native mates."""
import math
from pathlib import Path
import pythoncom
import win32com.client
from . import cad as n
from .geometry import relative_component_pose,validate_rigid_transform


class AssemblyBuildTools:
    def set_dimensions(self,document_id,state,dimensions):
        model,before=self._edit(document_id,state,1)
        if not isinstance(dimensions,list) or not 1<=len(dimensions)<=16:raise n.Failure('ARGUMENT','Provide 1..16 explicit SI dimensions',edit_may_be_partial=False)
        allowed={d['name'] for f in self._features(model,True) for d in f.get('dimensions',[])};seen=set();prepared=[]
        for item in dimensions:
            if not isinstance(item,dict) or set(item)!={'dimension_name','value_si'}:raise n.Failure('ARGUMENT','Use {dimension_name,value_si}',edit_may_be_partial=False)
            name=item['dimension_name'];value=float(item['value_si'])
            if name not in allowed or name in seen:raise n.Failure('DIMENSION_NAME','Use distinct exact names from sw_features',edit_may_be_partial=False)
            if not math.isfinite(value) or not 0<value<=100:raise n.Failure('DIMENSION_VALUE','System values must be finite and positive',edit_may_be_partial=False)
            dim=model.Parameter(name)
            if dim is None:raise n.Failure('DIMENSION_MISSING','Could not resolve an exact native dimension',edit_may_be_partial=False)
            seen.add(name);prepared.append((name,dim,value,float(n.member(dim,'SystemValue'))))
        for name,dim,value,old in prepared:dim.SystemValue=value
        after=self._finish(document_id);results=[]
        for name,dim,value,old in prepared:
            actual=float(n.member(dim,'SystemValue'))
            if abs(actual-value)>max(1e-9,abs(value)*1e-6):raise n.Failure('DIMENSION_READBACK','Native dimension differs after rebuild',dimension_name=name,edit_may_be_partial=True)
            results.append({'dimension_name':name,'actual_value_si':actual,'previous_value_si':old})
        return {**after,'changed_dimensions':results}

    def add_components(self,document_id,state,components):
        model,before=self._edit(document_id,state,2)
        if before['components']:raise n.Failure('ASSEMBLY_NOT_EMPTY','Bulk placement is limited to an empty assembly',edit_may_be_partial=False)
        if not isinstance(components,list) or not 1<=len(components)<=128:raise n.Failure('ARGUMENT','Provide 1..128 explicit components',edit_may_be_partial=False)
        specs=[]
        for row in components:
            if not isinstance(row,dict) or set(row)-{'path','transform','fixed'}:raise n.Failure('ARGUMENT','Use path, rigid transform and fixed',edit_may_be_partial=False)
            p=Path(row['path']).resolve(strict=True)
            if p.suffix.lower()!='.sldprt':raise n.Failure('COMPONENT_TYPE','Native part files only',edit_may_be_partial=False)
            if type(row.get('fixed',False))!=bool:raise n.Failure('ARGUMENT','fixed must be boolean',edit_may_be_partial=False)
            try:t=validate_rigid_transform(row.get('transform'))
            except (TypeError,ValueError) as error:raise n.Failure('TRANSFORM_ARGUMENT',str(error),edit_may_be_partial=False)
            self._check_name_collision(p);specs.append((str(p),t,row.get('fixed',False)))
        strings=lambda rows:win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_BSTR,tuple(rows))
        added=n.member(model,'AddComponents3',strings(s[0] for s in specs),n.double_array(v for s in specs for v in s[1]),strings('' for _ in specs))
        if added is None or len(added)!=len(specs):raise n.Failure('BULK_INSERT','Native inserted count differs; inspect partial assembly',edit_may_be_partial=True)
        model.ClearSelection2(True)
        try:
            for wanted in (True,False):
                changed=[c for c,s in zip(added,specs) if bool(n.member(c,'IsFixed'))!=s[2] and s[2]==wanted]
                for i,c in enumerate(changed):
                    if not c.Select4(i>0,None,False):raise n.Failure('COMPONENT_SELECTION','Bulk fixed-state selection failed',edit_may_be_partial=True)
                if changed:n.member(model,'FixComponent' if wanted else 'UnfixComponent')
                model.ClearSelection2(True)
        finally:model.ClearSelection2(True)
        self._part_fingerprints={};after=self._finish(document_id);actual={r['name']:r for r in after['components']};mapping=[]
        for comp,spec in zip(added,specs):
            name=str(n.member(comp,'Name2'));row=actual[name]
            if Path(row['path']).resolve()!=Path(spec[0]) or row['fixed']!=spec[2] or max(abs(a-b) for a,b in zip(row['transform'],spec[1]))>1e-7:raise n.Failure('BULK_READBACK','Inserted part identity, placement or fixed state differs',component=name,edit_may_be_partial=True)
            if not row['geometry_hash']:raise n.Failure('UNRESOLVED_COMPONENT','Inserted component geometry was not resolved',component=name,edit_may_be_partial=True)
            mapping.append({'component_name':name,'path':spec[0]})
        return {**after,'inserted_components':mapping,'scope':'Initial rigid placement only. Add native mates before claiming a mechanism. AddComponents3 does not expose per-file OpenDoc6 load flags.'}

    def connect_rigid_group(self,document_id,state,anchor_component,members,name_prefix='rigid'):
        model,before=self._edit(document_id,state,2)
        if not isinstance(members,list) or not 1<=len(members)<=64 or any(not isinstance(x,str) for x in members) or len(set(members))!=len(members) or anchor_component in members:raise n.Failure('ARGUMENT','Choose one anchor and 1..64 distinct other component names',edit_may_be_partial=False)
        if not isinstance(name_prefix,str) or not name_prefix or len(name_prefix)>60 or any(c in name_prefix for c in '@\\/\r\n'):raise n.Failure('ARGUMENT','Invalid name prefix',edit_may_be_partial=False)
        anchor=self._component(model,anchor_component);children=[self._component(model,name) for name in members]
        existing={r['name'] for r in self._features(model)}
        names=[name_prefix+'_'+str(i+1) for i in range(len(members))]
        if existing.intersection(names):raise n.Failure('FEATURE_NAME','A proposed lock mate name already exists',edit_may_be_partial=False)
        for row in before['mates']:
            if not row['suppressed'] and any(r['component'] in members for r in row['references']):raise n.Failure('MEMBER_ALREADY_MATED','This helper only attaches members without existing active mates',mate=row['name'],edit_may_be_partial=False)
        poses={r['name']:r['transform'] for r in before['components']};completed=[]
        try:
            for child,name,feature_name in zip(children,members,names):
                model.ClearSelection2(True)
                if n.member(child,'IsFixed'):
                    if not child.Select4(False,None,False):raise RuntimeError('Could not select member to float')
                    n.member(model,'UnfixComponent');model.ClearSelection2(True)
                    if n.member(child,'IsFixed'):raise RuntimeError('Member did not become floating')
                for i,c in enumerate((anchor,child)):
                    data=model.SelectionManager.CreateSelectData();data.Mark=1
                    if not c.Select4(i>0,data,False):raise RuntimeError('Exact lock reference selection failed')
                mate,error=n.out_call(model,'AddMate5',(16,2,False,0.,0.,0.,0.,0.,0.,0.,0.,False,False,0),1)
                model.ClearSelection2(True)
                if mate is None or error!=1:raise RuntimeError('Native lock creation failed: '+str(error))
                feature=self.binding.cast(n.member(model.Extension,'GetLastFeatureAdded'),'IFeature')
                native=self.binding.cast(n.member(feature,'GetSpecificFeature2'),'IMate2')
                if int(n.member(native,'Type'))!=16:raise RuntimeError('Last feature is not the created lock mate')
                refs=[str(n.member(n.member(n.member(native,'MateEntity',i),'ReferenceComponent'),'Name2')) for i in range(int(n.member(native,'GetMateEntityCount')))]
                if set(refs)!={anchor_component,name}:raise RuntimeError('Native lock references differ')
                feature.Name=feature_name
                if str(n.member(feature,'Name'))!=feature_name or not model.ForceRebuild3(True):raise RuntimeError('Lock naming/rebuild failed')
                a=list(n.member(n.member(anchor,'Transform2'),'ArrayData'));b=list(n.member(n.member(child,'Transform2'),'ArrayData'))
                old=relative_component_pose(poses[anchor_component],poses[name]);new=relative_component_pose(a,b)
                if max(abs(x-y) for x,y in zip(old,new))>1e-7:raise RuntimeError('Lock changed relative geometry')
                completed.append(feature_name)
        except Exception as error:
            raise n.Failure('RIGID_GROUP_PARTIAL',str(error),completed_mates=completed,edit_may_be_partial=True) from error
        finally:model.ClearSelection2(True)
        after=self._finish(document_id);by_name={r['name']:r for r in after['components']}
        for name in members:
            a=relative_component_pose(poses[anchor_component],poses[name]);b=relative_component_pose(by_name[anchor_component]['transform'],by_name[name]['transform'])
            if by_name[name]['fixed'] or max(abs(x-y) for x,y in zip(a,b))>1e-7:raise n.Failure('RIGID_GROUP_READBACK','Rigid group member differs or remains grounded',component=name,edit_may_be_partial=True)
        status=self._assembly_status_for_snapshot(document_id,after)
        if status['native_mate_error_count'] or status['invalid_components']:raise n.Failure('ASSEMBLY_INVALID','Rigid group left invalid native constraints',status=status,edit_may_be_partial=True)
        return {**after,'created_lock_mates':completed,'rigid_anchor':anchor_component,'rigid_members':members}

    def create_joint(self,document_id,state,kind,name,axis_a=None,axis_b=None,plane_pairs=None,position=None):
        # The template is a short explicit mate sequence, never an arbitrary
        # method dispatcher. Every step uses a fresh inspected state.
        self._edit(document_id,state,2)
        if kind not in ('revolute','prismatic','spherical'):raise n.Failure('ARGUMENT','Unsupported joint template',edit_may_be_partial=False)
        if not isinstance(name,str) or not name or len(name)>60 or any(c in name for c in '@\\/\r\n'):raise n.Failure('ARGUMENT','Invalid joint name',edit_may_be_partial=False)
        pairs=plane_pairs or [];steps=[]
        if kind in ('revolute','spherical'):
            if not isinstance(axis_a,dict) or not isinstance(axis_b,dict):raise n.Failure('ARGUMENT','Choose two exact cylindrical/spherical faces',edit_may_be_partial=False)
            steps.append(dict(mate_type='concentric',reference_a=axis_a,reference_b=axis_b,name=name+'_axis'))
        if kind=='revolute' and len(pairs)!=1 or kind=='prismatic' and len(pairs)!=2 or kind=='spherical' and (pairs or position):raise n.Failure('ARGUMENT','Revolute needs one axial plane pair; prismatic two guide pairs; spherical only two sphere faces',edit_may_be_partial=False)
        for i,pair in enumerate(pairs):
            if not isinstance(pair,dict) or set(pair)-{'a','b','distance_mm'} or not {'a','b'}<=set(pair):raise n.Failure('ARGUMENT','Invalid plane pair',edit_may_be_partial=False)
            value=float(pair.get('distance_mm',0.))
            steps.append(dict(mate_type='distance' if value else 'coincident',reference_a=pair['a'],reference_b=pair['b'],value=value,name=name+'_guide_'+str(i)))
        if position is not None:
            if not isinstance(position,dict) or set(position)!={'a','b','value','minimum','maximum'}:raise n.Failure('ARGUMENT','Position needs a, b, value, minimum, maximum',edit_may_be_partial=False)
            steps.append(dict(mate_type='limit_angle' if kind=='revolute' else 'limit_distance',reference_a=position['a'],reference_b=position['b'],value=position['value'],minimum=position['minimum'],maximum=position['maximum'],name=name+'_position'))
        # Resolve and validate the whole request before the first native edit.
        model=self._doc(document_id)['model']
        from .geometry import validate_mate_values
        existing={f['name'] for f in self._features(model)}
        if existing.intersection(s['name'] for s in steps):raise n.Failure('FEATURE_NAME','A joint template mate name already exists; no mate was added',edit_may_be_partial=False)
        resolved=[]
        for step in steps:
            try:validate_mate_values(step['mate_type'],step.get('value',0),step.get('minimum',0),step.get('maximum',0),'closest',False,False,step['name'])
            except (TypeError,ValueError) as error:raise n.Failure('ARGUMENT',str(error),edit_may_be_partial=False)
            refs=[self._resolve_reference(model,step[k]) for k in ('reference_a','reference_b')]
            wanted='sphere' if kind=='spherical' else 'cylinder' if step['mate_type']=='concentric' else 'plane'
            if any(r['kind']!=wanted for r in refs):raise n.Failure('MATE_FACE','Joint template reference geometry differs',edit_may_be_partial=False)
            if step['reference_a'].get('component')==step['reference_b'].get('component'):raise n.Failure('ARGUMENT','A joint connects two different components',edit_may_be_partial=False)
            resolved.append(refs)
        pairs_used=[(s['reference_a']['component'],s['reference_b']['component']) for s in steps]
        if len(set(pairs_used))!=1:raise n.Failure('ARGUMENT','Every joint template reference pair must connect the same two ordered components',edit_may_be_partial=False)
        if kind=='prismatic':
            for side in (0,1):
                a=resolved[0][side]['geometry']['normal'];b=resolved[1][side]['geometry']['normal']
                if abs(sum(x*y for x,y in zip(a,b)))>1e-6:raise n.Failure('ARGUMENT','Prismatic guide planes must be orthogonal in each component',edit_may_be_partial=False)
        current=state;created=[]
        try:
            for step in steps:
                after=self.add_mate(document_id,current,**step);current=after['state'];created.append(after['created_mate']['name'])
        except Exception as error:raise n.Failure('JOINT_PARTIAL',str(error),completed_mates=created,edit_may_be_partial=True) from error
        return {**after,'joint_kind':kind,'joint_name':name,'joint_mates':created}
