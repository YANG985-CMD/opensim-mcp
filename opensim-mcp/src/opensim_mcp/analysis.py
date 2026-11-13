from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from xml.etree import ElementTree as ET

from .core import (InputError, MAX_MODEL, MAX_RESULT, Settings, _JOB_LOCK, bounded_read,
                   environment, execute, read_motion, xml_model)
from .session import staged_model


def prop(parent,name,value):
    ET.SubElement(parent,name).text=str(value)


def validate_sample_times(actual,expected,tolerance):
    if len(actual)!=len(expected):raise InputError('Analysis output sample count differs from the requested window.')
    maximum=max(abs(a-b) for a,b in zip(actual,expected))
    if maximum>tolerance:raise InputError('Analysis output time alignment exceeds the serialization tolerance.')
    return maximum


def table_input(cfg,path):
    suffix=Path(path).suffix.lower()
    if suffix not in {".mot",".sto"}:
        raise InputError("Expected .mot/.sto coordinate or load data.")
    target=cfg.input_path(path,suffix)
    data=bounded_read(target,MAX_RESULT)
    return target,data,read_motion(target)


def validate_loads(model, table, forces):
    if not forces or len(forces)>100:
        raise InputError("Provide 1..100 external force definitions.")
    bodies={e.get("name") for e in model.iter("Body")}|{"ground"}
    keys={"name","applied_to_body","force_identifier","point_identifier","torque_identifier",
          "force_expressed_in_body","point_expressed_in_body"}
    names=set()
    normalized=[]
    for force in forces:
        if not isinstance(force,dict) or set(force)-keys:
            raise InputError("Unsupported external-force fields.")
        force=dict(force)
        force.setdefault("force_expressed_in_body","ground")
        force.setdefault("point_expressed_in_body","ground")
        if not {"name","applied_to_body","force_identifier","point_identifier"}<=force.keys():
            raise InputError("External force needs name, applied_to_body, force_identifier and point_identifier.")
        if any(not isinstance(v,str) or not v or len(v)>200 for v in force.values()):
            raise InputError("Force-definition values must be short, nonempty strings.")
        if force["name"] in names:
            raise InputError("Duplicate external-force name.")
        names.add(force["name"])
        for key in ("applied_to_body","force_expressed_in_body","point_expressed_in_body"):
            if force[key] not in bodies:
                raise InputError("External-force body/frame is not a serialized model body or ground.")
        for key in ("force_identifier","point_identifier","torque_identifier"):
            if key in force and not all(force[key]+axis in table["columns"] for axis in "xyz"):
                raise InputError(f"Load table lacks XYZ columns for {key}={force[key]}.")
        normalized.append(force)
    return normalized


def run_analysis(cfg:Settings,kind:str,model_path:str,coordinates_path:str,
                 loads_path:str|None=None,external_forces:list[dict]|None=None,
                 no_external_loads:bool=False,start_time:float|None=None,end_time:float|None=None,
                 lowpass_cutoff_hz:float|None=None,joint_names:list[str]|None=None,on_body:str='child',
                 in_frame:str='ground',forces_path:str|None=None,ignore_actuators:bool=False,optimizer_max_iterations:int=200) -> dict:
    if kind not in {"id","muscle_analysis","static_optimization","joint_reaction"}:
        raise InputError("Unknown analysis.")
    if not _JOB_LOCK.acquire(blocking=False):
        raise InputError("Another native analysis is running.")
    try:
        return _run(cfg,kind,model_path,coordinates_path,loads_path,external_forces,
                    no_external_loads,start_time,end_time,lowpass_cutoff_hz,joint_names,on_body,in_frame,forces_path,ignore_actuators,optimizer_max_iterations)
    finally:
        _JOB_LOCK.release()


