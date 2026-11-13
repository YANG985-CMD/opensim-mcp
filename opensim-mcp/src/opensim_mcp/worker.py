"""Standalone native API worker. Keep compatible with CPython 3.8.

No MCP import: this file is launched by a separately configured interpreter.
OpenSim's native stdout is kept away from the MCP transport.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import threading


def bootstrap():
    global _dll_handles
    _dll_handles = []
    root = os.environ.get("OPENSIM_MCP_INSTALL_DIR")
    sdk = os.environ.get("OPENSIM_MCP_API_SDK")
    # A PyPI wheel owns its native libraries. Do not inject a different GUI
    # installation's DLLs into that process. Only legacy SDK mode needs this.
    if sdk and not root:
        raise RuntimeError("SDK mode requires OPENSIM_MCP_INSTALL_DIR.")
    if root and sdk:
        binary = str(Path(root) / "bin")
        os.environ["PATH"] = binary + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            _dll_handles.append(os.add_dll_directory(binary))
    if sdk:
        sys.path.insert(0, sdk)
    spec = importlib.util.find_spec("opensim")
    if spec is None:
        raise RuntimeError("OpenSim Python bindings not found in the API interpreter/SDK.")
    if os.name == 'nt' and not sdk and spec.submodule_search_locations:
        # Pin dynamic solver lookup to this wheel, not another program's CasADi.
        binary = str(Path(next(iter(spec.submodule_search_locations))).resolve())
        if hasattr(os, 'add_dll_directory'):
            _dll_handles.append(os.add_dll_directory(binary))
        os.environ['PATH'] = binary + os.pathsep + os.environ.get('PATH', '')
        if (Path(binary) / 'casadi_nlpsol_ipopt.dll').is_file():
            os.environ['CASADIPATH'] = binary
    module = importlib.util.module_from_spec(spec)
    # The 4.3 installer normally patches this global in __init__.py. Supply it
    # to the module without modifying any OpenSim installation file.
    if root and sdk:
        module.DLL_PATH = str(Path(root) / "bin")
    sys.modules["opensim"] = module
    spec.loader.exec_module(module)
    return module


def atomic_json(path, data):
    temporary = Path(str(path) + ".writing")
    temporary.write_text(json.dumps(data, ensure_ascii=True, allow_nan=False), encoding="utf-8")
    os.replace(str(temporary), str(path))


def serializable(value, depth=0):
    if depth > 6:
        return "[depth limit]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return value[:12000]
    if isinstance(value, dict):
        return {str(k)[:200]: serializable(v, depth+1) for k, v in list(value.items())[:200]}
    if isinstance(value, (list, tuple)):
        return [serializable(v, depth+1) for v in value[:200]]
    if hasattr(value, "tolist"):
        return serializable(value.tolist(), depth+1)
    return str(value)[:2000]


class Capture(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.count = 0

    def write(self, text):
        if self.count < 24000:
            self.parts.append(text[:24000-self.count])
        self.count += len(text)
        return len(text)

    def value(self):
        return "".join(self.parts) + ("\n[output truncated]" if self.count > 24000 else "")


class Runtime:
    def __init__(self, osim):
        self.osim = osim
        self.model = None
        self.state = None
        self.revision = 0
        self.source = None
        self.undo_stack = []
        self.redo_stack = []
        self.namespace = {"osim": osim, "opensim": osim, "__name__": "__opensim_session__"}
        try:
            import numpy as np
            self.namespace["np"] = np
        except ImportError:
            pass

    def assign(self, model, state):
        self.model, self.state = model, state
        self.namespace.update(model=model, state=state)
        self.revision += 1

    def overview(self):
        result = {"opensim_version": self.osim.GetVersionAndDate(), "python": sys.version.split()[0],
                  "worker_pid": os.getpid(),
                  "revision": self.revision, "model_loaded": self.model is not None,
                  "source_path": self.source, "gui_synchronized": False,
                  "undo_depth":len(self.undo_stack),"redo_depth":len(self.redo_stack)}
        if self.model:
            m = self.model
            result.update(name=m.getName(),total_mass_kg=m.getTotalMass(self.state),time=self.state.getTime(), counts={"bodies": m.getBodySet().getSize(),
                          "joints": m.getJointSet().getSize(), "coordinates": m.getCoordinateSet().getSize(),
                          "markers": m.getMarkerSet().getSize(), "muscles": m.getMuscles().getSize()},
                          coordinate_names=[m.getCoordinateSet().get(i).getName() for i in range(min(200,m.getCoordinateSet().getSize()))],
                          coordinate_values={m.getCoordinateSet().get(i).getName(): m.getCoordinateSet().get(i).getValue(self.state)
                                             for i in range(m.getCoordinateSet().getSize())} if self.state else {})
        return result

    def component(self, kind, name, model=None):
        model = model or self.model
        if model is None:
            raise ValueError("Load a model first.")
        sets = {"body": model.getBodySet, "coordinate": model.getCoordinateSet,
                "marker": model.getMarkerSet, "muscle": model.getMuscles}
        if kind not in sets:
            raise ValueError("component_type must be body, coordinate, marker or muscle.")
        return sets[kind]().get(name)

    def properties(self, kind, obj):
        if kind == "body":
            return {"mass": obj.get_mass(), "mass_center": [obj.get_mass_center().get(i) for i in range(3)]}
        if kind == "coordinate":
            return {"default_value": obj.getDefaultValue(), "range_min": obj.getRangeMin(),
                    "range_max": obj.getRangeMax(), "locked": obj.getDefaultLocked(),
                    "clamped": obj.getDefaultClamped()}
        if kind == "marker":
            return {"location": [obj.get_location().get(i) for i in range(3)]}
        return {"max_isometric_force": obj.getMaxIsometricForce(),
                "optimal_fiber_length": obj.getOptimalFiberLength(), "tendon_slack_length": obj.getTendonSlackLength()}

    def snapshot(self):
        if self.model is None:raise ValueError('Load a model first.')
        return {'model':self.osim.Model(self.model),'pose':self.overview()['coordinate_values'],
                'time':self.state.getTime(),'source':self.source,'state_variables':self.native_states()}

    def native_states(self):
        names=self.model.getStateVariableNames()
        return {names.get(i):float(self.model.getStateVariableValue(self.state,names.get(i))) for i in range(names.getSize())}

    def restore_states(self,model,state,values):
        names=model.getStateVariableNames();available=set(names.get(i) for i in range(names.getSize()))
        for name,value in values.items():
            if name in available:model.setStateVariableValue(state,name,value)

    def undo(self,redo=False,expected_revision=None):
        if expected_revision is not None and expected_revision!=self.revision:
            raise ValueError('Model revision changed; refresh before undo/redo.')
        source=self.redo_stack if redo else self.undo_stack
        target=self.undo_stack if redo else self.redo_stack
        if not source:raise ValueError('No structured edit to '+('redo' if redo else 'undo')+'.')
        item=source[-1];candidate=self.osim.Model(item['model'])
        candidate.finalizeConnections();state=candidate.initSystem()
        self.restore_states(candidate,state,item.get('state_variables',{}))
        for name,value in item['pose'].items():candidate.getCoordinateSet().get(name).setValue(state,value,False)
        state.setTime(item['time']);candidate.assemble(state);candidate.realizePosition(state)
        target.append(self.snapshot());del target[:-10];source.pop()
        self.assign(candidate,state);self.source=item['source']
        return dict(self.overview(),operation='redo' if redo else 'undo')

    def change(self, args):
        if self.model is None:
            raise ValueError("Load a model first.")
        kind, name, prop, value = (args[k] for k in ("component_type", "component_name", "property_name", "value"))
        previous_pose = {}
        if self.state is not None:
            for i in range(self.model.getCoordinateSet().getSize()):
                coordinate = self.model.getCoordinateSet().get(i)
                previous_pose[coordinate.getName()] = coordinate.getValue(self.state)
        candidate = self.osim.Model(self.model)
        obj = self.component(kind, name, candidate)
        before = self.properties(kind, obj)
        if prop not in before:
            raise ValueError("Unsupported property for this component; use scripting for advanced edits.")
        if prop in {"mass_center", "location"}:
            if not isinstance(value, list) or len(value) != 3 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in value):
                raise ValueError("Expected three finite numeric values in meters.")
            getattr(obj, "set_"+prop)(self.osim.Vec3(*value))
        elif prop in {"locked", "clamped"}:
            if not isinstance(value, bool):
                raise ValueError("Expected a boolean.")
            getattr(obj, "setDefault"+prop.capitalize())(value)
        else:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError("Expected a finite number.")
            if prop in {"mass", "max_isometric_force", "optimal_fiber_length", "tendon_slack_length"} and value <= 0:
                raise ValueError("Physical property must be positive.")
            methods = {"mass":"set_mass", "default_value":"setDefaultValue", "range_min":"setRangeMin", "range_max":"setRangeMax",
                       "max_isometric_force":"setMaxIsometricForce", "optimal_fiber_length":"setOptimalFiberLength", "tendon_slack_length":"setTendonSlackLength"}
            getattr(obj,methods[prop])(float(value))
        if kind == "coordinate" and obj.getRangeMin() >= obj.getRangeMax():
            raise ValueError("Coordinate range_min must be less than range_max.")
        candidate.finalizeConnections()
        state = candidate.initSystem()
        previous_states=self.native_states()
        if kind=='coordinate' and prop=='default_value':
            previous_states={k:v for k,v in previous_states.items() if not k.endswith('/'+name+'/value')}
        self.restore_states(candidate,state,previous_states)
        state.setTime(self.state.getTime())
        for coordinate_name, coordinate_value in previous_pose.items():
            if kind == "coordinate" and coordinate_name == name and prop == "default_value":
                continue
            candidate.getCoordinateSet().get(coordinate_name).setValue(state, coordinate_value, False)
        candidate.assemble(state)
        candidate.realizePosition(state)
        after = self.properties(kind,obj)
        self.undo_stack.append(self.snapshot());del self.undo_stack[:-10]
        self.redo_stack=[]
        self.assign(candidate,state)
        return {"revision":self.revision,"component_type":kind,"component_name":name,"before":before,"after":after,
                "native_initialized":True,"gui_synchronized":False}

    def dispatch(self, op, args):
        if op=='native_state':
            if self.model is None:raise ValueError('Load a model first.')
            values=self.native_states();paths=args.get('state_paths')
            if paths is not None:
                if not isinstance(paths,list) or not 1<=len(paths)<=200 or len(set(paths))!=len(paths) or set(paths)-set(values):raise ValueError('Select 1..200 unique existing state paths.')
                selected=paths
            else:selected=sorted(values)[args.get('offset',0):args.get('offset',0)+args.get('limit',200)]
            return dict(revision=self.revision,time=float(self.state.getTime()),states=[dict(path=n,value=values[n]) for n in selected],total_state_count=len(values),returned_state_count=len(selected),truncated=len(selected)<len(values))
        if op=='topology_commit':
            if type(args.get('expected_revision')) is not int or args['expected_revision']!=self.revision:raise ValueError('Model revision changed during topology preview.')
            candidate=self.osim.Model(args['model_file']);candidate.finalizeConnections();state=candidate.initSystem()
            data=json.loads(Path(args['state_file']).read_text(encoding='utf-8'));names=candidate.getStateVariableNames();available=set(names.get(i) for i in range(names.getSize()));values={}
            for name,value in data['state_variables'].items():
                for old,new in args.get('renames',[]):
                    if name==old or name.startswith(old+'/'):name=new+name[len(old):]
                values[name]=value
            self.restore_states(candidate,state,values);state.setTime(data['time']);candidate.assemble(state);candidate.realizePosition(state)
            retained=set(values)&available;new_names=available-set(values);removed=set(values)-available
            self.undo_stack.append(self.snapshot());del self.undo_stack[:-10];self.redo_stack=[];self.assign(candidate,state)
            return dict(self.overview(),native_initialized=True,retained_state_count=len(retained),new_state_count=len(new_names),removed_state_count=len(removed),new_state_paths=sorted(new_names),removed_state_paths=sorted(removed))
        if op=='recovery_save':
            if self.model is None:raise ValueError('No native model to snapshot.')
            names=self.model.getStateVariableNames();values={}
            for i in range(names.getSize()):
                name=names.get(i);value=float(self.model.getStateVariableValue(self.state,name))
                if not math.isfinite(value):raise ValueError('Cannot snapshot nonfinite native state.')
                values[name]=value
            if len(values)>5000:raise ValueError('Native state snapshot exceeds 5000 variables.')
            folder=Path(args['folder']);self.model.printToXML(str(folder/'model.osim'))
            atomic_json(folder/'state.json',dict(state_variables=values,state_count=len(values),time=float(self.state.getTime())))
            return dict(model_name=self.model.getName(),source_path=self.source,state_count=len(values),revision=self.revision,opensim_version=self.osim.GetVersionAndDate())
        if op=='recovery_restore':
            candidate=self.osim.Model(args['model_file']);candidate.finalizeConnections();state=candidate.initSystem()
            data=json.loads(Path(args['state_file']).read_text(encoding='utf-8'));names=candidate.getStateVariableNames()
            expected=set(names.get(i) for i in range(names.getSize()))
            if expected!=set(data['state_variables']):raise ValueError('Recovery model state identities differ.')
            for name,value in data['state_variables'].items():candidate.setStateVariableValue(state,name,float(value))
            state.setTime(float(data['time']));candidate.realizeVelocity(state)
            error=max([abs(candidate.getStateVariableValue(state,n)-v) for n,v in data['state_variables'].items()] or [0.])
            self.assign(candidate,state);self.source=args.get('source_path');self.undo_stack=[];self.redo_stack=[]
            return dict(self.overview(),restored_state_count=len(expected),max_native_state_restore_error=error)
        if op=='transaction':
            if self.model is None:raise ValueError('Load a model first.')
            if type(args.get('expected_revision')) is not int or args['expected_revision']!=self.revision:
                raise ValueError('Model revision changed; refresh before transaction.')
            edits=args.get('edits')
            if not isinstance(edits,list) or not 1<=len(edits)<=50:raise ValueError('Provide 1..50 edits.')
            # Validate all edits on an independent model/state. Failure never mutates the live model.
            candidate=Runtime(self.osim);snap=self.snapshot()
            candidate.assign(self.osim.Model(snap['model']),None);candidate.source=self.source
            candidate.state=candidate.model.initSystem();candidate.namespace['state']=candidate.state
            self.restore_states(candidate.model,candidate.state,snap.get('state_variables',{}))
            for name,value in snap['pose'].items():candidate.model.getCoordinateSet().get(name).setValue(candidate.state,value,False)
            candidate.state.setTime(snap['time']);candidate.model.assemble(candidate.state)
            changes=[]
            for edit in edits:changes.append(candidate.change(edit))
            candidate.state.setTime(snap['time'])
            result={'changes':changes,'native_initialized':True,'revision':self.revision,'dry_run':args.get('dry_run',True),
                    'candidate_mass_kg':candidate.model.getTotalMass(candidate.state),'gui_synchronized':False,
                    'scope':'Atomic parameter edits; no component topology or external script/file changes.'}
            if not args.get('dry_run',True):
                self.undo_stack.append(snap);del self.undo_stack[:-10];self.redo_stack=[]
                self.assign(candidate.model,candidate.state);result.update(revision=self.revision,committed=True)
            return result
        if op=='scene':
            if self.model is None:raise ValueError('Load a model first.')
            self.model.realizePosition(self.state)
            def xyz(frame):
                p=frame.getTransformInGround(self.state).p()
                return [p.get(i) for i in range(3)]
            joints=[]
            for i in range(self.model.getJointSet().getSize()):
                joint=self.model.getJointSet().get(i)
                joints.append({'name':joint.getName(),'parent':xyz(joint.getParentFrame().findBaseFrame()),
                               'child':xyz(joint.getChildFrame().findBaseFrame())})
            markers=[]
            for i in range(min(500,self.model.getMarkerSet().getSize())):
                marker=self.model.getMarkerSet().get(i);p=marker.getLocationInGround(self.state)
                markers.append({'name':marker.getName(),'position':[p.get(k) for k in range(3)]})
            return {'name':self.model.getName(),'revision':self.revision,'joints':joints,'markers':markers,
                    'scope':'Native body-frame origins and marker positions in meters; no surface meshes.'}
        if op=='documentation':
            from catalog import documentation
            return documentation(self.osim,**args)
        if op=='symbols':
            return {'symbols':dict((name,hasattr(self.osim,name)) for name in args['names'][:500])}
        if op=='components':
            from catalog import components
            return components(self.model,**args)
        if op=='component_details':
            from catalog import component_details
            return component_details(self.model,args['component_path'])
        if op in {'undo','redo'}:return self.undo(op=='redo',args.get('expected_revision'))
        if op == "status":
            return self.overview()
        if op == "load":
            model = self.osim.Model(args["staged_path"])
            model.finalizeConnections()
            state = model.initSystem()
            self.assign(model,state)
            self.source=args["source_path"]
            self.undo_stack=[];self.redo_stack=[]
            return self.overview()
        if op == "component":
            kind=args["component_type"]; obj=self.component(kind,args["component_name"])
            return {"component_type":kind,"name":obj.getName(),"class":obj.getConcreteClassName(),
                    "properties":self.properties(kind,obj),"revision":self.revision}
        if op == "change":
            return self.change(args)
        if op == "pose":
            if self.model is None:
                raise ValueError("Load a model first.")
            for name,value in args["coordinates"].items():
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError("Coordinate values must be finite numbers.")
                self.model.getCoordinateSet().get(name).setValue(self.state,float(value),False)
            self.model.assemble(self.state)
            self.model.realizePosition(self.state)
            if 'time' in args:self.state.setTime(float(args['time']))
            return self.overview()
        if op == "save":
            if self.model is None:
                raise ValueError("Load a model first.")
            self.model.printToXML(args["destination"])
            return {"model_file":args["destination"],"revision":self.revision,
                    "coordinate_values":self.overview()['coordinate_values'],"time":self.state.getTime(),
                    "opensim_version":self.osim.GetVersionAndDate(),
                    "sha256":hashlib.sha256(Path(args["destination"]).read_bytes()).hexdigest()}
        if op == "evaluate":
            capture,error=Capture(),Capture()
            self.namespace.pop("result",None)
            self.namespace["__file__"]=args.get("filename","<mcp>")
            failure=None;locations=[]
            try:
                with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(error):
                    exec(compile(args["code"],self.namespace["__file__"],"exec"),self.namespace,self.namespace)
            except BaseException:
                failure=traceback.format_exc()[-12000:]
                locations=[{'filename':frame.filename,'line':frame.lineno,'function':frame.name,
                            'source_line':args['code'].splitlines()[frame.lineno-1] if 0<frame.lineno<=len(args['code'].splitlines()) else frame.line} for frame in traceback.extract_tb(sys.exc_info()[2])
                           if frame.filename==self.namespace['__file__']][-20:]
            finally:
                # Arbitrary scripts can replace these objects, even on an exception.
                self.model=self.namespace.get("model")
                self.state=self.namespace.get("state")
                self.revision+=1
                self.undo_stack=[];self.redo_stack=[]
            return {"status":"failed" if failure else "completed", "error":failure,
                    "stdout":capture.value(),"stderr":error.value(),"result":serializable(self.namespace.get("result")),
                    "revision":self.revision,"diagnostics":locations,"gui_synchronized":False,"trust":"arbitrary_code_current_user_permissions"}
        raise ValueError("Unknown API operation.")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",required=True)
    parser.add_argument("--parent-pid",type=int,required=True)
    parser.add_argument('--revision-base',type=int,default=0)
    args=parser.parse_args()
    folder=Path(args.directory)
    def watch_parent():
        if os.name=="nt":
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.WinDLL("kernel32",use_last_error=True)
            kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
            kernel.OpenProcess.restype=wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            handle=kernel.OpenProcess(0x00100000,False,args.parent_pid)
            if not handle:os._exit(2)
            while True:
                if kernel.WaitForSingleObject(handle,0)==0:os._exit(0)
                time.sleep(.5)
    threading.Thread(target=watch_parent,daemon=True).start()
    try:
        runtime=Runtime(bootstrap())
        runtime.revision=args.revision_base
        atomic_json(folder/"ready.json",{"ok":True,"environment":runtime.overview()})
    except BaseException:
        atomic_json(folder/"ready.json",{"ok":False,"error":traceback.format_exc()[-12000:]})
        return
    while not (folder/"stop").exists():
        request=folder/"request.json"
        if not request.exists():
            time.sleep(.02); continue
        try:
            data=json.loads(request.read_text(encoding="utf-8"))
            request.unlink()
            try:
                value=runtime.dispatch(data["operation"],data.get("arguments",{}))
                response={"id":data["id"],"ok":True,"value":serializable(value)}
            except BaseException:
                response={"id":data["id"],"ok":False,"error":traceback.format_exc()[-12000:]}
            atomic_json(folder/"response.json",response)
        except BaseException:
            traceback.print_exc()
            time.sleep(.1)


if __name__=="__main__":
    main()
