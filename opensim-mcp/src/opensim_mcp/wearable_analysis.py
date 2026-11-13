"""Matched ID comparison for explicitly welded wearable mass and ideal assist."""
import json,math,uuid
from pathlib import Path
from .core import InputError,MAX_MODEL,bounded_read,read_motion,xml_model
from .projects import digest
from .analysis import run_analysis

def compare_id(cfg,baseline_model_path,assembly_report_path,coordinates_path,loads_path=None,external_forces=None,no_external_loads=False,
               lowpass_cutoff_hz=None,assistance_path=None,assistance_mapping=None):
    baseline=cfg.input_path(baseline_model_path,'.osim');report=json.loads(bounded_read(cfg.input_path(assembly_report_path,'.json'),2*1024**2))
    combined=cfg.input_path(report['model_file'],'.osim')
    if digest(bounded_read(baseline,MAX_MODEL))!=report['source_model_sha256'] or digest(bounded_read(combined,MAX_MODEL))!=report['model_sha256']:raise InputError('Baseline/combined model differs from verified assembly; review and rebuild.')
    if not report['physical'] or any(link['joint_type']!='WeldJoint' for link in report['links']):raise InputError('Matched biological-demand comparison currently requires welded device links; articulated/coupled devices need a study-specific force projection.')
    _,original=xml_model(bounded_read(baseline,MAX_MODEL));coordinates={n.get('name') for n in original.iter('Coordinate')}
    if (assistance_path is None)!=(assistance_mapping is None):raise InputError('Assistance requires both a measured/prescribed table and explicit coordinate/column/unit mapping.')
    assist=None
    if assistance_path:
        source=Path(assistance_path)
        if source.suffix.lower() not in {'.mot','.sto'}:raise InputError('Assistance must be STO/MOT.')
        cfg.input_path(assistance_path,source.suffix.lower());assist=read_motion(source)
        if not isinstance(assistance_mapping,list) or not 1<=len(assistance_mapping)<=100:raise InputError('Provide 1..100 explicit assist mappings.')
        seen=set()
        for item in assistance_mapping:
            if not isinstance(item,dict) or set(item)!={'coordinate','column','unit'} or item['coordinate'] not in coordinates or item['coordinate'] in seen or item['column'] not in assist['columns'] or item['column']=='time' or item['unit'] not in {'N','Nm'}:raise InputError('Invalid/duplicate assistance mapping.')
            seen.add(item['coordinate'])
    runs=[run_analysis(cfg,'id',str(path),coordinates_path,loads_path,external_forces,no_external_loads,lowpass_cutoff_hz=lowpass_cutoff_hz) for path in (baseline,combined)]
    tables=[read_motion(next(Path(f) for f in run['files'] if f.endswith('inverse_dynamics.sto'))) for run in runs]
    a,b=tables
    if a['columns']!=b['columns'] or len(a['rows'])!=len(b['rows']) or any(abs(x[0]-y[0])>1e-7 for x,y in zip(a['rows'],b['rows'])):raise InputError('Matched ID outputs must share all coordinate columns and sample times.')
    if assist and (len(assist['rows'])!=len(b['rows']) or any(abs(x[0]-y[0])>1e-7 for x,y in zip(assist['rows'],b['rows']))):raise InputError('Assistance must coincide with every returned ID sample; explicitly resample/crop upstream if needed.')
    mapping={x['coordinate']+('_moment' if x['unit']=='Nm' else '_force'):x for x in (assistance_mapping or [])}
    if set(mapping)-set(b['columns']):raise InputError('Assistance N/Nm unit does not match a returned coordinate force/moment.')
    def metrics(values):return dict(rms=math.sqrt(sum(v*v for v in values)/len(values)),peak_abs=max(abs(v) for v in values))
    result={};output=[];labels=['time']
    for column in a['columns'][1:]:labels += [column+'_baseline',column+'_combined',column+'_assist',column+'_remaining']
    for i,(ra,rb) in enumerate(zip(a['rows'],b['rows'])):
        row=[ra[0]]
        for j,column in enumerate(a['columns'][1:],1):
            item=mapping.get(column);force=assist['rows'][i][assist['columns'].index(item['column'])] if item else 0.
            row += [ra[j],rb[j],force,rb[j]-force]
        output.append(row)
    for j,column in enumerate(a['columns'][1:]):
        k=1+4*j;baseline_values=[r[k] for r in output];combined_values=[r[k+1] for r in output];forces=[r[k+2] for r in output];remaining=[r[k+3] for r in output]
        result[column]=dict(unit='Nm' if column.endswith('_moment') else 'N',baseline=metrics(baseline_values),combined=metrics(combined_values),added_device_demand=metrics([b-a for a,b in zip(baseline_values,combined_values)]),assistance=metrics(forces),remaining_generalized_demand=metrics(remaining))
    folder=cfg.results_root/('wearable-id-'+uuid.uuid4().hex);folder.mkdir(parents=True);file=folder/'comparison.sto'
    file.write_text('Matched wearable ID and explicit ideal generalized assistance\nversion=1\nnRows='+str(len(output))+'\nnColumns='+str(len(labels))+'\ninDegrees=no\nendheader\n'+'\t'.join(labels)+'\n'+'\n'.join('\t'.join(format(v,'.17g') for v in row) for row in output)+'\n',encoding='utf-8')
    report=dict(status='completed',baseline_run=runs[0],combined_run=runs[1],metrics=result,assistance_mapping=assistance_mapping or [],comparison_file=str(file),
        scope='Same measured kinematics/loads/filter, welded added masses only. Remaining demand = combined ID minus explicitly mapped ideal generalized assistance. Not muscle-force redistribution, interface/strap forces, pressure or a clinical benefit claim.')
    destination=folder/'comparison.json';report['report_file']=str(destination);destination.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8');return report
