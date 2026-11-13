"""Bounded study-to-animation binding without extrapolation or guessed columns."""
import bisect,json,math
from .core import InputError,bounded_read
from .muscle_forces import load_report

def sample_series(series,requested_times,names,interpolation):
    if interpolation not in {'none','linear'}:raise InputError('muscle_data_interpolation must be none or linear.')
    times=series['times'];dt=min(b-a for a,b in zip(times,times[1:]));tolerance=min(1e-6,dt*.001)
    output=[]
    for t in requested_times:
        i=bisect.bisect_left(times,t);near=min((j for j in (i-1,i) if 0<=j<len(times)),key=lambda j:abs(times[j]-t))
        if abs(times[near]-t)<=tolerance:a=b=near;weight=0.
        else:
            if interpolation!='linear':raise InputError('Muscle and animation samples differ; explicitly choose linear interpolation.')
            if not 0<i<len(times):raise InputError('Muscle result interpolation cannot extrapolate.')
            a,b=i-1,i
            if times[b]-times[a]>3*dt:raise InputError('Muscle result gap exceeds three minimum sample periods.')
            weight=(t-times[a])/(times[b]-times[a])
        output.append({field:{n:series[field][n][a]+weight*(series[field][n][b]-series[field][n][a]) for n in names} for field in ('forces_N','activations')})
    return output

def bind(cfg,data,motion_sha256,primary_path=None,comparison_path=None,volume_path=None,interpolation='none'):
    names=data.get('muscle_names',[]);times=[f['time'] for f in data['frames']]
    if comparison_path and not primary_path:raise InputError('A comparison muscle report needs a primary muscle report.')
    reports=[]
    for index,path in enumerate((primary_path,comparison_path)):
        if path is None:continue
        r=load_report(cfg,path)
        if not set(names)<=set(r['series']['forces_N']):raise InputError('Muscle results omit displayed model muscles.')
        if r['study_context']['coordinates_sha256']!=motion_sha256:raise InputError('Muscle report was calculated from different coordinate file bytes.')
        if index==0 and r['source_model_physics_signature']!=data['physics_signature']:raise InputError('Primary muscle report physics differ from the current model.')
        if index and r['context_sha256']!=reports[0]['context_sha256']:raise InputError('Muscle comparison motion, loads or solver settings differ.')
        values=sample_series(r['series'],times,names,interpolation)
        prefix='' if index==0 else 'comparison_'
        for frame,value in zip(data['frames'],values):
            frame[prefix+'muscle_forces_N']=value['forces_N'];frame[prefix+'muscle_activations']=value['activations']
        reports.append(r)
    data['muscle_result_info']=[dict(label=r.get('label','Muscle-force estimate'),quality=r['quality'],
        lowpass_cutoff_hz=r['study_context']['lowpass_cutoff_hz'],solver=r['solver'],source_model_sha256=r['source_model_sha256']) for r in reports]
    data['muscle_data_interpolation']=interpolation
    if volume_path:
        r=json.loads(bounded_read(cfg.input_path(volume_path,'.json'),2*1024**2))
        if r.get('schema')!='opensim_muscle_volumes_v1' or r.get('source_model_physics_signature')!=data['physics_signature']:raise InputError('Volume report belongs to different model physics.')
        muscles=r.get('muscles',{})
        if not set(names)<=set(muscles):raise InputError('Volume report omits displayed muscles.')
        for n in names:
            v=muscles[n]
            if type(v.get('volume_cm3')) not in {int,float} or not math.isfinite(v['volume_cm3']) or v['volume_cm3']<=0 or v.get('source') not in {'supplied_measurement','parameter_estimate'}:raise InputError('Volume values or provenance are invalid.')
            if not isinstance(v.get('source_label'),str) or not v['source_label'] or len(v['source_label'])>1000:raise InputError('Volume source label is required.')
            if v['source']=='parameter_estimate' and (type(v.get('specific_tension_Pa')) not in {int,float} or not math.isfinite(v['specific_tension_Pa']) or v['specific_tension_Pa']<=0):raise InputError('Estimated volume requires explicit positive specific tension.')
        data['muscle_volumes']={n:muscles[n] for n in names}
    return data
