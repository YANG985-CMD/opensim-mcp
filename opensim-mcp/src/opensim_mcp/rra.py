"""Explicit torque-driven RRA with original actuators restored in the saved model."""
import bisect,json,math
from pathlib import Path
from .core import InputError,MAX_MODEL,bounded_read,read_motion,xml_model
from .analysis import table_input,validate_loads,run_analysis
from .structured import run_native,actuator_definitions
from .workflows import finite

def run_rra(cfg,model_path,coordinates_path,actuators,task_weights,loads_path=None,external_forces=None,no_external_loads=False,
            start_time=None,end_time=None,lowpass_cutoff_hz=6.,adjust_com_body=None,kp=100.,kv=20.,max_tracking_error=None,compare_inverse_dynamics=True):
    _,model=xml_model(bounded_read(cfg.input_path(model_path,'.osim'),MAX_MODEL));_,_,table=table_input(cfg,coordinates_path)
    definitions=actuator_definitions(actuators);names={e.get('name') for e in model.iter('Coordinate')}
    if not names<=set(table['columns']) or table['in_degrees'].lower() not in {'yes','no','true','false'}:raise InputError('RRA requires all coordinates and explicit inDegrees.')
    if len(table['rows'])<6:raise InputError('RRA requires at least six reference samples.')
    if not isinstance(task_weights,dict) or not task_weights or set(task_weights)-names:raise InputError('Explicit coordinate task_weights required.')
    for n,w in task_weights.items():finite(w,'task '+n,1e-9,1e9)
    for n in ('no_external_loads','compare_inverse_dynamics'):
        if type(locals()[n]) is not bool:raise InputError(n+' must be boolean.')
    start=table['rows'][0][0] if start_time is None else start_time;end=table['rows'][-1][0] if end_time is None else end_time
    finite(start,'start_time',0,1e6);finite(end,'end_time',0,1e6)
    if not table['rows'][0][0]<=start<end<=table['rows'][-1][0] or end-start>100:raise InputError('RRA window must be covered and <=100 s.')
    finite(lowpass_cutoff_hz,'cutoff',.01,1000);finite(kp,'kp',.001,1e6);finite(kv,'kv',.001,1e6)
    if max_tracking_error is not None:
        if not isinstance(max_tracking_error,dict) or set(max_tracking_error)-names:raise InputError('Unknown coordinate tracking limit.')
        for n,v in max_tracking_error.items():finite(v,n,0,1e6)
    if adjust_com_body is not None and adjust_com_body not in {e.get('name') for e in model.iter('Body')}:raise InputError('Unknown COM adjustment body.')
    if adjust_com_body:
        residuals={d['name']:d for d in definitions if d['role']=='residual'}
        if not {'FX','FY','FZ','MX','MY','MZ'}<=residuals.keys():raise InputError('Native COM adjustment requires explicitly named FX/FY/FZ/MX/MY/MZ residual actuators.')
        if any(residuals[n]['unit']!=('N' if n.startswith('F') else 'Nm') for n in ('FX','FY','FZ','MX','MY','MZ')):raise InputError('COM residuals FX/FY/FZ require N, MX/MY/MZ require Nm.')
    forces=[];assets={'coordinates.sto':coordinates_path}
    if loads_path:
        if no_external_loads:raise InputError('Cannot combine loads with no_external_loads.')
        _,_,loads=table_input(cfg,loads_path);forces=validate_loads(model,loads,external_forces)
        if loads['rows'][0][0]>start or loads['rows'][-1][0]<end:raise InputError('Loads do not cover RRA window.')
        assets['loads.sto']=loads_path
    elif external_forces or not no_external_loads:raise InputError('RRA requires explicit loads or no_external_loads=true.')
    parameters=dict(actuators=definitions,task_weights=task_weights,external_forces=forces,no_external_loads=no_external_loads,
        start_time=start,end_time=end,lowpass_cutoff_hz=lowpass_cutoff_hz,adjust_com_body=adjust_com_body,kp=kp,kv=kv,
        in_degrees=table['in_degrees'],max_tracking_error=max_tracking_error or {})
    result=run_native(cfg,'rra',model_path,parameters,assets)
    if compare_inverse_dynamics:
        folder=Path(result['model_file']).parent;actual_start,actual_end=result['quality']['time_range_s']
        samples=[row[0] for row in table['rows'] if max(start,actual_start)<=row[0]<=min(end,actual_end)]
        if len(samples)<6:raise InputError('RRA/ID comparison requires six common reference samples; widen the window or disable the explicit comparison.')
        compare_start,compare_end=samples[0],samples[-1]
        actual_table=read_motion(folder/'rra_coordinates.mot')
        def resample(source,path):
            times=[row[0] for row in source['rows']];rows=[]
            for t in samples:
                i=max(0,min(len(times)-2,bisect.bisect_right(times,t)-1));a,b=source['rows'][i:i+2];w=(t-a[0])/(b[0]-a[0])
                rows.append([t]+[a[k]+w*(b[k]-a[k]) for k in range(1,len(a))])
            text='RRA comparison\nversion=1\nnRows='+str(len(rows))+'\nnColumns='+str(len(source['columns']))+'\ninDegrees='+source['in_degrees']+'\nendheader\n'+'\t'.join(source['columns'])+'\n'
            path.write_text(text+'\n'.join('\t'.join(format(v,'.17g') for v in row) for row in rows)+'\n',encoding='utf-8')
        before_reference=folder/'comparison_before.sto';after_reference=folder/'comparison_after.sto'
        resample(table,before_reference);resample(actual_table,after_reference);result['files']+=[str(before_reference),str(after_reference)]
        before=run_analysis(cfg,'id',model_path,str(before_reference),loads_path,forces or None,no_external_loads,compare_start,compare_end,lowpass_cutoff_hz)
        after=run_analysis(cfg,'id',result['model_file'],str(after_reference),loads_path,forces or None,no_external_loads,compare_start,compare_end,lowpass_cutoff_hz)
        values=[]
        for r in (before,after):
            path=next(Path(f) for f in r['files'] if f.endswith('inverse_dynamics.sto'));t=read_motion(path);residual={}
            for d in definitions:
                if d['role']!='residual':continue
                suffix='_moment' if d['unit']=='Nm' else '_force';index=t['columns'].index(d['coordinate']+suffix);data=[row[index] for row in t['rows']]
                residual[d['name']]={'rms':math.sqrt(sum(v*v for v in data)/len(data)),'peak_abs':max(abs(v) for v in data),'unit':d['unit']}
            values.append(residual)
        result['id_comparison']={'before':values[0],'after':values[1],'files_before':before['files'],'files_after':after['files'],'time_range_s':[compare_start,compare_end],
            'sampling':'Both trajectories sampled linearly on common original reference times, without extrapolation; same filter/window.',
            'note':'Measured before/after residual coordinate forces; a reduction is not guaranteed. Original actuators restored; mass recommendations are not applied.'}
        (folder/'id_comparison.json').write_text(json.dumps(result['id_comparison'],indent=2,allow_nan=False),encoding='utf-8')
        result['files'].append(str(folder/'id_comparison.json'))
        (folder/'provenance.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result
