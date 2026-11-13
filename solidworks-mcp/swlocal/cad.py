"""SOLIDWORKS COM adapter. Instantiated only on the worker's STA main thread.

There are no imports from a community CAD repository. See THIRD_PARTY_NOTICES
for the adapted, MIT-licensed sketch constraint recipe and design references.
"""
import hashlib
import json
import math
import os
import subprocess
import threading
import uuid
from pathlib import Path

import pythoncom
import win32com.client
from .geometry import coaxial_error, direction_from_bounds, finite_positive, polygon_area
from .com import Binding
from .errors import load_error


class Failure(RuntimeError):
    def __init__(self,code,message,**details):
        self.payload={'code':code,'message':message,**details}
        super().__init__(message)


def member(obj,name,*args):
    value=getattr(obj,name)
    if not args and hasattr(value,'_oleobj_'):
        return value
    return value(*args) if args or callable(value) else value


def optional(obj,name,*args,default=None):
    try: return member(obj,name,*args)
    except (pythoncom.com_error,AttributeError,TypeError): return default


def null_dispatch():
    return None


def out_call(obj,name,args,count):
    result=getattr(obj,name)(*args,*([0]*count))
    if not isinstance(result,tuple) or len(result)!=count+1:
        raise Failure('OUTPUT_BINDING',f'{name} did not return its documented output parameters')
    return result


def double_array(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,tuple(float(v) for v in values))


def rounded(seq,scale=1.0):
    values=[round(float(v)*scale,8) for v in seq]
    return [0.0 if v==0 else v for v in values]


def digest(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]


from .mechanisms import MechanismTools
from .assembly_build import AssemblyBuildTools
from .organization import OrganizationTools
from .pose_update import PoseUpdateTools
from .reference_views import ReferenceViewTools
from .assembly_audit import AssemblyAuditTools
from .completion import CompletionTools
from .revision import RevisionTools
from .recipes import RecipeTools


