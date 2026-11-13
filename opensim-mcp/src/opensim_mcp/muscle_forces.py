"""Explicit muscle-force studies, numeric quality and source-traceable volumes."""
from __future__ import annotations
import csv,hashlib,json,math,uuid,tempfile
from dataclasses import replace
from pathlib import Path
from .core import InputError,MAX_MODEL,bounded_read,read_motion,xml_model
from .structured import run_native,configure_actuators,actuator_definitions
from .analysis import run_analysis
from .workflows import finite
from .progress import report as progress

def digest(data):return hashlib.sha256(data).hexdigest()
def metadata(cfg,model_path):
    result=run_native(cfg,'muscle_metadata',model_path,{})
    return json.loads(bounded_read(Path(result['files'][0]),2*1024**2))

def validate_limits(limits):
    keys={'max_reserve_peak_fraction','max_residual_actuator_force_N','max_residual_actuator_moment_Nm'}
    if not isinstance(limits,dict) or set(limits)!=keys:raise InputError('Provide all three explicit reserve/residual quality limits.')
    return {name:finite(value,name,0,1e6) for name,value in limits.items()}

def statistics(times,values):
    duration=times[-1]-times[0]
    integral=sum((b-a)*(x+y)/2 for a,b,x,y in zip(times,times[1:],values,values[1:]))
    integral_square=sum((b-a)*(x*x+y*y)/2 for a,b,x,y in zip(times,times[1:],values,values[1:]))
    return dict(peak=max(values),peak_abs=max(abs(v) for v in values),mean=integral/duration,rms=math.sqrt(integral_square/duration),integral=integral)

def assess_series(times,forces,activations,reference,definitions,limits):
    """All definitions are explicit; zero reference demand is never divided by."""
    limits=validate_limits(limits);checks=[];actuators={}
    for d in definitions:
        column=d['coordinate']+('_moment' if d['unit']=='Nm' else '_force')
        if d['name'] not in forces or column not in reference:raise InputError('Missing classified actuator force or matching ID column.')
        values=forces[d['name']];peak=max(abs(v) for v in values);denominator=max(abs(v) for v in reference[column])
        ratio=peak/denominator if denominator>1e-8 else (0. if peak<1e-8 else None)
        if d['role']=='reserve':value=ratio;limit=limits['max_reserve_peak_fraction']
        else:value=peak;limit=limits['max_residual_actuator_force_N' if d['unit']=='N' else 'max_residual_actuator_moment_Nm']
        passed=value is not None and value<=limit
        checks.append(dict(name=d['name'],role=d['role'],unit=d['unit'],value=value,limit=limit,passed=passed))
        actuators[d['name']]=dict(statistics(times,values),unit=d['unit'],role=d['role'],peak_fraction_ID=ratio)
    for name,values in activations.items():
        if any(not -1e-6<=v<=1.000001 for v in values):raise InputError('Muscle activation is outside [0,1]: '+name)
    return dict(status='pass' if all(c['passed'] for c in checks) else 'needs_review',checks=checks,actuators=actuators,
                failed_checks=[c['name'] for c in checks if not c['passed']],
                scope='Explicit numerical limits only; not physiological validation, assistance efficacy or measured individual muscle force.')

def _table(path):
    table=read_motion(Path(path));return [r[0] for r in table['rows']],{c:[r[i] for r in table['rows']] for i,c in enumerate(table['columns']) if i}

