"""Explicit CAD-to-body assembly. Geometry never supplies guessed physiology."""
from __future__ import annotations
import json,math,re,shutil,uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from .core import InputError,MAX_MODEL,bounded_read,xml_model,read_motion
from .structured import run_native
from .viewer import mesh_data,geometry
from .projects import digest
from .mass_properties import validate_central_inertia

def number(value,name,low=-1e6,high=1e6):
    if type(value) not in {int,float} or not math.isfinite(value) or not low<=value<=high:raise InputError('Invalid '+name)
    return float(value)

def vector(value,name,length=3):
    if not isinstance(value,list) or len(value)!=length:raise InputError('Expected '+str(length)+' values for '+name)
    return [number(x,name) for x in value]

def validate_links(cfg,links,physical):
    if not isinstance(links,list) or not 1<=len(links)<=20:raise InputError('Provide 1..20 explicit wearable links.')
    result=[];names=set()
    for link in links:
        required={'name','parent_frame','mesh_path','mesh_units'}
        common={'translation_m','orientation_xyz_rad','color','landmarks'}
        dynamics={'mass_kg','mass_center_m','inertia_kg_m2','joint_type','coordinate','coupling','joint_location_in_child_m','joint_orientation_in_child_xyz_rad'} if physical else set()
        if not isinstance(link,dict) or not required<=link.keys() or set(link)-required-common-dynamics:raise InputError('Missing/unrecognized wearable link fields.')
        name=link['name']
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,60}',name) or name in names:raise InputError('Unique bounded ASCII wearable names required.')
        names.add(name);parent=link['parent_frame']
        if not isinstance(parent,str) or not parent.startswith('/') or '..' in parent or len(parent)>500:raise InputError('Use an absolute physical parent frame path.')
        path=Path(link['mesh_path']);suffix=path.suffix.lower()
        if suffix not in {'.stl','.obj','.vtp'}:raise InputError('Export CAD to STL/OBJ/VTP or use the separate SolidWorks mesh exporter first.')
        source=cfg.input_path(str(path),suffix)
        units={'m':1.,'mm':.001,'cm':.01}
        if link['mesh_units'] not in units:raise InputError('Mesh units must explicitly be m/mm/cm; STL does not declare units.')
        item=dict(name=name,parent_frame=parent,mesh_path=str(source),unit_scale=units[link['mesh_units']],
            translation_m=vector(link.get('translation_m',[0.,0.,0.]),'translation'),orientation_xyz_rad=vector(link.get('orientation_xyz_rad',[0.,0.,0.]),'body-fixed XYZ orientation'),color=vector(link.get('color',[.15,.65,.9]),'color'))
        if any(not 0<=v<=1 for v in item['color']):raise InputError('Color must be RGB in [0,1].')
        if 'landmarks' in link:
            if 'translation_m' in link or 'orientation_xyz_rad' in link:raise InputError('Choose explicit transform or landmark fit, not both.')
            lm=link['landmarks']
            if not isinstance(lm,dict) or set(lm)-{'cad_points','parent_points_m','allow_uniform_scale'} or not {'cad_points','parent_points_m'}<=lm.keys():raise InputError('Invalid landmark correspondence.')
            a,b=lm['cad_points'],lm['parent_points_m']
            if not isinstance(a,list) or not isinstance(b,list) or len(a)!=len(b) or not 3<=len(a)<=50:raise InputError('Provide 3..50 corresponding CAD/body-frame landmarks.')
            item['landmarks']={'cad_points':[vector(v,'CAD landmark') for v in a],'parent_points_m':[vector(v,'body-frame landmark') for v in b],'allow_uniform_scale':lm.get('allow_uniform_scale',False)}
            if type(item['landmarks']['allow_uniform_scale']) is not bool:raise InputError('allow_uniform_scale must be boolean.')
            if physical and item['landmarks']['allow_uniform_scale']:raise InputError('Physical links require rigid landmark fitting; resizing would invalidate their mass/inertia.')
        if physical:
            for field in ('mass_kg','mass_center_m','inertia_kg_m2','joint_type'):
                if field not in link:raise InputError('Physical links require explicit '+field)
            item.update(mass_kg=number(link['mass_kg'],'mass_kg',1e-6,1000),mass_center_m=vector(link['mass_center_m'],'mass center'),inertia_kg_m2=vector(link['inertia_kg_m2'],'inertia tensor',6),joint_type=link['joint_type'])
            validate_central_inertia(item['inertia_kg_m2'])
            if item['joint_type'] not in {'WeldJoint','PinJoint','SliderJoint'}:raise InputError('Physical device links support WeldJoint/PinJoint/SliderJoint.')
            if item['joint_type']!='WeldJoint':
                if not {'joint_location_in_child_m','joint_orientation_in_child_xyz_rad'}<=link.keys():raise InputError('Pin/Slider require explicit joint center and axes in the CAD/body frame.')
                item['joint_location_in_child_m']=vector(link['joint_location_in_child_m'],'CAD joint center')
                item['joint_orientation_in_child_xyz_rad']=vector(link['joint_orientation_in_child_xyz_rad'],'CAD joint orientation')
                c=link.get('coordinate')
                if not isinstance(c,dict) or set(c)!={'name','range','default_value'} or not isinstance(c['name'],str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,60}',c['name']):raise InputError('Pin/Slider links need explicit coordinate name/range/default_value.')
                limits=vector(c['range'],'coordinate range',2);value=number(c['default_value'],'default_value')
                if not limits[0]<limits[1] or not limits[0]<=value<=limits[1]:raise InputError('Invalid device coordinate range/default.')
                item['coordinate']=dict(name=c['name'],range=limits,default_value=value)
                if 'coupling' in link:
                    coupling=link['coupling']
                    if not isinstance(coupling,dict) or set(coupling)!={'independent_coordinate','scale','offset'} or not isinstance(coupling['independent_coordinate'],str):raise InputError('Explicit linear coordinate coupling required.')
                    item['coupling']=dict(independent_coordinate=coupling['independent_coordinate'],scale=number(coupling['scale'],'coupling scale',-100,100),offset=number(coupling['offset'],'coupling offset'))
            elif 'coordinate' in link or 'coupling' in link:raise InputError('A welded link has no independent coordinate/coupling.')
        result.append(item)
    return result

