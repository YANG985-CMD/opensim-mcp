import hashlib,os,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from swlocal import cad as n

class ImportHarness:
    import_step=n.CAD.import_step
    def __init__(self,root):
        self.output=root/'project';self.output.mkdir();self.calls=[];self.settings=types.SimpleNamespace(MapConfigurationData=True)
        self.app=types.SimpleNamespace(GetOpenDocumentByName=lambda p:None,GetImportFileData=lambda p:self.settings)
        self.sw=self.app;self.binding=types.SimpleNamespace(cast=lambda obj,interface:obj)
        self.model=object();self.native_errors=0
    def _app(self):self.calls.append('app');return self.app
    def _check_resources(self):self.calls.append('resources')
    def _register(self,model,**kwargs):self.registered=(model,kwargs);return 'imported'
    def snapshot(self,key):return dict(document_id=key,kind=1,body_count=1,volume_mm3=123.)
    def source(self,name='part.step',size=200):
        p=self.output/name;p.write_bytes(b'x'*size);return p
    def load(self,obj,method,args,count):
        self.calls.append((method,args));return self.model,self.native_errors

class StepImportTests(unittest.TestCase):
    def harness(self):
        context=tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']);self.addCleanup(context.cleanup)
        return ImportHarness(Path(context.name))
    def test_scope_and_size_rejected_before_native_access(self):
        h=self.harness();outside=h.output.parent/'outside.step';outside.write_bytes(b'x'*200)
        for p in [outside,h.source('tiny.step',99),h.source('bad.txt')]:
            with self.assertRaises(n.Failure):h.import_step(str(p))
        self.assertEqual(h.calls,[])
    def test_open_input_is_not_imported_twice(self):
        h=self.harness();p=h.source();h.app.GetOpenDocumentByName=lambda p:object()
        with patch.object(n,'out_call') as call:
            with self.assertRaises(n.Failure) as error:h.import_step(str(p))
            self.assertEqual(error.exception.payload['code'],'IMPORT_ALREADY_OPEN');call.assert_not_called()
    def test_native_errors_return_registered_partial_document(self):
        h=self.harness();p=h.source();h.native_errors=17
        with patch.object(n,'out_call',side_effect=h.load):
            with self.assertRaises(n.Failure) as error:h.import_step(str(p))
        self.assertEqual(error.exception.payload['document_id'],'imported')
        self.assertTrue(error.exception.payload['edit_may_be_partial'])
    def test_success_preserves_input_and_disables_configuration_mapping(self):
        h=self.harness();p=h.source();data=p.read_bytes()
        with patch.object(n,'out_call',side_effect=h.load):result=h.import_step(str(p))
        self.assertEqual(p.read_bytes(),data);self.assertFalse(h.settings.MapConfigurationData)
        self.assertEqual(result['import_source_sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(h.registered[1],dict(editable=True,owned=True))
        self.assertEqual(h.calls[-1][0],'LoadFile4');self.assertEqual(h.calls[-1][1][1],'r')
    def test_non_solid_result_is_explicitly_partial(self):
        h=self.harness();p=h.source();h.snapshot=lambda key:dict(kind=1,body_count=0,volume_mm3=0)
        with patch.object(n,'out_call',side_effect=h.load):
            with self.assertRaises(n.Failure) as error:h.import_step(str(p))
        self.assertEqual(error.exception.payload['code'],'IMPORT_SCOPE')
        self.assertTrue(error.exception.payload['edit_may_be_partial'])

if __name__=='__main__':unittest.main()