class CAD(MechanismTools,AssemblyBuildTools,OrganizationTools,PoseUpdateTools,ReferenceViewTools,AssemblyAuditTools,CompletionTools,RevisionTools,RecipeTools):
    def __init__(self):
        self.owner=threading.get_ident()
        self.generation=uuid.uuid4().hex[:12]
        self.sw=None
        self.documents={}
        self._part_fingerprints={}
        self.sketch_baseline=set()
        self.output=Path(os.environ.get('SWLOCAL_OUTPUT',str(Path(__file__).resolve().parents[1]/'outputs'))).resolve()
        self.scratch=Path(os.environ['TEMP']).resolve()
        import win32com
        import win32com.gen_py
        generated=self.scratch/'gen_py'
        generated.mkdir(parents=True,exist_ok=True)
        win32com.__gen_path__=str(generated)
        win32com.gen_py.__path__=[str(generated)]
        self.output.mkdir(parents=True,exist_ok=True)
        self.expected_year=int(os.environ.get('SWLOCAL_YEAR','2025'))

    def _thread(self):
        if threading.get_ident()!=self.owner: raise Failure('COM_THREAD','COM object accessed from the wrong thread')

    def health(self):
        import importlib.metadata
        from . import __version__
        library = self._configured_type_library()
        library_exists = library.is_file()
        return {'bridge':'solidworks-mcp','version':__version__,'mcp_sdk':importlib.metadata.version('mcp'),'expected_year':self.expected_year,'com_thread':self.owner,'generation':self.generation,'connected':self.sw is not None,'output_root':str(self.output),'scratch_root':str(self.scratch),
                'type_library':str(library),'type_library_exists':library_exists,
                'next_tool': ('sw_documents' if self.sw is not None else 'sw_connect') if library_exists else None,
                'diagnosis': 'TYPELIB_MISSING' if not library_exists else 'ATTACHED' if self.sw is not None else 'ATTACH_PENDING'}

    @staticmethod
    def _configured_type_library():
        return Path(os.environ.get('SWLOCAL_TYPELIB', r'D:\SW2025\SOLIDWORKS\sldworks.tlb'))

    def _load_type_library(self):
        from comtypes import COMError, typeinfo
        path = self._configured_type_library()
        if not path.is_file():
            raise Failure('TYPELIB_MISSING', 'The configured SOLIDWORKS type library does not exist.', type_library=str(path), edit_may_be_partial=False)
        try:
            library = typeinfo.LoadTypeLibEx(str(path), typeinfo.REGKIND_NONE)
        except (OSError, COMError, pythoncom.com_error) as error:
            raise Failure('TYPELIB_LOAD_FAILED', 'Could not read the configured SOLIDWORKS type library.', type_library=str(path), native_error=str(error), edit_may_be_partial=False) from error
        major = library.GetLibAttr().wMajorVerNum
        if major != self.expected_year - 1992:
            raise Failure('TYPELIB_VERSION_MISMATCH', f'Expected the SOLIDWORKS {self.expected_year} type library; got version {major + 1992}.', type_library=str(path), edit_may_be_partial=False)
        return path, library

    def connect(self,start_if_needed=False,visible=True):
        self._thread()
        tlb_path, tlb = self._load_type_library()
        try: sw=win32com.client.GetActiveObject('SldWorks.Application')
        except pythoncom.com_error as error:
            # tasklist follows the Windows console code page, independent of
            # this bridge's UTF-8 environment. Only match its ASCII executable.
            try:
                running=subprocess.run(['tasklist','/FI','IMAGENAME eq SLDWORKS.exe','/FO','CSV','/NH'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
            except (OSError, subprocess.TimeoutExpired) as probe_error:
                raise Failure('RUNNING_NOT_READY','Windows process inventory unavailable; SOLIDWORKS was not launched') from probe_error
            if running.returncode:
                raise Failure('RUNNING_NOT_READY','Windows process inventory unavailable; no SOLIDWORKS instance was launched')
            if b'sldworks.exe' in (running.stdout or b'').lower():
                from .process_probe import read_process_inventory
                try:
                    probe=read_process_inventory()
                    # Recheck before launch. Only old, tiny zero-thread records
                    # are excluded; uncertain observations remain blocking.
                    if start_if_needed and not probe['active_or_unknown']:
                        probe=read_process_inventory()
                except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
                    raise Failure('RUNNING_NOT_READY','SOLIDWORKS process state could not be verified; no second instance was launched') from error
                if probe['active_or_unknown']:
                    raise Failure('RUNNING_NOT_READY','An existing SOLIDWORKS instance is not available through COM; no second instance was launched',processes=probe['active_or_unknown'])
            if not start_if_needed:
                raise Failure('NOT_RUNNING','Start SOLIDWORKS or call sw_connect(start_if_needed=True)') from error
            sw=win32com.client.Dispatch(f'SldWorks.Application.{self.expected_year-1992}')
        revision=str(member(sw,'RevisionNumber'))
        year=int(revision.split('.')[0])+1992
        if year!=self.expected_year: raise Failure('VERSION_MISMATCH',f'Expected {self.expected_year}, connected to {year}',revision=revision)
        # Some installations expose working IDispatch calls but broken
        # IDispatch.GetTypeInfo. Generate from the installed official TLB,
        # rather than asking the application to discover its own type info.
        from win32com.client import makepy,gencache
        makepy.GenerateFromTypeLibSpec(str(tlb_path),bForDemand=True)
        self.binding=Binding(tlb)
        self.sw=self.binding.cast(sw,'ISldWorks')
        sw.Visible=visible
        from .native_batch import NativeBatch,restore_pending
        restore_pending(self.sw,self.scratch)
        with NativeBatch(self.sw,self.scratch):documents=self.list_documents()
        return {'year':year,'revision':revision,'documents':documents}

    def _app(self):
        if self.sw is None: self.connect()
        member(self.sw,'RevisionNumber')
        return self.sw

    def _register(self,model,editable=False,owned=False):
        title=str(member(model,'GetTitle'))
        path=str(member(model,'GetPathName') or '')
        for key,record in self.documents.items():
            try:
                if member(record['model'],'GetTitle')==title and str(member(record['model'],'GetPathName') or '')==path:
                    record['editable']=record['editable'] or editable
                    return key
            except (pythoncom.com_error,AttributeError): pass
        key=self.generation+'-'+uuid.uuid4().hex[:10]
        self.documents[key]={'model':model,'editable':editable,'owned':owned}
        return key

    def _doc(self,document_id):
        self._thread()
        if document_id not in self.documents: raise Failure('DOCUMENT_HANDLE','Unknown or expired document handle; call sw_documents again')
        record=self.documents[document_id]
        try: member(record['model'],'GetTitle')
        except pythoncom.com_error as e: raise Failure('DOCUMENT_CLOSED','The referenced document is no longer open') from e
        return record

    def _activate(self,model):
        title=str(member(model,'GetTitle'))
        path=str(member(model,'GetPathName') or '')
        activated,errors=out_call(self._app(),'ActivateDoc3',(path or title,False,0),1)
        if activated is None or str(member(activated,'GetTitle'))!=title or str(member(activated,'GetPathName') or '')!=str(member(model,'GetPathName') or ''):
            raise Failure('ACTIVATION_FAILED','Could not activate the explicitly referenced document',errors=errors,expected_title=title,expected_path=str(member(model,'GetPathName') or ''),actual_title=str(member(activated,'GetTitle')) if activated is not None else None,actual_path=str(member(activated,'GetPathName')) if activated is not None else None,edit_may_be_partial=False)

    def list_documents(self):
        sw=self._app()
        result=[]
        for model in member(sw,'GetDocuments') or []:
            key=self._register(model)
            rec=self.documents[key]
            result.append({'document_id':key,'title':str(member(model,'GetTitle')),'path':str(member(model,'GetPathName') or ''),'kind':int(member(model,'GetType')),'editable':rec['editable'],'native_read_only':bool(member(model,'IsOpenedReadOnly')),'owned_by_bridge':rec['owned'],'visible':bool(member(model,'Visible')),'modified':bool(member(model,'GetSaveFlag'))})
        return result

    def _features(self,model,with_dimensions=False):
        result=[]
        seen=set()
        assembly=int(member(model,'GetType'))==2
        def walk(feature,level=0):
            steps=0
            while feature is not None and len(result)<2000 and steps<2000:
                steps+=1
                name=str(member(feature,'Name'))
                kind=str(member(feature,'GetTypeName2'))
                key=(name,kind)
                if key not in seen:
                    seen.add(key)
                    item={'name':name,'type':kind,'level':level}
                    if with_dimensions:
                        dims=[]
                        display=optional(feature,'GetFirstDisplayDimension')
                        while display is not None and len(dims)<128:
                            dim=member(display,'GetDimension2',0)
                            dims.append({'name':str(optional(dim,'FullName',default='') or optional(dim,'Name',default='')),'value_si':float(member(dim,'SystemValue')),'dimension_type':optional(dim,'GetType')})
                            display=optional(feature,'GetNextDisplayDimension',display)
                        item['dimensions']=dims
                    result.append(item)
                    if level<8 and not (assembly and kind=='Reference'): walk(optional(feature,'GetFirstSubFeature'),level+1)
                feature=optional(feature,'GetNextSubFeature' if level else 'GetNextFeature')
        walk(member(model,'FirstFeature'))
        return result

    def _edge(self,edge,index):
        curve=member(edge,'GetCurve')
        params=list(member(edge,'GetCurveParams2'))
        start,end=float(params[6]),float(params[7])
        length=abs(float(member(curve,'GetLength3',start,end)))*1000
        circle=bool(member(curve,'IsCircle'))
        line=bool(member(curve,'IsLine'))
        result={'edge_id':index,'length_mm':round(length,7),'kind':'circle' if circle else 'line' if line else 'curve','midpoint_mm':None,'convexity':'undetermined'}
        if line:
            a=list(member(member(edge,'GetStartVertex'),'GetPoint'))
            b=list(member(member(edge,'GetEndVertex'),'GetPoint'))
            result['midpoint_mm']=rounded([(a[i]+b[i])/2 for i in range(3)],1000)
            v=[b[i]-a[i] for i in range(3)]
            norm=math.sqrt(sum(float(x)**2 for x in v))
            result['direction']=rounded([float(x)/norm for x in v])
        if circle:
            cp=list(member(curve,'CircleParams'))
            result.update(center_mm=rounded(cp[:3],1000),axis=rounded(cp[3:6]),diameter_mm=round(abs(float(cp[6]))*2000,7),closed=abs(abs(end-start)-2*math.pi)<1e-6)
        return result

    def _part_geometry(self,model,include_objects=False):
        bodies=list(member(model,'GetBodies2',0,False) or [])
        edges=[];faces=[];edge_objects=[];face_objects=[];boxes=[]
        for bi,body in enumerate(bodies):
            boxes.append(list(member(body,'GetBodyBox')))
            for edge in member(body,'GetEdges') or []:
                item=self._edge(edge,len(edges));item['body_id']=bi
                edges.append(item);edge_objects.append(edge)
            for face in member(body,'GetFaces') or []:
                surface=member(face,'GetSurface')
                f={'face_id':len(faces),'body_id':bi,'area_mm2':round(float(member(face,'GetArea'))*1e6,6),'bounds_mm':rounded(member(face,'GetBox'),1000)}
                if member(surface,'IsCylinder'):
                    cp=list(member(surface,'CylinderParams'))
                    f.update(kind='cylinder',axis_point_mm=rounded(cp[:3],1000),axis=rounded(cp[3:6]),diameter_mm=round(float(cp[6])*2000,7))
                elif member(surface,'IsPlane'):
                    f.update(kind='plane',normal=rounded(member(face,'Normal')))
                elif member(surface,'IsSphere'):
                    sp=list(member(surface,'SphereParams'))
                    f.update(kind='sphere',center_mm=rounded(sp[:3],1000),radius_mm=round(float(sp[3])*1000,7))
                else: f['kind']='surface'
                faces.append(f);face_objects.append(face)
        bounds=[min(b[i] for b in boxes) for i in range(3)]+[max(b[i+3] for b in boxes) for i in range(3)] if boxes else None
        volume=0.0
        if bodies:
            mass=member(member(model,'Extension'),'CreateMassProperty')
            volume=float(member(mass,'Volume'))*1e9
            if not math.isfinite(volume) or volume<=0: raise Failure('MEASUREMENT_FAILED','Could not verify positive solid volume')
        data={'body_count':len(bodies),'volume_mm3':round(volume,6),'bounds_mm':rounded(bounds,1000) if bounds else None,'size_mm':rounded([bounds[i+3]-bounds[i] for i in range(3)],1000) if bounds else None,'edges':edges,'faces':faces}
        if include_objects: return data,edge_objects,face_objects,bounds
        return data

    def _components(self,model):
        result=[]
        components=list(member(model,'GetComponents',True) or [])
        if len(components)>128: raise Failure('MODEL_LIMIT','Version 0.1 limits assemblies to 128 top-level components')
        for component in components:
            transform=member(component,'Transform2')
            child=member(component,'GetModelDoc2')
            referenced_configuration=str(member(component,'ReferencedConfiguration'))
            loaded_configuration=str(member(member(member(child,'ConfigurationManager'),'ActiveConfiguration'),'Name')) if child is not None else None
            fingerprint=None
            if child is not None and int(member(child,'GetType'))==1:
                fingerprint=self._part_fingerprint(child,referenced_configuration,loaded_configuration)
            result.append({'name':str(member(component,'Name2')),'path':str(member(component,'GetPathName')),'fixed':bool(member(component,'IsFixed')),'transform':rounded(member(transform,'ArrayData')),'referenced_configuration':referenced_configuration,'loaded_part_configuration':loaded_configuration,'native_part_update_stamp':int(member(child,'GetUpdateStamp')) if child is not None else None,'geometry_hash':fingerprint})
        self._component_map_cache=(model._oleobj_.QueryInterface(pythoncom.IID_IUnknown),int(member(model,'GetUpdateStamp')),{r['name']:c for r,c in zip(result,components)})
        return result

    def _part_fingerprint(self,model,referenced_configuration,loaded_configuration):
        # Cache only a digest, never selectable face/edge objects or IDs. Native
        # stamps track geometry changes; names/configuration/material are read
        # separately because not every metadata change increments the stamp.
        key=(str(member(model,'GetPathName')),str(member(model,'GetTitle')),loaded_configuration,int(member(model,'GetUpdateStamp')))
        identity=model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
        cache=getattr(self,'_part_fingerprints',{})
        if key not in cache or cache[key][0]!=identity:
            cache[key]=(identity,digest(self._assembly_part_summary(model)))
            if len(cache)>256:cache={key:cache[key]}
            self._part_fingerprints=cache
        material=self._material_identity(model,referenced_configuration)
        if int(member(model,'GetUpdateStamp'))!=key[3]:raise Failure('INSPECTION_CHANGED_STATE','Part changed during native inspection; inspect again',edit_may_be_partial=False)
        return digest({'geometry':cache[key][1],'material':material,'configuration':referenced_configuration})

    def _assembly_part_summary(self,model):
        # Assembly state does not need tens of thousands of selectable edge
        # descriptors. Stamp + identity + configuration guard this measurement;
        # face/edge selection still calls the uncached full _part_geometry.
        bodies=list(member(model,'GetBodies2',0,False) or [])
        prop=member(model.Extension,'CreateMassProperty');prop.UseSystemUnits=True
        volume=float(member(prop,'Volume'))
        if not bodies or not math.isfinite(volume) or volume<=0:raise Failure('MEASUREMENT_FAILED','Assembly part must contain positive native solid geometry',edit_may_be_partial=False)
        return {'bodies':[{'bounds_m':rounded(member(body,'GetBodyBox')),
          'face_count':int(member(body,'GetFaceCount')),'edge_count':int(member(body,'GetEdgeCount'))} for body in bodies],
          'volume_m3':volume}

    def snapshot(self,document_id):
        rec=self._doc(document_id);model=rec['model']
        kind=int(member(model,'GetType'))
        if kind==2:
            components=self._components(model);mates,objects=self._mate_rows(model,True)
            geometry={'components':components,'mates':mates}
        else:geometry=self._part_geometry(model) if kind==1 else {}
        if kind==1:geometry['material']=self._material_identity(model)
        features=self._features(model)
        configuration=str(member(member(member(model,'ConfigurationManager'),'ActiveConfiguration'),'Name'))
        state=self.generation+'-'+digest({'document_id':document_id,'configuration':configuration,'geometry':geometry,'features':features})
        if kind==2:
            cache=getattr(self,'_mate_object_snapshots',{});cache[document_id]=(state,objects);self._mate_object_snapshots=cache
        return {'document_id':document_id,'title':str(member(model,'GetTitle')),'path':str(member(model,'GetPathName') or ''),'configuration':configuration,'kind':kind,'editable':rec['editable'],'state':state,**geometry}

    def _edit(self,document_id,state,kind=None):
        rec=self._doc(document_id)
        if not rec['editable']: raise Failure('READ_ONLY','Document was attached read-only; explicitly open it editable before editing',edit_may_be_partial=False)
        current=self.snapshot(document_id)
        if current['state']!=state: raise Failure('STALE_STATE','Geometry or feature state changed; inspect it again before selecting or editing',current_state=current['state'],edit_may_be_partial=False)
        if kind is not None and current['kind']!=kind: raise Failure('DOCUMENT_TYPE','Operation does not support this document type',edit_may_be_partial=False)
        if kind is not None:self._check_resources()
        self._activate(rec['model'])
        rec['model'].ClearSelection2(True)
        return rec['model'],current

    def _check_resources(self):
        from .resources import memory_margins,enough_memory
        values=memory_margins()
        if not enough_memory(values):raise Failure('RESOURCE_MARGIN','Low memory margin; this edit was not started. Save/checkpoint and close only explicitly owned work before continuing. SOLIDWORKS was left running.',resources=values,edit_may_be_partial=False,retry_automatically=False)

    def _finish(self,document_id):
        model=self._doc(document_id)['model']
        model.ClearSelection2(True)
        if not model.ForceRebuild3(int(member(model,'GetType'))==2): raise Failure('REBUILD_FAILED','Native rebuild reported a failure',edit_may_be_partial=True)
        return self.snapshot(document_id)

    def _template(self,kind):
        pref,suffix={'part':(8,'.prtdot'),'assembly':(9,'.asmdot')}[kind]
        candidate=Path(str(self._app().GetUserPreferenceStringValue(pref) or ''))
        if candidate.is_file() and candidate.suffix.lower()==suffix: return str(candidate)
        base=Path(os.environ.get('PROGRAMDATA',r'C:\ProgramData'))/'SOLIDWORKS'/f'SOLIDWORKS {self.expected_year}'/'templates'
        matches=list(base.glob('*'+suffix)) if base.exists() else []
        if matches: return str(matches[0])
        raise Failure('TEMPLATE_MISSING',f'Configure a default {kind} template in SOLIDWORKS; no interactive template dialog was opened')

    def new_document(self,kind='part'):
        if kind not in ('part','assembly'): raise Failure('DOCUMENT_TYPE','Version 0.1 supports part and assembly documents')
        self._check_resources()
        model=self._app().NewDocument(self._template(kind),0,0.0,0.0)
        if model is None: raise Failure('NEW_DOCUMENT_FAILED','NewDocument returned no object; no fallback to another active document')
        key=self._register(model,editable=True,owned=True)
        return self.snapshot(key)

    def open_document(self,path,editable=False,state=None):
        p=Path(path).expanduser().resolve(strict=True)
        kind={'.sldprt':1,'.sldasm':2}.get(p.suffix.lower())
        if kind is None: raise Failure('FILE_TYPE','Only native SLDPRT/SLDASM inputs are supported in version 0.1')
        model=self._app().GetOpenDocumentByName(str(p))
        if model is None:
            self._part_fingerprints={}
            model,errors,warnings=out_call(self.sw,'OpenDoc6',(str(p),kind,1|(0 if editable else 2),''),2)
            if model is None or errors: raise Failure(**load_error(errors,warnings))
        if editable and bool(member(model,'IsOpenedReadOnly')):
            key=self._register(model)
            before=self.snapshot(key)
            if not state or before['state']!=state:raise Failure('STALE_STATE','Restoring write access to an already-open read-only document requires its fresh sw_geometry state. No close/reopen, save or discard was attempted.',current_state=before['state'],document_id=key,edit_may_be_partial=False)
            modified=bool(member(model,'GetSaveFlag'))
            succeeded=bool(member(model,'SetReadOnlyState',False))
            still_read_only=bool(member(model,'IsOpenedReadOnly'))
            after=self.snapshot(key)
            if before['state']!=after['state'] or bool(member(model,'GetSaveFlag'))!=modified:raise Failure('ACCESS_CHANGED_STATE','Changing native write access changed model state or its unsaved flag; inspect before further action. Nothing was saved, closed or discarded.',current_state=after['state'],native_read_only=still_read_only,edit_may_be_partial=True)
            if not succeeded or still_read_only:raise Failure('FILE_READ_ONLY','Native write access was refused. The file may be read-only on disk or locked by another writer. No access rights, locks or file attributes were changed; no retry, close/reopen, save or discard was attempted.',native_read_only=still_read_only,edit_may_be_partial=not still_read_only)
        key=self._register(model,editable=editable)
        return self.snapshot(key)

    def _front_plane(self,model):
        feature=member(model,'FirstFeature')
        while feature is not None:
            if member(feature,'GetTypeName2')=='RefPlane': return feature
            feature=member(feature,'GetNextFeature')
        raise Failure('PLANE_MISSING','No native reference plane found')

    def import_step(self,path):
        """Import one explicit local STEP as a new document; never retry writes."""
        p=Path(path).expanduser().resolve(strict=True)
        if p.suffix.lower() not in {'.step','.stp'} or not p.is_relative_to(self.output):
            raise Failure('IMPORT_SCOPE','STEP must be staged inside the configured project output root',edit_may_be_partial=False)
        if not 100<=p.stat().st_size<=64*1024**2:raise Failure('IMPORT_SIZE','STEP must be 100 bytes to 64 MiB',edit_may_be_partial=False)
        if self._app().GetOpenDocumentByName(str(p)) is not None:raise Failure('IMPORT_ALREADY_OPEN','Inspect the already open imported document instead of repeating import',edit_may_be_partial=False)
        self._check_resources();source_hash=hashlib.sha256(p.read_bytes()).hexdigest()
        data=member(self.sw,'GetImportFileData',str(p))
        if data is None:raise Failure('IMPORT_API','Native STEP import settings unavailable',edit_may_be_partial=False)
        data=self.binding.cast(data,'IImportStepData');data.MapConfigurationData=False
        model,errors=out_call(self.sw,'LoadFile4',(str(p),'r',data),1)
        if model is None:raise Failure('IMPORT_FAILED','Native STEP import returned no document; inspect dialogs/documents before retry',native_errors=errors,edit_may_be_partial=True)
        model=self.binding.cast(model,'IModelDoc2');key=self._register(model,editable=True,owned=True)
        if errors:raise Failure('IMPORT_PARTIAL','STEP document opened with native error flags; inspect before editing',document_id=key,native_errors=errors,edit_may_be_partial=True)
        result=self.snapshot(key)
        if result['kind']!=1 or not result.get('body_count') or result.get('volume_mm3',0)<=0:
            raise Failure('IMPORT_SCOPE','STEP must produce a solid native part; assembly/surface imports require explicit inspection',document_id=key,edit_may_be_partial=True)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=source_hash:raise Failure('IMPORT_CHANGED_SOURCE','STEP input changed during import',document_id=key,edit_may_be_partial=True)
        return {**result,'import_source_path':str(p),'import_source_sha256':source_hash,'native_errors':errors,'scope':'Static native STEP geometry; source units retained, no feature-recognition, material or purchased-mass claim.'}

    def _start_sketch(self,model):
        if member(member(model,'SketchManager'),'ActiveSketch') is not None: raise Failure('SKETCH_ACTIVE','Exit the existing sketch before starting another operation')
        model.ClearSelection2(True)
        self.sketch_baseline={f['name'] for f in self._features(model) if f['type']=='ProfileFeature'}
        if not self._front_plane(model).Select2(False,0): raise Failure('SELECTION_FAILED','Could not select the actual front-plane feature')
        model.SketchManager.InsertSketch(True)
        sketch=member(model.SketchManager,'ActiveSketch')
        if sketch is None: raise Failure('SKETCH_FAILED','Sketch edit mode was not entered')
        return sketch

    def _fully_define(self,model,sketch):
        # Adapted recipe from SolidWorks Automation Skill (MIT), cited in notices.
        origin=None;feature=member(model,'FirstFeature')
        while feature is not None:
            if member(feature,'GetTypeName2')=='OriginProfileFeature': origin=str(member(feature,'Name'));break
            feature=member(feature,'GetNextFeature')
        selected=False
        for point in ('Point1','点1'):
            if origin and model.Extension.SelectByID2(point+'@'+origin,'EXTSKETCHPOINT',0,0,0,False,6,null_dispatch(),0): selected=True;break
        if not selected: raise Failure('ORIGIN_SELECTION','Could not select the native sketch origin for dimensions')
        model.SketchManager.FullyDefineSketch(True,True,1023,True,1,null_dispatch(),1,null_dispatch(),1,1)
        status=int(member(sketch,'GetConstrainedStatus'))
        if status!=3: raise Failure('SKETCH_UNDERDEFINED','Sketch did not become fully defined',constrained_status=status)
        model.ClearSelection2(True)

    def _sketch_feature(self,sketch,model):
        # ISketch has no GetFeature in the installed 2025 type library.
        # Resolve its exact interface through IFeature.GetSpecificFeature2.
        feature=member(model,'FirstFeature')
        created=[]
        while feature is not None:
            if str(member(feature,'GetTypeName2'))=='ProfileFeature':
                candidate=member(feature,'GetSpecificFeature2')
                if candidate is not None and candidate._oleobj_==sketch._oleobj_: return feature
                if str(member(feature,'Name')) not in self.sketch_baseline: created.append(feature)
            feature=member(feature,'GetNextFeature')
        if len(created)==1: return created[0]
        raise Failure('SKETCH_REFERENCE','Cannot obtain the exact newly created sketch feature')

    def _extrude(self,model,sketch_feature,depth,cut=False,reverse=False,both=False):
        model.ClearSelection2(True)
        if not sketch_feature.Select2(False,0): raise Failure('SELECTION_FAILED','Could not select the exact newly created sketch feature')
        if cut:
            feature=model.FeatureManager.FeatureCut4(not both,False,reverse,1,1 if both else 0,0.01,0.01 if both else 0,False,False,False,False,0.,0.,False,False,False,False,False,True,True,False,False,False,0,0.,False,False)
        else:
            feature=model.FeatureManager.FeatureExtrusion3(True,False,False,0,0,depth,0.,False,False,False,False,0.,0.,False,False,False,False,True,False,True,0,0.,False)
        if feature is None: raise Failure('FEATURE_FAILED','Native feature creation returned no feature; no automatic replay was attempted',edit_may_be_partial=True)
        return str(member(feature,'Name'))

    def _primitive(self,document_id,state,shape,values):
        # Validate before entering sketch edit mode.
        depth=finite_positive(values['depth_mm'],'depth')/1000
        if shape=='box':
            w=finite_positive(values['width_mm'],'width')/1000;h=finite_positive(values['height_mm'],'height')/1000
        elif shape=='cylinder':
            r=finite_positive(values['diameter_mm'],'diameter')/2000
        else:
            pts,area=polygon_area(values['vertices_mm'])
        model,before=self._edit(document_id,state,1)
        if before['body_count']: raise Failure('NONEMPTY_PART','Primitive creation requires an empty part; use separate parts for assembly components',edit_may_be_partial=False)
        sketch=self._start_sketch(model)
        try:
            if shape=='box':
                model.SketchManager.CreateCenterRectangle(0.,0.,0.,w/2,h/2,0.)
                expected=w*h*depth*1e9
            elif shape=='cylinder':
                model.SketchManager.CreateCircleByRadius(0.,0.,0.,r)
                expected=math.pi*r*r*depth*1e9
            else:
                for a,b in zip(pts,pts[1:]+pts[:1]): model.SketchManager.CreateLine(a[0]/1000,a[1]/1000,0.,b[0]/1000,b[1]/1000,0.)
                expected=area*depth*1000
            self._fully_define(model,sketch)
            sketch_feature=self._sketch_feature(sketch,model)
        finally:
            if optional(model.SketchManager,'ActiveSketch') is not None: model.SketchManager.InsertSketch(True)
        feature_name=self._extrude(model,sketch_feature,depth)
        after=self._finish(document_id)
        if abs(after['volume_mm3']-expected)>max(.01,expected*1e-6): raise Failure('VOLUME_MISMATCH','Created solid does not match requested profile and depth',expected_mm3=expected,actual_mm3=after['volume_mm3'],edit_may_be_partial=True)
        return {**after,'feature_name':feature_name,'verified_volume_mm3':expected,'sketch_fully_defined':True}

    def box(self,document_id,state,width_mm,height_mm,depth_mm):
        return self._primitive(document_id,state,'box',locals())

    def cylinder(self,document_id,state,diameter_mm,depth_mm):
        return self._primitive(document_id,state,'cylinder',locals())

    def polygon(self,document_id,state,vertices_mm,depth_mm):
        polygon_area(vertices_mm)
        return self._primitive(document_id,state,'polygon',locals())

    def through_hole(self,document_id,state,diameter_mm,x_mm=0.0,y_mm=0.0):
        diameter=finite_positive(diameter_mm,'diameter')/1000
        if not all(math.isfinite(v) and abs(v)<=5000 for v in (x_mm,y_mm)): raise Failure('COORDINATE','Hole coordinates must be finite and within 5000 mm')
        model,before=self._edit(document_id,state,1)
        if before['body_count']!=1: raise Failure('BODY_SCOPE','A through-hole requires exactly one solid body')
        _geo,_edges,_faces,bounds=self._part_geometry(model,True)
        sketch=self._start_sketch(model)
        try:
            transform=member(member(sketch,'ModelToSketchTransform'),'Inverse')
            utility=member(self.sw,'GetMathUtility')
            origin=list(member(member(utility.CreatePoint(double_array([0.,0.,0.])),'MultiplyTransform',transform),'ArrayData'))
            normal=list(member(member(utility.CreateVector(double_array([0.,0.,1.])),'MultiplyTransform',transform),'ArrayData'))
            if math.sqrt(sum(v*v for v in normal))<1e-7: raise Failure('SKETCH_NORMAL','Native sketch transform returned an invalid normal',origin=origin,normal=normal,bounds=bounds)
            reverse,both=direction_from_bounds(bounds,origin,normal)
            model.SketchManager.CreateCircleByRadius(x_mm/1000,y_mm/1000,0.,diameter/2)
            self._fully_define(model,sketch)
            sf=self._sketch_feature(sketch,model)
        finally:
            if optional(model.SketchManager,'ActiveSketch') is not None: model.SketchManager.InsertSketch(True)
        name=self._extrude(model,sf,0,cut=True,reverse=reverse,both=both)
        after=self._finish(document_id)
        if after['body_count']!=1 or not .000001<after['volume_mm3']<before['volume_mm3']-.000001: raise Failure('CUT_NOT_VERIFIED','Through-hole did not remove material from one solid body',edit_may_be_partial=True)
        candidates=[f for f in after['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-diameter_mm)<.001]
        if not candidates: raise Failure('HOLE_GEOMETRY','No cylindrical wall of the requested diameter was found',edit_may_be_partial=True)
        return {**after,'feature_name':name,'diameter_mm':diameter_mm,'cut_reverse':reverse,'cut_both_directions':both,'removed_volume_mm3':before['volume_mm3']-after['volume_mm3']}

    def fillet(self,document_id,state,edge_ids,radius_mm):
        radius=finite_positive(radius_mm,'radius')/1000
        model,before=self._edit(document_id,state,1)
        geo,objects,_faces,_bounds=self._part_geometry(model,True)
        if not edge_ids or len(edge_ids)>128 or len(set(edge_ids))!=len(edge_ids) or any(type(i)!=int or i<0 or i>=len(objects) for i in edge_ids): raise Failure('EDGE_SELECTION','Choose distinct edge IDs from the current sw_geometry result')
        try:
            for i,index in enumerate(edge_ids):
                if not objects[index].Select4(i>0,null_dispatch()): raise Failure('SELECTION_FAILED',f'Could not select edge {index}')
            feature=model.FeatureManager.FeatureFillet(195,radius,0,0)
        finally: model.ClearSelection2(True)
        if feature is None: raise Failure('FILLET_FAILED','Native fillet returned no feature; reduce the radius or inspect the selected edges',edit_may_be_partial=True)
        after=self._finish(document_id)
        if abs(after['volume_mm3']-before['volume_mm3'])<1e-6: raise Failure('FILLET_NOT_VERIFIED','Solid volume did not change after fillet',edit_may_be_partial=True)
        return {**after,'feature_name':str(member(feature,'Name')),'selected_edge_ids':edge_ids,'radius_mm':radius_mm}

    def features(self,document_id):
        model=self._doc(document_id)['model']
        return {'document_id':document_id,'state':self.snapshot(document_id)['state'],'features':self._features(model,True)}

    def set_dimension(self,document_id,state,dimension_name,value_si):
        if not math.isfinite(value_si) or value_si<=0 or value_si>100: raise Failure('DIMENSION_VALUE','System value must be finite and positive; lengths use metres and angles radians')
        model,before=self._edit(document_id,state,1)
        allowed={d['name'] for f in self._features(model,True) for d in f.get('dimensions',[])}
        if dimension_name not in allowed: raise Failure('DIMENSION_NAME','Use an exact dimension name returned by sw_features')
        dim=model.Parameter(dimension_name)
        if dim is None: raise Failure('DIMENSION_MISSING','Named dimension could not be resolved')
        old=float(member(dim,'SystemValue'))
        dim.SystemValue=value_si
        after=self._finish(document_id)
        actual=float(member(dim,'SystemValue'))
        if abs(actual-value_si)>max(1e-9,abs(value_si)*1e-6): raise Failure('DIMENSION_READBACK','Dimension did not match requested value',edit_may_be_partial=True)
        return {**after,'dimension_name':dimension_name,'previous_value_si':old,'actual_value_si':actual}

    def _output_path(self,path,suffixes,overwrite=False,current_path=None):
        p=Path(path).expanduser().resolve()
        if not any(p.is_relative_to(root) for root in (self.output,self.scratch)):
            raise Failure('OUTPUT_SCOPE','Output must be inside the configured model output folder or this worker temporary folder',edit_may_be_partial=False)
        if p.suffix.lower() not in suffixes: raise Failure('OUTPUT_TYPE','Output extension does not match this operation')
        same=current_path and p==Path(current_path).resolve()
        if p.exists() and not overwrite and not same: raise Failure('FILE_EXISTS','Refusing to overwrite an existing file; choose a new path or explicitly set overwrite=True',edit_may_be_partial=False)
        p.parent.mkdir(parents=True,exist_ok=True)
        return p,bool(same)

    def save(self,document_id,state,path,overwrite=False,close_when_finished=False):
        if type(close_when_finished)!=bool:raise Failure('ARGUMENT','close_when_finished must be a boolean',edit_may_be_partial=False)
        model,before=self._edit(document_id,state)
        p,same=self._output_path(path,{1:{'.sldprt'},2:{'.sldasm'}}[before['kind']],overwrite,before['path'])
        if not same: self._check_name_collision(p)
        success,errors,warnings=out_call(model,'Save3',(1,),2) if same else out_call(model.Extension,'SaveAs',(str(p),0,1,null_dispatch()),2)
        if not success or errors or not p.is_file() or p.stat().st_size<100: raise Failure('SAVE_FAILED','Native save or output file validation failed',errors=errors,warnings=warnings)
        result={**self.snapshot(document_id),'saved_path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'native_warnings':warnings}
        if before['kind']==2 and len(result['components'])>20:
            folders=self._folder_rows(model);result['module_folder_count']=len(folders)
            if not folders:result['delivery_organization_note']='Large assembly tree is still ungrouped. Before final delivery use descriptive module folders, collapse them, and verify references and STL. Do not merge or suppress functional parts merely to shorten the tree.'
        return self._finish_saved_part_window(document_id,result) if close_when_finished else result

    def export(self,document_id,state,path,overwrite=False):
        model,before=self._edit(document_id,state)
        p,_same=self._output_path(path,{'.step','.stp','.stl'},overwrite)
        stl=p.suffix.lower()=='.stl'
        if stl:
            from .export_options import StlOptions
            self._check_resources()
            with StlOptions(self.sw,self.scratch):ok,errors,warnings=out_call(model.Extension,'SaveAs',(str(p),0,1,null_dispatch()),2)
        else:ok,errors,warnings=out_call(model.Extension,'SaveAs',(str(p),0,1,null_dispatch()),2)
        if not ok or errors or not p.is_file() or p.stat().st_size<100: raise Failure('EXPORT_FAILED','Native export failed',errors=errors,warnings=warnings)
        return {'document_id':document_id,'state':self.snapshot(document_id)['state'],'exported_path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'native_warnings':warnings,**({'stl_options':{'units':'mm','binary':True,'assembly_components_in_one_file':True,'retain_native_origin':True,'previous_preferences_restored':True,'scope':'Current pose. Overlapping components are not fused or made printable; run explicit native interference checks.'}} if stl else {})}

    def close(self,document_id,discard_changes=False):
        rec=self._doc(document_id);model=rec['model']
        if bool(member(model,'GetSaveFlag')) and not discard_changes: raise Failure('UNSAVED_DOCUMENT','Save this document or explicitly allow discarding its changes',edit_may_be_partial=False)
        title=str(member(model,'GetTitle'))
        path=str(member(model,'GetPathName') or '')
        self._app().CloseDoc(path or title)
        for opened in member(self.sw,'GetDocuments') or []:
            opened_path=str(member(opened,'GetPathName') or '')
            if (path and opened_path.casefold()==path.casefold()) or (not path and not opened_path and str(member(opened,'GetTitle'))==title):
                raise Failure('CLOSE_NOT_CONFIRMED','The explicitly referenced document remains loaded; inspect its assembly references before retrying',edit_may_be_partial=True)
        del self.documents[document_id]
        self._part_fingerprints={}
        getattr(self,'_mate_object_snapshots',{}).pop(document_id,None)
        self._component_map_cache=None
        return {'closed_document_id':document_id,'closed_title':title}

    def add_component(self,document_id,state,path,x_mm=0.,y_mm=0.,z_mm=0.,fixed=False):
        model,before=self._edit(document_id,state,2)
        p=Path(path).resolve(strict=True)
        if p.suffix.lower()!='.sldprt': raise Failure('COMPONENT_TYPE','Version 0.1 inserts native part files only')
        if not all(math.isfinite(v) and abs(v)<=5000 for v in (x_mm,y_mm,z_mm)): raise Failure('COORDINATE','Component coordinates must be finite and within 5000 mm')
        child=self.sw.GetOpenDocumentByName(str(p))
        if child is None:
            self._check_name_collision(p)
            child,e,w=out_call(self.sw,'OpenDoc6',(str(p),1,1|2,''),2)
            if child is None or e: raise Failure(**load_error(e,w))
        if Path(str(member(child,'GetPathName'))).resolve()!=p:
            raise Failure('COMPONENT_PATH','SOLIDWORKS resolved a different part file; insertion was not attempted',edit_may_be_partial=False)
        self._activate(model)
        comp=model.AddComponent5(str(p),0,'',False,'',0.,0.,0.)
        if comp is None: raise Failure('ADD_COMPONENT_FAILED','Native AddComponent5 returned no component',edit_may_be_partial=True)
        if Path(str(member(comp,'GetPathName'))).resolve()!=p:
            raise Failure('COMPONENT_PATH','Inserted component references a different part file',edit_may_be_partial=True)
        if not comp.Select4(False,null_dispatch(),False): raise Failure('COMPONENT_SELECTION','Could not select the inserted component')
        model.UnfixComponent()
        model.ClearSelection2(True)
        matrix=[1.,0.,0.,0.,1.,0.,0.,0.,1.,x_mm/1000,y_mm/1000,z_mm/1000,1.,0.,0.,0.]
        comp.Transform2=self.sw.GetMathUtility().CreateTransform(double_array(matrix))
        if fixed:
            comp.Select4(False,null_dispatch(),False);model.FixComponent();model.ClearSelection2(True)
        actual=list(member(member(comp,'Transform2'),'ArrayData'))
        if any(abs(actual[9+i]-matrix[9+i])>1e-7 for i in range(3)) or bool(member(comp,'IsFixed'))!=fixed: raise Failure('COMPONENT_READBACK','Inserted component placement/fixed state differs',edit_may_be_partial=True)
        return {**self._finish(document_id),'inserted_component':str(member(comp,'Name2'))}

    def _check_name_collision(self,path):
        for opened in member(self.sw,'GetDocuments') or []:
            existing=str(member(opened,'GetPathName') or '')
            if existing and Path(existing).name.casefold()==path.name.casefold() and Path(existing).resolve()!=path:
                raise Failure('DOCUMENT_NAME_COLLISION','A different loaded document has the same filename. Choose a unique filename or explicitly close that document; the bridge will not close it automatically.',requested_path=str(path),conflicting_path=existing,edit_may_be_partial=False)

    def _component(self,model,name):
        cached=getattr(self,'_component_map_cache',None);matches=[]
        if cached and cached[0]==model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) and cached[1]==int(member(model,'GetUpdateStamp')):
            candidate=cached[2].get(name)
            if candidate is not None and str(member(candidate,'Name2'))==name:matches=[candidate]
        if not matches:matches=[c for c in member(model,'GetComponents',True) or [] if str(member(c,'Name2'))==name]
        if len(matches)!=1: raise Failure('COMPONENT_NAME','Choose an exact top-level name returned in the assembly snapshot')
        child=member(matches[0],'GetModelDoc2')
        if child is not None:
            referenced=str(member(matches[0],'ReferencedConfiguration'))
            loaded=str(member(member(member(child,'ConfigurationManager'),'ActiveConfiguration'),'Name'))
            if referenced!=loaded:raise Failure('CONFIGURATION_SCOPE','The component references a different configuration from the loaded part. This version refuses face selection or editing in that ambiguous context.',component=name,referenced_configuration=referenced,loaded_configuration=loaded,edit_may_be_partial=False)
        return matches[0]

    def component_geometry(self,document_id,component_name):
        rec=self._doc(document_id);model=rec['model']
        if int(member(model,'GetType'))!=2: raise Failure('DOCUMENT_TYPE','Expected assembly')
        comp=self._component(model,component_name)
        child=member(comp,'GetModelDoc2')
        if child is None: raise Failure('UNRESOLVED_COMPONENT','Resolve the component in SOLIDWORKS before inspecting it')
        child_kind=int(member(child,'GetType'))
        if child_kind==1:
            geometry=self._part_geometry(child)
        elif child_kind==2:
            # Subassemblies have native datum planes but no IPartDoc.GetBodies2.
            # Do not misreport the absence of part-level faces as zero mass.
            geometry={'body_count':None,'volume_mm3':None,'bounds_mm':None,'size_mm':None,'edges':[],'faces':[],
                      'geometry_scope':'Subassembly datum planes only; constituent solids are not flattened here.'}
        else:
            raise Failure('DOCUMENT_TYPE','Component must reference a part or assembly')
        return {'document_id':document_id,'state':self.snapshot(document_id)['state'],'component_name':component_name,'coordinate_frame':'component local coordinates','component_document_type':child_kind,**geometry,'reference_planes':self._reference_planes(child)}

    def mate_cylinders(self,document_id,state,component_a,face_a,component_b,face_b):
        model,before=self._edit(document_id,state,2)
        if component_a==component_b: raise Failure('MATE_SELECTION','Choose two different components')
        axes=[]
        for index,(name,fid) in enumerate(((component_a,face_a),(component_b,face_b))):
            comp=self._component(model,name)
            child=member(comp,'GetModelDoc2')
            geo,_edges,faces,_bounds=self._part_geometry(child,True)
            if type(fid)!=int or fid<0 or fid>=len(faces) or geo['faces'][fid]['kind']!='cylinder': raise Failure('MATE_FACE','Face ID must identify a cylindrical face from sw_component_geometry')
            axes.append((comp,geo['faces'][fid]))
            entity=comp.GetCorrespondingEntity(faces[fid])
            data=model.SelectionManager.CreateSelectData();data.Mark=1
            if entity is None or not entity.Select4(index>0,data): raise Failure('ASSEMBLY_CONTEXT','Could not map/select the cylindrical face in assembly context')
        try: mate,error=out_call(model,'AddMate5',(1,0,False,0.,0.,0.,0.,0.,0.,0.,0.,False,False,0),1)
        finally: model.ClearSelection2(True)
        if mate is None or error!=1: raise Failure('MATE_FAILED','Native concentric mate failed',native_error=error,edit_may_be_partial=True)
        after=self._finish(document_id)
        utility=self.sw.GetMathUtility()
        global_axes=[]
        for comp,face in axes:
            transform=member(comp,'Transform2')
            point=utility.CreatePoint(double_array([v/1000 for v in face['axis_point_mm']]))
            vector=utility.CreateVector(double_array(face['axis']))
            position=rounded(member(member(point,'MultiplyTransform',transform),'ArrayData'),1000)
            direction=member(member(vector,'MultiplyTransform',transform),'ArrayData')
            global_axes.append((position,direction))
        verification=coaxial_error(*global_axes[0],*global_axes[1])
        if verification['axis_angle_deg']>1e-4 or verification['axis_offset_mm']>1e-4:
            raise Failure('MATE_GEOMETRY','Native mate returned success but cylinder axes are not aligned',**verification,edit_may_be_partial=True)
        return {**after,'mate_type':'concentric','native_error':error,'verification':verification}

    def api_lookup(self,interface,member_name=''):
        path, lib = self._load_type_library()
        for i in range(lib.GetTypeInfoCount()):
            if lib.GetDocumentation(i)[0]!=interface: continue
            ti=lib.GetTypeInfo(i);attr=ti.GetTypeAttr();records=[]
            for j in range(attr.cFuncs):
                fd=ti.GetFuncDesc(j);doc=ti.GetDocumentation(fd.memid)
                if member_name and doc[0]!=member_name: continue
                records.append({'name':doc[0],'parameter_names':list(ti.GetNames(fd.memid,fd.cParams+1))[1:],'parameter_count':fd.cParams,'documentation':doc[1] or ''})
            return {'interface':interface,'type_library':str(path),'members':records[:200],'total_matches':len(records),'truncated':len(records)>200}
        raise Failure('API_INTERFACE','Interface name not found in the installed 2025 type library')
