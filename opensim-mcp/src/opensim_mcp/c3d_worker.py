"""Native C3D parser/converter. Launched in a disposable Windows Job Object."""
import json,re,sys
from pathlib import Path
import ezc3d
import numpy as np

def scalar_unit(value,kind):
    normalized=str(value).strip().lower().replace(' ','').replace('·','').replace('*','')
    options={'length':{'m':1.,'mm':.001},'force':{'n':1.},'moment':{'nm':1.,'nmm':.001}}
    if normalized not in options[kind]:raise ValueError('Unsupported '+kind+' unit: '+str(value))
    return options[kind][normalized]

def process(work,request):
    p=request['parameters'];extract=bool(p.get('plate_mappings'))
    trial=ezc3d.c3d(str(work/'input.c3d'),extract_forceplat_data=extract)
    points=trial['data']['points'];labels=list(trial['parameters']['POINT']['LABELS']['value']);rate=float(trial['parameters']['POINT']['RATE']['value'][0])
    if not 2<=points.shape[2]<=100000 or not 1<=len(labels)<=500 or len(labels)!=points.shape[1] or not np.isfinite(rate) or not 0<rate<=10000:raise ValueError('Unsupported marker dimensions/rate.')
    if len(set(labels))!=len(labels):raise ValueError('Duplicate C3D marker labels.')
    unit=trial['parameters']['POINT']['UNITS']['value'][0];scale=scalar_unit(unit,'length')
    residuals=trial['data'].get('meta_points',{}).get('residuals',np.zeros((1,len(labels),points.shape[2])))
    missing=(~np.isfinite(points[:3]).all(axis=0))|(residuals[0]<0)
    first=int(trial['header']['points']['first_frame']);analog_rate=float(trial['parameters']['ANALOG']['RATE']['value'][0])
    platform_count=int(trial['parameters'].get('FORCE_PLATFORM',{}).get('USED',{'value':[0]})['value'][0])
    info=dict(marker_names=labels,marker_count=len(labels),frames=points.shape[2],marker_rate_Hz=rate,
        point_unit=str(unit),first_frame=first,analog_rate_Hz=analog_rate,force_platform_count=platform_count,
        missing_samples={name:int(missing[i].sum()) for i,name in enumerate(labels)},native_reader='ezc3d '+ezc3d.__version__)
    if request['operation']=='inspect':return info
    indices=[labels.index(name) for name in (p['marker_names'] or labels)]
    if not indices:raise ValueError('No selected markers.')
    if any(missing[i].any() for i in indices):raise ValueError('Selected markers contain missing/nonfinite samples. Fill gaps explicitly before import.')
    names=[p['marker_name_map'].get(labels[i],labels[i]) for i in indices]
    if len(set(names))!=len(names) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,99}',n) for n in names):raise ValueError('Output marker names must be unique OpenSim-safe identifiers; provide marker_name_map.')
    unknown=set(p['marker_name_map'])-set(labels)
    if unknown:raise ValueError('Unknown source marker mapping: '+str(unknown))
    rotation=np.asarray(p['rotation'],dtype=float);xyz=np.einsum('ij,jkt->ikt',rotation,points[:3,indices,:]*scale)
    t0=0. if p['time_origin']=='zero' else first/rate;times=t0+np.arange(points.shape[2])/rate
    header=['PathFileType\t4\t(X/Y/Z)\tmarkers.trc','DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames',
      f'{rate:g}\t{rate:g}\t{len(times)}\t{len(names)}\tm\t{rate:g}\t1\t{len(times)}',
      'Frame#\tTime\t'+'\t\t\t'.join(names)+'\t\t','\t\t'+'\t'.join(f'{a}{i+1}' for i in range(len(names)) for a in 'XYZ'),'']
    rows=['\t'.join([str(j+1),format(float(t),'.12g')]+[format(float(xyz[a,i,j]),'.12g') for i in range(len(names)) for a in range(3)]) for j,t in enumerate(times)]
    (work/'markers.trc').write_text('\n'.join(header+rows)+'\n',encoding='utf-8')
    outputs=['markers.trc'];definitions=[];contacts=[];columns=['time'];arrays=[];sample_count=None
    for mapping in p['plate_mappings']:
        index=mapping['plate_index']
        if index>=len(trial['data']['platform']):raise ValueError('Force platform index does not exist.')
        plate=trial['data']['platform'][index];force=np.asarray(plate['force'],dtype=float)*scalar_unit(plate['unit_force'],'force')
        point=np.asarray(plate['center_of_pressure'],dtype=float)*scalar_unit(plate['unit_position'],'length')
        torque=np.asarray(plate['Tz'],dtype=float)*scalar_unit(plate['unit_moment'],'moment')
        if force.ndim!=2 or force.shape[0]!=3 or point.shape!=force.shape or torque.shape!=force.shape or not np.isfinite(force).all():raise ValueError('Invalid platform dimensions/forces.')
        n=force.shape[1]
        if not 0<analog_rate<=100000 or abs(analog_rate/rate-round(analog_rate/rate))>1e-8 or n!=len(times)*round(analog_rate/rate):raise ValueError('Unsynchronized analog/point sample dimensions.')
        if sample_count is not None and sample_count!=n:raise ValueError('Platform sampling differs.')
        sample_count=n;contact=np.abs(force[2])>=p['contact_threshold_N']
        if not np.isfinite(point[:,contact]).all() or not np.isfinite(torque[:,contact]).all():raise ValueError('COP/free moment is invalid during contact.')
        force[:,~contact]=0.;point[:,~contact]=0.;torque[:,~contact]=0.
        force=(rotation@force)*p['force_sign'];point=rotation@point;torque=(rotation@torque)*p['force_sign']
        stem=mapping['name'];arrays.extend([force.T,point.T,torque.T]);columns.extend([stem+'_'+kind+a for kind in ('force_v','force_p','torque_') for a in 'xyz'])
        definitions.append(dict(name=stem,applied_to_body=mapping['body'],force_identifier=stem+'_force_v',point_identifier=stem+'_force_p',torque_identifier=stem+'_torque_',force_expressed_in_body='ground',point_expressed_in_body='ground'))
        edges=np.diff(np.r_[False,contact,False].astype(int));starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)-1
        contacts.append(dict(name=stem,plate_index=index,body=mapping['body'],contact_fraction=float(contact.mean()),peak_force_N=float(np.linalg.norm(force,axis=0).max()),
            intervals_s=[[float(t0+a/analog_rate),float(t0+b/analog_rate)] for a,b in zip(starts,ends)]))
    if sample_count:
        samples=np.column_stack([t0+np.arange(sample_count)/analog_rate,*arrays])
        text='C3D external loads\nnRows='+str(sample_count)+'\nnColumns='+str(len(columns))+'\ninDegrees=no\nendheader\n'+'\t'.join(columns)+'\n'
        text+='\n'.join('\t'.join(format(float(v),'.12g') for v in row) for row in samples)+'\n'
        (work/'loads.mot').write_text(text,encoding='utf-8');outputs.append('loads.mot')
    result=dict(info,outputs=outputs,source_point_unit=info['point_unit'],converted_marker_names=names,marker_length_unit='m',force_unit='N',point_unit='m',torque_unit='Nm',external_forces=definitions,
        plate_contacts=contacts,source_to_opensim_rotation=p['rotation'],source_up_axis=p['source_up_axis'],force_sign=p['force_sign'],time_origin=p['time_origin'],time_range_s=[float(times[0]),float(times[-1])],
        scope='Explicit coordinate transform; ezc3d Z-up force filter. No automatic foot assignment, sign inference, gap filling or analog resampling.')
    (work/'trial.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');outputs.append('trial.json')
    return result

if __name__=='__main__':
    directory=Path(sys.argv[1]);request=json.loads((directory/'request.json').read_text(encoding='utf-8'))
    (directory/'result.json').write_text(json.dumps(process(directory,request),allow_nan=False),encoding='utf-8')