def _run(cfg,kind,model_path,coordinates_path,loads_path,external_forces,no_external_loads,start_time,end_time,cutoff,
         joint_names,on_body,in_frame,forces_path,ignore_actuators,optimizer_max_iterations=200):
    if type(optimizer_max_iterations) is not int or not 1<=optimizer_max_iterations<=5000:raise InputError('optimizer_max_iterations must be 1..5000.')
    if type(no_external_loads) is not bool:
        raise InputError("no_external_loads must be a boolean.")
    model_file=cfg.input_path(model_path,".osim")
    original=bounded_read(model_file,MAX_MODEL)
    staged=staged_model(original)
    _,model=xml_model(staged)
    coordinate_file,coordinate_bytes,coordinates=table_input(cfg,coordinates_path)
    coordinate_names={e.get("name") for e in model.iter("Coordinate")}
    if not coordinate_names or not coordinate_names<=set(coordinates["columns"]):
        raise InputError("Coordinate data must explicitly include every model coordinate.")
    if coordinates["in_degrees"].lower() not in {"yes","no","true","false"}:
        raise InputError("Coordinate file must explicitly specify inDegrees=yes/no.")
    times=[row[0] for row in coordinates["rows"]]
    start=times[0] if start_time is None else start_time
    end=times[-1] if end_time is None else end_time
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (start,end)):
        raise InputError("Finite numeric start/end times required.")
    if not times[0]<=start<end<=times[-1] or start not in times or end not in times:
        raise InputError("Time window must match coordinate sample times within the trial.")
    expected=[t for t in times if start<=t<=end]
    if len(expected)<6:
        raise InputError("At least six coordinate samples are required for native spline differentiation.")
    # OpenSim's low-pass Storage resampling can accumulate sub-microsecond
    # float rounding on a 60 Hz trial. Keep all rows and original timestamps;
    # allow only a bounded fraction of one input sample, and report the delta.
    tolerance=min(min(b-a for a,b in zip(expected,expected[1:]))*.001,
                  max(1e-7,1e-6*max(1,abs(start),abs(end)))) if cutoff is not None else 1e-7
    if cutoff is not None and (isinstance(cutoff,bool) or not isinstance(cutoff,(int,float)) or not math.isfinite(cutoff) or cutoff<=0):
        raise InputError("lowpass_cutoff_hz must be positive and finite, or null for no filtering.")
    if cutoff is not None:
        dt=[b-a for a,b in zip(times,times[1:])]
        if max(dt)-min(dt)>1e-6*max(dt) or cutoff>=.5/max(dt):
            raise InputError("Filtering requires uniform sampling and cutoff below Nyquist.")
    muscles=[e.get("name") for e in model.findall("./ForceSet/objects/*") if "muscle" in e.tag.lower()]
    if kind in {"muscle_analysis","static_optimization"} and not muscles:
        raise InputError("Muscle analysis/optimization requires at least one serialized muscle.")
    force_bytes=None
    if kind=='joint_reaction':
        if on_body not in {'parent','child'} or in_frame not in {'ground','parent','child'}:raise InputError('Unsupported joint reaction body/frame.')
        if type(ignore_actuators) is not bool:raise InputError('ignore_actuators must be boolean.')
        joints={e.get('name') for e in model.iter() if e.tag.endswith('Joint') and e.tag!='Joint'}
        if joint_names is None:joint_names=sorted(joints)
        if not isinstance(joint_names,list) or not joint_names or len(joint_names)>300 or len(set(joint_names))!=len(joint_names) or set(joint_names)-joints:
            raise InputError('joint_names must select existing joints without duplicates.')
        if any(not isinstance(name,str) or any(c.isspace() for c in name) for name in joint_names):raise InputError('Joint names containing whitespace are unsupported.')
        actuators=[e for e in model.findall('./ForceSet/objects/*') if 'muscle' in e.tag.lower() or e.tag.endswith('Actuator')]
        if forces_path:
            if ignore_actuators:raise InputError('Cannot supply actuator forces and ignore_actuators together.')
            _,force_bytes,forces=table_input(cfg,forces_path)
            if forces['rows'][0][0]>start or forces['rows'][-1][0]<end:raise InputError('Actuator forces do not cover the analysis window.')
            if not {e.get('name') for e in actuators}<=set(forces['columns']):raise InputError('Force table must include every serialized muscle/actuator by name.')
        elif actuators and not ignore_actuators:
            raise InputError('JointReaction needs muscle/actuator forces_path (for example SO output), or explicit ignore_actuators=true.')
        if ignore_actuators:
            parent=model.find('./ForceSet/objects')
            for actuator in actuators:parent.remove(actuator)
            root,_=xml_model(staged);root.remove(root.find('Model'));root.append(model)
            staged=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    load_bytes=None; force_definitions=[]
    if kind=="muscle_analysis" and (loads_path or external_forces):
        raise InputError("This geometry-only muscle analysis does not consume external loads.")
    if loads_path:
        if no_external_loads:
            raise InputError("Cannot combine loads_path with no_external_loads=true.")
        load_file,load_bytes,loads=table_input(cfg,loads_path)
        if loads["rows"][0][0]>start or loads["rows"][-1][0]<end:
            raise InputError("External loads do not cover the requested time window.")
        force_definitions=validate_loads(model,loads,external_forces)
    elif external_forces:
        raise InputError("External-force definitions need a loads_path.")
    elif kind!="muscle_analysis" and not no_external_loads:
        raise InputError("Provide measured/modeled external loads, or explicitly set no_external_loads=true for a study with no external loads.")
    job=uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix=kind+"-",dir=cfg.temp_root) as directory:
        work=Path(directory)
        (work/"model.osim").write_bytes(staged)
        (work/"coordinates.mot").write_bytes(coordinate_bytes)
        if force_bytes is not None:(work/'actuator_forces.sto').write_bytes(force_bytes)
        if load_bytes is not None:
            (work/"loads.sto").write_bytes(load_bytes)
            root=ET.Element("OpenSimDocument",Version="40000")
            load_set=ET.SubElement(root,"ExternalLoads",name="external_loads")
            objects=ET.SubElement(load_set,"objects"); ET.SubElement(load_set,"groups")
            for force in force_definitions:
                obj=ET.SubElement(objects,"ExternalForce",name=force["name"])
                for name,value in force.items():
                    if name!="name":prop(obj,name,value)
            prop(load_set,"datafile","loads.sto")
            ET.ElementTree(root).write(work/"external_loads.xml",encoding="utf-8",xml_declaration=True)
        root=ET.Element("OpenSimDocument",Version="40000")
        tool=ET.SubElement(root,"InverseDynamicsTool" if kind=="id" else "AnalyzeTool",name="analysis")
        for key,value in {"model_file":"model.osim","results_directory":".","coordinates_file":"coordinates.mot",
                          "external_loads_file":"external_loads.xml" if load_bytes is not None else "",
                          "lowpass_cutoff_frequency_for_coordinates":cutoff if cutoff is not None else -1}.items():prop(tool,key,value)
        if kind=="id":
            prop(tool,"time_range",f"{start:.17g} {end:.17g}")
            prop(tool,"forces_to_exclude","muscles")
            prop(tool,"output_gen_force_file","inverse_dynamics.sto")
        else:
            prop(tool,"initial_time",start);prop(tool,"final_time",end)
            prop(tool,"solve_for_equilibrium_for_auxiliary_states","true")
            aset=ET.SubElement(tool,"AnalysisSet",name="analyses")
            objects=ET.SubElement(aset,"objects");ET.SubElement(aset,"groups")
            analysis_class={'muscle_analysis':'MuscleAnalysis','static_optimization':'StaticOptimization','joint_reaction':'JointReaction'}[kind]
            analysis=ET.SubElement(objects,analysis_class,name=analysis_class)
            for key,value in {"on":"true","start_time":start,"end_time":end,"step_interval":1}.items():prop(analysis,key,value)
            if kind=="muscle_analysis":
                prop(analysis,"muscle_list","all");prop(analysis,"moment_arm_coordinate_list","all");prop(analysis,"compute_moments","true")
            elif kind=='static_optimization':
                prop(analysis,"use_model_force_set","true");prop(analysis,"activation_exponent",2)
                prop(analysis,"use_muscle_physiology","true");prop(analysis,"optimizer_max_iterations",optimizer_max_iterations)
            else:
                prop(analysis,'joint_names',' '.join(joint_names));prop(analysis,'on_body',on_body);prop(analysis,'in_frame',in_frame)
                prop(analysis,'forces_file','actuator_forces.sto' if force_bytes is not None else '')
        ET.ElementTree(root).write(work/"setup.xml",encoding="utf-8",xml_declaration=True)
        native=execute(cfg,["run-tool","setup.xml"],work,cfg.timeout)
        native_log=bounded_read(work/"cli.log",8*1024*1024).decode("utf-8",errors="replace")
        if kind=="static_optimization" and re.search(r"optimization failed|optimizer failed|did not converge|could not find a solution|staticoptimization[^\n]*(failed|unsuccessful)",native_log,re.I):
            match=re.search(r"optimization failed|optimizer failed|did not converge|could not find a solution|staticoptimization[^\n]*(failed|unsuccessful)",native_log,re.I)
            raise InputError("Static Optimization reported failure even though the CLI exited zero: "+native_log[max(0,match.start()-250):match.start()+1400])
        outputs=[];tables={};reaction_quality={}
        for path in sorted(work.glob("*.sto")):
            if path.name in {"loads.sto","actuator_forces.sto"}:continue
            lower=path.name.lower()
            if kind=="muscle_analysis" and not any(x in lower for x in ("length","momentarm","moment_arm","pennation","velocity","speed")):
                continue
            table=read_motion(path)
            if kind=='joint_reaction':
                if 'reactionloads' not in lower:continue
                for joint in joint_names:
                    bases=[c[:-3] for c in table['columns'] if c.startswith(joint+'_') and c.endswith('_fx')]
                    if len(bases)!=1 or not all(bases[0]+'_'+axis in table['columns'] for axis in ('fx','fy','fz','mx','my','mz')):
                        raise InputError('Incomplete joint reaction force/moment columns: '+joint)
                    base=bases[0]
                    metrics={}
                    for prefix,unit in (('f','N'),('m','Nm')):
                        indexes=[table['columns'].index(base+'_'+prefix+axis) for axis in 'xyz']
                        metrics['peak_resultant_'+prefix+'_'+unit]=max(math.sqrt(sum(row[i]**2 for i in indexes)) for row in table['rows'])
                    reaction_quality[joint]=metrics
            if kind=="id" and path.name=="inverse_dynamics.sto":
                if not all(name+"_force" in table["columns"] or name+"_moment" in table["columns"] for name in coordinate_names):
                    raise InputError("ID output is missing generalized force/moment columns.")
            actual=[row[0] for row in table["rows"]]
            time_delta=validate_sample_times(actual,expected,tolerance)
            if kind=="static_optimization" and "activation" in lower:
                for name in muscles:
                    if name not in table["columns"]:raise InputError("Missing muscle activation column.")
                    index=table["columns"].index(name)
                    if any(not -1e-6<=row[index]<=1.000001 for row in table["rows"]):
                        raise InputError("Muscle activation outside [0,1].")
            outputs.append(path);tables[path.name]={"rows":len(actual),"columns":table["columns"],"time_range":[actual[0],actual[-1]],
                                                    "max_time_alignment_error_s":time_delta,"time_tolerance_s":tolerance}
        if not outputs or (kind=="id" and not any(p.name=="inverse_dynamics.sto" for p in outputs)):
            raise InputError("Expected native output files were not produced.")
        if kind=="static_optimization" and not all(any(term in p.name.lower() for p in outputs) for term in ("activation","force")):
            raise InputError("Static Optimization must produce activation and force tables.")
        version=environment(cfg)["opensim_version"]
        destination=cfg.results_root/(kind+"-"+job)
        destination.mkdir(parents=True,exist_ok=False)
        try:
            for path in outputs:shutil.copyfile(path,destination/path.name)
            result={"status":"completed","analysis":kind,"job_id":job,"opensim_version":version,
                    "backend":native.get("backend","opensim_cli"),
                    "time_range":[start,end],"files":[str(destination/p.name) for p in outputs],"tables":tables,
                    "native_exit_code":native["exit_code"],"elapsed_seconds":native["elapsed_seconds"],
                    "validation":"finite tables, expected time coverage; activation bounds for SO",
                    "warnings":["Numerical completion is not physiological validation."]}
            if load_bytes is None and kind!="muscle_analysis":result["warnings"].append("Explicit no-external-loads assumption used.")
            if kind=="id":result["warnings"].append("Model muscles excluded from ID; other passive/contact forces remain included.")
            if kind=="muscle_analysis":result["warnings"].append("Only geometric/kinematic muscle outputs are published; muscle forces are not inferred.")
            if kind=='joint_reaction':
                result.update(joint_reaction_quality=reaction_quality,on_body=on_body,in_frame=in_frame,
                              actuator_force_source='force_table' if force_bytes is not None else ('explicitly_removed' if ignore_actuators else 'no_serialized_actuators'))
                result['warnings'].append('Joint resultant loads are not individual cartilage/contact forces; force estimates and dynamics consistency require study-specific validation.')
            provenance={**result,"input_hashes":{"model":hashlib.sha256(original).hexdigest(),"coordinates":hashlib.sha256(coordinate_bytes).hexdigest(),
                         "loads":hashlib.sha256(load_bytes).hexdigest() if load_bytes is not None else None},
                        "external_forces":force_definitions,"lowpass_cutoff_hz":cutoff,"no_external_loads":no_external_loads}
            if kind=='static_optimization':provenance['optimizer_max_iterations']=optimizer_max_iterations
            if kind=='joint_reaction':provenance.update(joint_names=joint_names,on_body=on_body,in_frame=in_frame,ignore_actuators=ignore_actuators,
                                                       actuator_forces_sha256=hashlib.sha256(force_bytes).hexdigest() if force_bytes is not None else None)
            (destination/"provenance.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
            return result
        except BaseException:
            shutil.rmtree(destination);raise
