"""Read-only recovery must preserve unsaved models and honour native refusal."""
import tempfile
import os
import types
import unittest
from pathlib import Path
from swlocal.cad import CAD, Failure


class AccessTests(unittest.TestCase):
    def fixture(self, folder):
        path=Path(folder)/'saved.SLDASM';path.write_bytes(b'owned test fixture')
        data={'read_only':True,'modified':True,'state':'fresh'};calls=[]
        def set_access(value):
            calls.append(value);data['read_only']=value;return True
        model=types.SimpleNamespace(IsOpenedReadOnly=lambda:data['read_only'],GetSaveFlag=lambda:data['modified'],SetReadOnlyState=set_access)
        c=object.__new__(CAD);c.documents={'doc':{'model':model,'editable':False}}
        c._app=lambda:types.SimpleNamespace(GetOpenDocumentByName=lambda _:model)
        def register(model,editable=False):
            c.documents['doc']['editable'] |= editable
            return 'doc'
        c._register=register;c.snapshot=lambda _: {'document_id':'doc','state':data['state'],'editable':c.documents['doc']['editable']}
        return c,path,data,calls,model

    def test_restore_in_place_keeps_unsaved_edits_and_grants_bridge_permission(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as folder:
            c,path,data,calls,_=self.fixture(folder)
            result=c.open_document(str(path),editable=True,state='fresh')
            self.assertEqual(calls,[False]);self.assertFalse(data['read_only'])
            self.assertTrue(data['modified']);self.assertTrue(result['editable'])
            self.assertEqual(path.read_bytes(),b'owned test fixture')

    def test_missing_or_stale_state_never_requests_native_write_access(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as folder:
            c,path,data,calls,_=self.fixture(folder)
            for state in (None,'old'):
                with self.assertRaises(Failure) as caught:c.open_document(str(path),editable=True,state=state)
                self.assertEqual(caught.exception.payload['code'],'STALE_STATE')
            self.assertEqual(calls,[]);self.assertTrue(data['read_only'])

    def test_another_writer_refusal_does_not_save_close_or_change_attributes(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as folder:
            c,path,data,calls,model=self.fixture(folder)
            model.SetReadOnlyState=lambda _:False
            with self.assertRaises(Failure) as caught:c.open_document(str(path),editable=True,state='fresh')
            self.assertEqual(caught.exception.payload['code'],'FILE_READ_ONLY')
            self.assertFalse(c.documents['doc']['editable']);self.assertTrue(data['modified'])

    def test_read_only_inspection_never_downgrades_an_existing_writable_model(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as folder:
            c,path,data,calls,_=self.fixture(folder);data['read_only']=False
            c.open_document(str(path),editable=False)
            self.assertFalse(data['read_only']);self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