def assemble(cfg,model_path,links,physical=True,geometry_roots=None,max_landmark_error_m=None):
    if type(physical) is not bool:raise InputError('physical must be boolean.')
    source=cfg.input_path(model_path,'.osim');raw=bounded_read(source,MAX_MODEL);root,model=xml_model(raw)
    parsed=validate_links(cfg,links,physical)
    if max_landmark_error_m is not None:number(max_landmark_error_m,'landmark threshold',0,1.)
    params=[{k:v for k,v in item.items() if k not in {'mesh_path','color'}} for item in parsed]
    validation=run_native(cfg,'wearable_assembly',str(source),dict(links=params,physical=physical,max_landmark_error_m=max_landmark_error_m))
    native=json.loads(bounded_read(Path(validation['files'][0]),2*1024**2))
    # Native OpenSim owns schema upgrades. Mixing freshly serialized 4.6 joints
    # into an older document's original XML can trigger a second legacy upgrade.
    canonical=next(Path(f) for f in validation['files'] if Path(f).name=='assembled_model.osim')
    root,model=xml_model(bounded_read(canonical,MAX_MODEL))
    records=[]
    for item,fit in zip(parsed,native['links']):
        records.append(dict(name=item['name'],frame=fit['frame_path'],type='mesh',color=item['color'],scale=[item['unit_scale']*fit['uniform_scale']]*3,source_path=item['mesh_path']))
    # Preserve only approved body visuals, converting them into the fresh package.
    base_records,warnings=geometry(cfg,str(source),geometry_roots,1.)
    for parent in list(model.iter()):
        for child in list(parent):
            if child.tag in {'attached_geometry','VisibleObject'}:parent.remove(child)
    meshes,hashes=mesh_data(cfg,base_records+records)
    folder=cfg.results_root/('wearable-'+uuid.uuid4().hex);folder.mkdir(parents=True);assets=folder/'Geometry';assets.mkdir()
    owners={}
    def walk(node,current=''):
        if node.tag=='Ground':current='/ground'
        elif node.tag=='Body':current='/bodyset/'+node.get('name','')
        elif node.tag.endswith('Joint'):current='/jointset/'+node.get('name','')
        elif node.tag=='PhysicalOffsetFrame':current=current+'/'+node.get('name','')
        if node.tag in {'Ground','Body','PhysicalOffsetFrame'}:owners[current]=node
        for child in node:walk(child,current)
    walk(model)
    mesh_summary=[]
    for index,mesh in enumerate(meshes):
        owner=owners.get(mesh['frame'])
        if owner is None:warnings.append('Visual frame unavailable: '+mesh['frame']);continue
        filename='mesh-'+str(index)+'.obj';target=assets/filename
        with target.open('w',encoding='ascii') as stream:
            for row in mesh['vertices']:stream.write('v '+' '.join(format(v,'.15g') for v in row)+'\n')
            for row in mesh['triangles']:stream.write('f '+' '.join(str(v+1) for v in row)+'\n')
        attached=owner.find('attached_geometry')
        if attached is None:attached=ET.SubElement(owner,'attached_geometry')
        entry=ET.SubElement(attached,'Mesh',name='wearable_visual_'+str(index));ET.SubElement(entry,'socket_frame').text='..'
        ET.SubElement(entry,'mesh_file').text='Geometry/'+filename;ET.SubElement(entry,'scale_factors').text='1 1 1'
        appearance=ET.SubElement(entry,'Appearance');ET.SubElement(appearance,'color').text=' '.join(map(str,mesh['color']))
        mesh_summary.append(dict(frame=mesh['frame'],points=len(mesh['vertices']),triangles=len(mesh['triangles']),file=str(target),sha256=digest(target.read_bytes())))
    path=folder/'wearable_model.osim';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    result=dict(status='completed',model_file=str(path),model_sha256=digest(path.read_bytes()),physical=physical,quality=native['quality'],links=native['links'],coordinate_types=native['coordinate_types'],meshes=mesh_summary,
        mass_property_checks=[dict(name=item['name'],**validate_central_inertia(item['inertia_kg_m2'])) for item in parsed] if physical else [],
        reopened_body_mass_properties=native.get('reopened_body_mass_properties',[]),
        warnings=warnings,source_model_sha256=digest(raw),mesh_source_hashes=hashes,
        scope='Explicit rigid-body mass/inertia, supported joints and optional ideal linear coordinate couplings. Geometry alone supplies no guessed mass, axes, contact, strap stiffness or assistance. Input/API/GUI models unchanged.',
        files=[str(path)]+[m['file'] for m in mesh_summary])
    report=folder/'wearable_assembly.json';result['report_file']=str(report);result['files'].append(str(report));report.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result