def _force_study(cfg,model_path,coordinates_path,actuator_profile,quality_limits,loads_path=None,external_forces=None,
                no_external_loads=False,lowpass_cutoff_hz=None,label='',optimizer_max_iterations=2000):
    limits=validate_limits(quality_limits);definitions=actuator_definitions(actuator_profile)
    if not isinstance(label,str) or len(label)>120:raise InputError('Study label must be short text.')
    source=cfg.input_path(model_path,'.osim');source_hash=digest(bounded_read(source,MAX_MODEL));meta=metadata(cfg,model_path)
    if not meta['muscles']:raise InputError('A muscle-force study needs native model muscles.')
    progress('preparing_muscle_actuators',case=label)
    profile=configure_actuators(cfg,model_path,definitions);solver=profile['model_file']
    progress('solving_muscle_reference_ID',case=label)
    reference=run_analysis(cfg,'id',solver,coordinates_path,loads_path,external_forces,no_external_loads,lowpass_cutoff_hz=lowpass_cutoff_hz)
    progress('solving_muscle_forces',case=label)
    solved=run_analysis(cfg,'static_optimization',solver,coordinates_path,loads_path,external_forces,no_external_loads,
                        lowpass_cutoff_hz=lowpass_cutoff_hz,optimizer_max_iterations=optimizer_max_iterations)
    def output(term):
        paths=[f for f in solved['files'] if term in Path(f).name.lower()]
        if len(paths)!=1:raise InputError('Expected one native '+term+' table.')
        return paths[0]
    force_file=output('force');activation_file=output('activation')
    times,forces=_table(force_file);other,activations=_table(activation_file)
    id_file=next(f for f in reference['files'] if Path(f).name=='inverse_dynamics.sto');id_times,id_values=_table(id_file)
    if len(times)!=len(other) or len(times)!=len(id_times) or any(abs(a-b)>1e-6 or abs(a-c)>1e-6 for a,b,c in zip(times,other,id_times)):raise InputError('SO force/activation and ID samples must coincide.')
    names=set(meta['muscles']);classified={d['name'] for d in definitions}
    external_columns={f['applied_to_body']+'_'+f['name']+'_'+suffix for f in (external_forces or []) for suffix in ('Fx','Fy','Fz','Tx','Ty','Tz','px','py','pz')}
    if not names<=set(forces) or not names<=set(activations) or set(forces)-names-classified-external_columns:raise InputError('All native muscle and non-muscle actuator forces must be present and explicitly classified.')
    if any(v < -1e-6 for n in names for v in forces[n]):raise InputError('Negative muscle tension encountered.')
    progress('assessing_muscle_force_quality',case=label)
    quality=assess_series(times,forces,{n:activations[n] for n in names},id_values,definitions,limits)
    metrics={n:dict(force_N=statistics(times,forces[n]),activation=statistics(times,activations[n])) for n in sorted(names)}
    context=dict(coordinates_sha256=digest(bounded_read(cfg.input_path(coordinates_path,Path(coordinates_path).suffix.lower()),64*1024**2)),
                 loads_sha256=digest(bounded_read(cfg.input_path(loads_path,Path(loads_path).suffix.lower()),64*1024**2)) if loads_path else None,
                 external_forces=external_forces or [],no_external_loads=no_external_loads,lowpass_cutoff_hz=lowpass_cutoff_hz,
                 actuator_profile=definitions,optimizer_max_iterations=optimizer_max_iterations,quality_limits=limits)
    report=dict(schema='opensim_muscle_force_study_v1',label=label or 'Muscle-force estimate',source_model_sha256=source_hash,
                source_model_physics_signature=meta['physics_signature'],muscle_parameters=meta['muscles'],study_context=context,
                context_sha256=digest(json.dumps(context,sort_keys=True,allow_nan=False).encode()),quality=quality,metrics=metrics,
                series=dict(times=times,forces_N={n:forces[n] for n in sorted(names)},activations={n:activations[n] for n in sorted(names)}),
                audit_series=dict(actuator_forces={d['name']:forces[d['name']] for d in definitions},reference_ID=id_values),
                solver='OpenSim StaticOptimization',native_run=solved,reference_ID=reference,solver_model_file=solver,
                raw_output_sha256={Path(p).name:digest(Path(p).read_bytes()) for p in (force_file,activation_file,id_file)},
                scope='Predicted muscle tensions under prescribed motion and external loads with explicit reserve/residual actuators. No activation dynamics, tendon compliance, measured muscle-force claim or interface/contact-pressure inference.')
    folder=cfg.results_root/('muscle-force-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    target=folder/'muscle_force_study.json';report['report_file']=str(target)
    target.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    with (folder/'muscle_metrics.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['muscle','peak_force_N','mean_force_N','rms_force_N','force_impulse_N_s','peak_activation'])
        for n,m in metrics.items():writer.writerow([n,m['force_N']['peak'],m['force_N']['mean'],m['force_N']['rms'],m['force_N']['integral'],m['activation']['peak']])
    return dict(status='completed',report_file=str(target),metrics_file=str(folder/'muscle_metrics.csv'),muscle_count=len(names),quality=quality,label=report['label'],time_range=[times[0],times[-1]],scope=report['scope'])

def force_study(cfg,model_path,coordinates_path,actuator_profile,quality_limits,loads_path=None,external_forces=None,
                no_external_loads=False,lowpass_cutoff_hz=None,label='',optimizer_max_iterations=2000):
    # Metadata, ID and SO must see the same immutable snapshot of each input.
    with tempfile.TemporaryDirectory(prefix='muscle-study-inputs-',dir=cfg.temp_root) as folder:
        root=Path(folder);paths=[]
        for name,value,maximum in (('model',model_path,MAX_MODEL),('coordinates',coordinates_path,64*1024**2),('loads',loads_path,64*1024**2)):
            if value is None:paths.append(None);continue
            suffix=Path(value).suffix.lower()
            if suffix not in ({'.osim'} if name=='model' else {'.mot','.sto'}):raise InputError('Unsupported study input extension.')
            source=cfg.input_path(value,suffix);target=root/(name+suffix);target.write_bytes(bounded_read(source,maximum));paths.append(str(target))
        pinned=replace(cfg,allowed_roots=(*cfg.allowed_roots,root))
        return _force_study(pinned,paths[0],paths[1],actuator_profile,quality_limits,paths[2],external_forces,no_external_loads,lowpass_cutoff_hz,label,optimizer_max_iterations)

def load_report(cfg,path):
    report=json.loads(bounded_read(cfg.input_path(path,'.json'),32*1024**2))
    if report.get('schema')!='opensim_muscle_force_study_v1':raise InputError('Expected a muscle-force study report.')
    s=report.get('series',{});times=s.get('times',[]);forces=s.get('forces_N',{});activations=s.get('activations',{})
    if not 2<=len(times)<=100000 or any(type(t) not in {float,int} or not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):raise InputError('Invalid muscle result time series.')
    if not isinstance(forces,dict) or not 1<=len(forces)<=300 or set(forces)!=set(activations):raise InputError('Muscle force/activation columns differ.')
    for field in (forces,activations):
        for name,values in field.items():
            if not isinstance(name,str) or len(name)>500 or not isinstance(values,list) or len(values)!=len(times) or any(type(v) not in {float,int} or not math.isfinite(v) for v in values):raise InputError('Invalid muscle result samples.')
    if any(v< -1e-6 for values in forces.values() for v in values) or any(not -1e-6<=v<=1.000001 for values in activations.values() for v in values):raise InputError('Muscle result tension/activation bounds invalid.')
    context=report.get('study_context')
    if digest(json.dumps(context,sort_keys=True,allow_nan=False).encode())!=report.get('context_sha256'):raise InputError('Muscle study context hash mismatch.')
    audit=report.get('audit_series',{})
    for field in (audit.get('actuator_forces',{}),audit.get('reference_ID',{})):
        if not isinstance(field,dict):raise InputError('Invalid actuator quality series.')
        for values in field.values():
            if not isinstance(values,list) or len(values)!=len(times) or any(type(v) not in {int,float} or not math.isfinite(v) for v in values):raise InputError('Invalid actuator quality samples.')
    definitions=actuator_definitions(context['actuator_profile'])
    report['quality']=assess_series(times,audit.get('actuator_forces',{}),activations,audit.get('reference_ID',{}),definitions,context['quality_limits'])
    return report

def compare_studies(cfg,baseline_model_path,assembly_report_path,coordinates_path,actuator_profile,quality_limits,
                    loads_path=None,external_forces=None,no_external_loads=False,lowpass_cutoff_hz=None,optimizer_max_iterations=2000):
    assembly=json.loads(bounded_read(cfg.input_path(assembly_report_path,'.json'),2*1024**2));base=cfg.input_path(baseline_model_path,'.osim');combined=cfg.input_path(assembly['model_file'],'.osim')
    if digest(base.read_bytes())!=assembly['source_model_sha256'] or digest(combined.read_bytes())!=assembly['model_sha256']:raise InputError('Wearable assembly/source model hashes changed.')
    if not assembly['physical'] or any(link['joint_type']!='WeldJoint' for link in assembly['links']):raise InputError('Matched muscle study currently supports verified welded mass-only devices.')
    common=dict(coordinates_path=coordinates_path,actuator_profile=actuator_profile,quality_limits=quality_limits,loads_path=loads_path,
                external_forces=external_forces,no_external_loads=no_external_loads,lowpass_cutoff_hz=lowpass_cutoff_hz,optimizer_max_iterations=optimizer_max_iterations)
    first=force_study(cfg,str(base),label='未穿戴',**common);second=force_study(cfg,str(combined),label='穿戴装置（质量负担）',**common)
    a=load_report(cfg,first['report_file']);b=load_report(cfg,second['report_file'])
    if a['context_sha256']!=b['context_sha256'] or a['series']['times']!=b['series']['times'] or set(a['metrics'])!=set(b['metrics']):raise InputError('Matched studies differ in context, time grid or muscle set.')
    differences={}
    for name in a['metrics']:
        x,y=a['metrics'][name]['force_N'],b['metrics'][name]['force_N']
        differences[name]={key:dict(baseline=x[key],wearable=y[key],difference=y[key]-x[key],percent_change=100*(y[key]-x[key])/x[key] if abs(x[key])>1e-8 else None) for key in ('peak','mean','rms','integral')}
    folder=cfg.results_root/('muscle-comparison-'+uuid.uuid4().hex);folder.mkdir(parents=True);target=folder/'comparison.json'
    report=dict(schema='opensim_matched_muscle_comparison_v1',baseline=first,wearable=second,differences=differences,
                quality_status='pass' if first['quality']['status']==second['quality']['status']=='pass' else 'needs_review',
                scope='Same prescribed motion, measured/modeled external loads, muscle parameters and SO settings; verified welded device masses only. Differences do not establish active assistance, altered gait, clinical benefit or measured force reduction.')
    target.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8');return dict(report_file=str(target),**report)

def estimate_volumes(cfg,model_path,specific_tension_Pa=None,measured_volumes_cm3=None,measurement_source=''):
    measured={} if measured_volumes_cm3 is None else measured_volumes_cm3
    if not isinstance(measured,dict):raise InputError('measured_volumes_cm3 must map muscle names to volumes.')
    if specific_tension_Pa is not None:finite(specific_tension_Pa,'specific_tension_Pa',1,1e9)
    if measured and (not isinstance(measurement_source,str) or not measurement_source.strip() or len(measurement_source)>1000):raise InputError('Measured volumes require a short measurement_source description.')
    meta=metadata(cfg,model_path);muscles=meta['muscles']
    if not muscles or set(measured)-set(muscles):raise InputError('Provide known native muscle names.')
    if set(muscles)-set(measured) and specific_tension_Pa is None:raise InputError('Provide explicit specific tension for all unmeasured model muscles.')
    rows={}
    for name,p in muscles.items():
        volume=finite(measured[name],name,1e-12,1e9) if name in measured else p['max_isometric_force_N']*p['optimal_fiber_length_m']/specific_tension_Pa*1e6
        finite(volume,name+' volume',1e-12,1e9)
        rows[name]=dict(volume_cm3=volume,source='supplied_measurement' if name in measured else 'parameter_estimate',
                        source_label=measurement_source if name in measured else 'V = Fmax * optimal_fiber_length / explicitly assumed specific_tension',
                        specific_tension_Pa=None if name in measured else specific_tension_Pa)
    folder=cfg.results_root/('muscle-volumes-'+uuid.uuid4().hex);folder.mkdir(parents=True);target=folder/'volumes.json'
    report=dict(schema='opensim_muscle_volumes_v1',source_model_physics_signature=meta['physics_signature'],muscles=rows,
                total_model_actuator_volume_cm3=sum(v['volume_cm3'] for v in rows.values()),
                scope='Supplied measurements are recorded, not independently verified. Parameter estimates use assumed specific tension and model fiber parameters; not individualized anatomy or whole-body volume. No pennation cosine is applied to the native maximum fiber force.')
    target.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8');return dict(report_file=str(target),**report)
