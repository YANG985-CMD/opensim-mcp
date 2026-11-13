import json,os,tempfile,types,unittest
from pathlib import Path
from swlocal.native_batch import NativeBatch,restore_pending


class BatchTests(unittest.TestCase):
    def scratch(self):
        root=Path(os.environ.get('SWLOCAL_TEMP',r'E:\simulink\_codex_tmp\solidworks_test_runtime'));root.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)
    def test_scope_restores_flag_after_success_and_error(self):
        with self.scratch() as p:
            sw=types.SimpleNamespace(CommandInProgress=False,GetProcessID=lambda:123)
            for fail in (False,True):
                try:
                    with NativeBatch(sw,p):
                        self.assertTrue(sw.CommandInProgress);self.assertTrue((Path(p)/'native_batch.json').exists())
                        if fail:raise ValueError('test')
                except ValueError:pass
                self.assertFalse(sw.CommandInProgress);self.assertFalse((Path(p)/'native_batch.json').exists())
    def test_existing_native_flag_is_preserved(self):
        with self.scratch() as p:
            sw=types.SimpleNamespace(CommandInProgress=True)
            with NativeBatch(sw,p):pass
            self.assertTrue(sw.CommandInProgress);self.assertFalse((Path(p)/'native_batch.json').exists())
    def test_recovery_only_restores_the_recorded_native_process(self):
        with self.scratch() as p:
            sw=types.SimpleNamespace(CommandInProgress=True,GetProcessID=lambda:123)
            lease=Path(p)/'native_batch.json';lease.write_text(json.dumps({'pid':124,'previous':False}),encoding='utf-8')
            with self.assertRaises(RuntimeError):restore_pending(sw,p)
            self.assertTrue(sw.CommandInProgress);self.assertTrue(lease.exists())
            lease.write_text(json.dumps({'pid':123,'previous':False}),encoding='utf-8');restore_pending(sw,p);self.assertFalse(sw.CommandInProgress)
    def test_display_recovery_never_opens_or_edits_a_model(self):
        with self.scratch() as p:
            view=types.SimpleNamespace(EnableGraphicsUpdate=False);redraw=[]
            doc=types.SimpleNamespace(ActiveView=view,GraphicsRedraw2=lambda:redraw.append(True))
            sw=types.SimpleNamespace(GetProcessID=lambda:123,GetOpenDocumentByName=lambda path:doc if path=='saved.SLDASM' else None)
            lease=Path(p)/'pose_display_lease.json';lease.write_text(json.dumps({'pid':123,'views':[{'path':'saved.SLDASM','enabled':True},{'path':'already_closed.SLDPRT','enabled':False}]}),encoding='utf-8')
            restore_pending(sw,p);self.assertTrue(view.EnableGraphicsUpdate);self.assertEqual(redraw,[True]);self.assertFalse(lease.exists())
    def test_wrong_process_preserves_display_lease(self):
        with self.scratch() as p:
            lease=Path(p)/'pose_display_lease.json';lease.write_text(json.dumps({'pid':124,'views':[]}),encoding='utf-8')
            with self.assertRaises(RuntimeError):restore_pending(types.SimpleNamespace(GetProcessID=lambda:123),p)
            self.assertTrue(lease.exists())

if __name__=='__main__':unittest.main()
