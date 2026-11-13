"""Explicit interface casts for factories declared as generic IDispatch in SW IDL."""
from win32com.client import gencache
import pythoncom

FACETS={'GetBodies2':'IPartDoc','GetComponents':'IAssemblyDoc','AddComponent5':'IAssemblyDoc','FixComponent':'IAssemblyDoc','UnfixComponent':'IAssemblyDoc','AddMate5':'IAssemblyDoc','Select4':'IEntity'}
FACETS.update({'InterferenceDetectionManager':'IAssemblyDoc','GetDragOperator':'IAssemblyDoc','GetMaterialPropertyName2':'IPartDoc','SetMaterialPropertyName2':'IPartDoc'})
FACETS.update({'CreateMateData':'IAssemblyDoc','CreateMate':'IAssemblyDoc'})
FACETS['AddComponents3']='IAssemblyDoc'
FACETS['ReorderComponents']='IAssemblyDoc'

RETURNS={
 'NewDocument':'IModelDoc2','OpenDoc6':'IModelDoc2','ActivateDoc3':'IModelDoc2',
 'GetOpenDocumentByName':'IModelDoc2','GetDocuments':'IModelDoc2','GetModelDoc2':'IModelDoc2',
 'Extension':'IModelDocExtension','SketchManager':'ISketchManager','FeatureManager':'IFeatureManager',
 'SelectionManager':'ISelectionMgr','ActiveSketch':'ISketch',
 'FirstFeature':'IFeature','GetNextFeature':'IFeature','GetFirstSubFeature':'IFeature','GetNextSubFeature':'IFeature',
 'FeatureExtrusion3':'IFeature','FeatureCut4':'IFeature','FeatureFillet':'IFeature',
 'GetBodies2':'IBody2','GetEdges':'IEdge','GetFaces':'IFace2','GetCurve':'ICurve',
 'GetStartVertex':'IVertex','GetEndVertex':'IVertex','CreateMassProperty':'IMassProperty',
 'GetMathUtility':'IMathUtility','CreatePoint':'IMathPoint','CreateVector':'IMathVector',
 'CreateTransform':'IMathTransform','ModelToSketchTransform':'IMathTransform',
 'Inverse':'IMathTransform','Transform2':'IMathTransform',
 'GetFirstDisplayDimension':'IDisplayDimension','GetNextDisplayDimension':'IDisplayDimension',
 'GetDimension2':'IDimension','Parameter':'IDimension','GetComponents':'IComponent2',
 'AddComponent5':'IComponent2','CreateSelectData':'ISelectData','GetCorrespondingEntity':'IEntity',
 'AddMate5':'IMate2',
 'GetMates':'IMate2','MateEntity':'IMateEntity2','ReferenceComponent':'IComponent2',
 'InterferenceDetectionManager':'IInterferenceDetectionMgr','GetInterferences':'IInterference','Components':'IComponent2',
 'GetDragOperator':'IDragOperator',
 'CreateMate':'IFeature',
 'DisplayDimension':'IDisplayDimension','DisplayDimension2':'IDisplayDimension',
 'ConfigurationManager':'IConfigurationManager','ActiveConfiguration':'IConfiguration',
 'AddComponents3':'IComponent2','GetLastFeatureAdded':'IFeature',
 'InsertFeatureTreeFolder2':'IFeature','GetFeatures':'IFeature','GetFeatureTreeRootItem2':'ITreeControlItem',
 'GetFirstChild':'ITreeControlItem','GetNext':'ITreeControlItem','GetPackAndGo':'IPackAndGo',
 'ActiveView':'IModelView',
 'GetAdvancedSaveAsOptions':'IAdvancedSaveAsOptions',
}


class Binding:
    def __init__(self,type_library):
        self.ids={type_library.GetDocumentation(i)[0]:str(type_library.GetTypeInfo(i).GetTypeAttr().guid) for i in range(type_library.GetTypeInfoCount())}
    def cast(self,obj,interface):
        if obj is None: return None
        if isinstance(obj,(list,tuple)):
            return tuple(self.cast(x,interface) if hasattr(x,'_oleobj_') else x for x in obj)
        if not hasattr(obj,'_oleobj_'): return obj
        cls=gencache.GetClassForCLSID(self.ids[interface])
        if cls is None: raise RuntimeError('Missing generated interface '+interface)
        dispatch=obj._oleobj_.QueryInterface(pythoncom.MakeIID(self.ids[interface]),pythoncom.IID_IDispatch)
        return COM(cls(dispatch),self)


class COM:
    def __init__(self,raw,binding):
        object.__setattr__(self,'_raw',raw)
        object.__setattr__(self,'_binding',binding)
    @property
    def _oleobj_(self): return self._raw._oleobj_
    def __getattr__(self,name):
        try: value=getattr(self._raw,name)
        except AttributeError:
            if name in FACETS: return getattr(self._binding.cast(self,FACETS[name]),name)
            raise
        target=RETURNS.get(name)
        if callable(value) and not hasattr(value,'_oleobj_'):
            def invoke(*args):
                result=value(*(x._raw if isinstance(x,COM) else x for x in args))
                return self._binding.cast(result,target) if target else result
            return invoke
        return self._binding.cast(value,target) if target else value
    def __setattr__(self,name,value):
        setattr(self._raw,name,value._raw if isinstance(value,COM) else value)