def prepare_motion(cfg,assembly_report_path,coordinates_path):
    report=json.loads(bounded_read(cfg.input_path(assembly_report_path,'.json'),2*1024**2))
    model=cfg.input_path(report['model_file'],'.osim')
    if digest(bounded_read(model,MAX_MODEL))!=report['model_sha256']:raise InputError('Wearable model changed after its assembly report; rebuild/review assembly first.')
    source=Path(coordinates_path);cfg.input_path(coordinates_path,source.suffix.lower());table=read_motion(source);flag=table['in_degrees'].lower()
    if flag not in {'yes','no','true','false'}:raise InputError('Motion must explicitly declare inDegrees.')
    degree=flag in {'yes','true'};types=report['coordinate_types'];columns=table['columns'][:];rows=[row[:] for row in table['rows']]
    pending={link['coordinate']['name']:link for link in report['links'] if link.get('coupling')}
    while pending:
        progressed=False
        for name,link in list(pending.items()):
            coupling=link['coupling'];independent=coupling['independent_coordinate']
            if independent not in columns:continue
            if types.get(independent)!=types.get(name):raise InputError('Coupled motion units mismatch.')
            offset=coupling['offset']*(180/math.pi if degree and types[name]==1 else 1.)
            values=[coupling['scale']*row[columns.index(independent)]+offset for row in rows]
            factor=math.pi/180 if degree and types[name]==1 else 1.
            if any(not link['coordinate']['range'][0]-1e-9<=v*factor<=link['coordinate']['range'][1]+1e-9 for v in values):raise InputError('Coupled wearable coordinate exceeds configured range.')
            if name in columns:
                if any(abs(row[columns.index(name)]-v)*factor>1e-6 for row,v in zip(rows,values)):raise InputError('Existing device coordinate conflicts with the explicit coupling.')
            else:
                columns.append(name)
                for row,value in zip(rows,values):row.append(value)
            del pending[name];progressed=True
        if not progressed:raise InputError('Motion lacks an independent coupling coordinate or has cyclic mappings.')
    if set(types)-set(columns):raise InputError('Provide measured/prescribed motion for all independent wearable coordinates; missing: '+str(sorted(set(types)-set(columns))))
    folder=cfg.results_root/('wearable-motion-'+uuid.uuid4().hex);folder.mkdir(parents=True);target=folder/'coordinates.mot'
    header='Wearable explicit coupled coordinates\nversion=1\nnRows='+str(len(rows))+'\nnColumns='+str(len(columns))+'\ninDegrees='+('yes' if degree else 'no')+'\nendheader\n'
    target.write_text(header+'\t'.join(columns)+'\n'+'\n'.join('\t'.join(format(v,'.15g') for v in row) for row in rows)+'\n',encoding='utf-8');read_motion(target)
    return dict(motion_file=str(target),rows=len(rows),columns=columns,scope='Copies all original samples and adds only explicit linear device couplings; no resampling or invented independent motion.')
