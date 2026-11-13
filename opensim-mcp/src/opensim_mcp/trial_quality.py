"""Explicit force-event cycles and complete named trajectory comparisons."""
import json,math
import bisect,uuid
from pathlib import Path
from .core import InputError,bounded_read,read_motion

def resample_coordinates(cfg,coordinates_path,frequency_hz,start_time=None,end_time=None):
    path=Path(coordinates_path)
    if path.suffix.lower() not in {'.mot','.sto'}:raise InputError('Coordinates must be MOT/STO.')
    cfg.input_path(coordinates_path,path.suffix.lower());table=read_motion(path)
    if type(frequency_hz) not in {int,float} or not math.isfinite(frequency_hz) or not .1<=frequency_hz<=1000:raise InputError('Explicit frequency must be .1..1000 Hz.')
    times=[r[0] for r in table['rows']];start=times[0] if start_time is None else start_time;end=times[-1] if end_time is None else end_time
    if any(type(t) not in {int,float} or not math.isfinite(t) for t in (start,end)) or not times[0]<=start<end<=times[-1]:raise InputError('Requested resampling window must be covered; no extrapolation.')
    if table['in_degrees'].lower() not in {'yes','no','true','false'}:raise InputError('Declare inDegrees before resampling coordinates.')
    count=int(math.floor((end-start)*frequency_hz+1e-9))+1
    if not 2<=count<=100000:raise InputError('Resampling needs 2..100000 output rows.')
    output=[]
    for k in range(count):
        t=start+k/frequency_hz;i=max(0,min(len(times)-2,bisect.bisect_right(times,t)-1));a,b=table['rows'][i:i+2];w=(t-a[0])/(b[0]-a[0])
        output.append([t]+[a[j]+w*(b[j]-a[j]) for j in range(1,len(a))])
    folder=cfg.results_root/('resampled-coordinates-'+uuid.uuid4().hex);folder.mkdir(parents=True);target=folder/'coordinates.mot'
    target.write_text('Explicit linear coordinate resampling\nversion=1\nnRows='+str(count)+'\nnColumns='+str(len(table['columns']))+'\ninDegrees='+table['in_degrees']+'\nendheader\n'+'\t'.join(table['columns'])+'\n'+'\n'.join('\t'.join(format(v,'.17g') for v in r) for r in output)+'\n',encoding='utf-8')
    from .projects import digest
    result=dict(motion_file=str(target),source_sha256=digest(bounded_read(path,64*1024**2)),source_rows=len(times),output_rows=count,frequency_hz=frequency_hz,
        requested_window_s=[start,end],actual_window_s=[output[0][0],output[-1][0]],method='linear',no_extrapolation=True,
        scope='Explicit resampling of numeric coordinate columns; preserves angle-unit declaration. No smoothing, gap filling, angle unwrapping or claim of recovered acquisition timing. Final time is the last full uniform-grid sample.')
    (folder/'resampling.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

def gait_cycles(cfg,loads_path,vertical_force_column,on_threshold_N=20.,off_threshold_N=10.,force_sign=1.,minimum_stance_s=.05,minimum_swing_s=.05):
    for name,value in [('on threshold',on_threshold_N),('off threshold',off_threshold_N),('minimum stance',minimum_stance_s),('minimum swing',minimum_swing_s)]:
        if type(value) not in {int,float} or not math.isfinite(value) or value<0:raise InputError('Invalid '+name)
    if type(force_sign) not in {int,float} or force_sign not in {-1.,1.} or not off_threshold_N<on_threshold_N or min(minimum_stance_s,minimum_swing_s)<=0:raise InputError('Explicit sign and ordered positive event settings required.')
    path=Path(loads_path);cfg.input_path(loads_path,path.suffix.lower());table=read_motion(path)
    if vertical_force_column not in table['columns'] or vertical_force_column=='time':raise InputError('Choose the measured upward force column explicitly, in N.')
    index=table['columns'].index(vertical_force_column);rows=table['rows'];contact=force_sign*rows[0][index]>=on_threshold_N;start=None;intervals=[]
    initial_contact=contact
    for row in rows[1:]:
        force=force_sign*row[index]
        if not contact and force>=on_threshold_N:contact=True;start=row[0]
        elif contact and force<=off_threshold_N:
            if start is not None and row[0]-start>=minimum_stance_s:intervals.append(dict(onset_s=start,offset_s=row[0]))
            contact=False;start=None
    if contact and start is not None and rows[-1][0]-start>=minimum_stance_s:intervals.append(dict(onset_s=start,offset_s=None))
    cycles=[]
    for a,b in zip(intervals,intervals[1:]):
        if a['offset_s'] is None or b['onset_s']-a['offset_s']<minimum_swing_s:continue
        cycles.append(dict(start_time=a['onset_s'],end_time=b['onset_s'],duration_s=b['onset_s']-a['onset_s'],stance_duration_s=a['offset_s']-a['onset_s']))
    return dict(cycles=cycles,contacts=intervals,initial_contact_onset_unknown=initial_contact,vertical_force_column=vertical_force_column,
        force_units='N',force_sign=force_sign,on_threshold_N=on_threshold_N,off_threshold_N=off_threshold_N,minimum_stance_s=minimum_stance_s,minimum_swing_s=minimum_swing_s,
        source_time_range_s=[rows[0][0],rows[-1][0]],event_definition='First source sample meeting the threshold; no interpolation. Cycle is two accepted onsets of this same measured foot/platform column.',
        scope='Force-event segmentation only. Caller confirms upward axis/sign/foot mapping and supplies kinematics covering both events; no anatomical/physiological validation.')

def assess_mesh(cfg,study_report_path,state_rms_limits,control_rms_limits):
    report=json.loads(bounded_read(cfg.input_path(study_report_path,'.json'),8*1024**2));comparisons=report.get('comparisons')
    if not isinstance(comparisons,list) or not 1<=len(comparisons)<=3:raise InputError('Expected a generated mesh study with 1..3 comparisons.')
    for value in (state_rms_limits,control_rms_limits):
        if not isinstance(value,dict) or not value or len(value)>1000 or any(not isinstance(k,str) or type(v) not in {int,float} or not math.isfinite(v) or v<0 for k,v in value.items()):raise InputError('Explicit complete named RMS limits required.')
    results=[]
    for comparison in comparisons:
        if type(comparison.get('objective_pass')) is not bool:raise InputError('Mesh objective check must be a measured boolean result.')
        if set(comparison['states'])!=set(state_rms_limits) or set(comparison['controls'])!=set(control_rms_limits):raise InputError('RMS limits must cover every state and control exactly; no unassessed columns.')
        failed=[]
        for kind,limits in [('states',state_rms_limits),('controls',control_rms_limits)]:
            for name,limit in limits.items():
                value=comparison[kind][name]['rms']
                if type(value) not in {int,float} or not math.isfinite(value):raise InputError('Invalid/nonfinite measured trajectory RMS.')
                if value>limit:failed.append(dict(kind=kind,column=name,rms=value,limit=limit))
        results.append(dict(coarse_interval_s=comparison['coarse_interval_s'],fine_interval_s=comparison['fine_interval_s'],objective_pass=bool(comparison['objective_pass']),
            all_state_and_control_columns_assessed=True,failed_columns=failed,configured_checks_pass=bool(comparison['objective_pass']) and not failed))
    return dict(comparisons=results,state_rms_limits=state_rms_limits,control_rms_limits=control_rms_limits,
        status='configured_checks_passed' if results[-1]['configured_checks_pass'] else 'needs_review',
        scope='Every named state/control on shared interpolated trajectory times plus the original objective check. Caller limits are numerical criteria, not a convergence proof or physiological acceptance.')

def audit_trajectory(cfg,model_path,coordinates_path,states_path,controls_path,loads_path=None,external_forces=None,no_external_loads=False,ignore_tendon_compliance=False):
    from .tracking import reference_inputs
    from .structured import run_native
    tables=[]
    for value in (states_path,controls_path):
        path=Path(value)
        if path.suffix.lower() not in {'.sto','.mot'}:raise InputError('State/control tables must be STO/MOT.')
        cfg.input_path(value,path.suffix.lower());tables.append(read_motion(path))
    states,controls=tables
    if len(states['rows'])>1000 or states['in_degrees'].lower() not in {'no','false'}:raise InputError('Audit <=1000 full native-radian state nodes.')
    times=[r[0] for r in states['rows']]
    if len(controls['rows'])!=len(times) or any(abs(r[0]-t)>1e-9 for r,t in zip(controls['rows'],times)):raise InputError('State/control audit nodes must coincide exactly.')
    if type(ignore_tendon_compliance) is not bool:raise InputError('Explicit tendon option must be boolean.')
    assets,forces=reference_inputs(cfg,model_path,coordinates_path,times[0],times[-1],loads_path,external_forces,no_external_loads)
    assets.update({'states.sto':states_path,'controls.sto':controls_path})
    return run_native(cfg,'trajectory_audit',model_path,dict(external_forces=forces,ignore_tendon_compliance=ignore_tendon_compliance),assets)
