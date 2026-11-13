import hashlib,types,unittest
from pathlib import Path
from unittest.mock import patch
from swlocal.completion import CompletionTools
from swlocal.cad import CAD,Failure


class CompletionTests(unittest.TestCase):
    def harness(self,retained=False):
        h=CompletionTools();part=types.SimpleNamespace(GetPathName='part.SLDPRT',GetSaveFlag=False,Visible=True)
        h.documents={'part':{'model':part}};h._doc=lambda d:h.documents[d]
        h._part_fingerprints={'cached':True};h._mate_object_snapshots={'part':{}};h._component_map_cache='old'
        h.snapshot=lambda d:{'state':'same'};h._completion_parent_states=lambda path:{'assembly':{'mates':['hip'], 'modified':True}} if retained else {}
        h.closed=[]
        def close(path):
            h.closed.append(path)
            if retained:part.Visible=False
        h.sw=types.SimpleNamespace(GetDocuments=[part],CloseDoc=close,GetOpenDocumentByName=lambda p:part if retained else None)
        saved={'kind':1,'document_id':'part','state':'same','saved_path':'part.SLDPRT','sha256':hashlib.sha256(b'file').hexdigest()}
        return h,part,saved

    def test_completed_unreferenced_part_closes_and_invalidates_handle(self):
        h,part,saved=self.harness()
        with patch.object(Path,'read_bytes',return_value=b'file'):
            r=h._finish_saved_part_window('part',saved)
        self.assertEqual(h.closed,['part.SLDPRT']);self.assertIsNone(r['state']);self.assertFalse(r['document_handle_valid'])
        self.assertNotIn('part',h.documents);self.assertEqual(r['saved_state'],'same');self.assertTrue(r['window_cleanup']['document_unloaded'])

    def test_referenced_part_loses_window_but_preserves_parent_and_handle(self):
        h,part,saved=self.harness(True)
        with patch.object(Path,'read_bytes',return_value=b'file'):
            r=h._finish_saved_part_window('part',saved)
        self.assertFalse(part.Visible);self.assertTrue(r['reference_geometry_remains_loaded']);self.assertEqual(r['state'],'same')
        self.assertTrue(r['document_handle_valid']);self.assertEqual(r['window_cleanup']['parent_assemblies_verified'],1)

    def test_hidden_unsaved_document_is_never_closed_or_saved(self):
        h,part,saved=self.harness();h.sw.GetDocuments.append(types.SimpleNamespace(GetSaveFlag=True,Visible=False,GetPathName='',GetTitle='User unfinished model'))
        r=h._finish_saved_part_window('part',saved)
        self.assertEqual(h.closed,[]);self.assertTrue(part.Visible);self.assertEqual(r['window_cleanup']['reason'],'hidden_unsaved_documents_preserved')

    def test_new_edit_after_save_keeps_window(self):
        h,part,saved=self.harness();part.GetSaveFlag=True
        r=h._finish_saved_part_window('part',saved)
        self.assertEqual(h.closed,[]);self.assertEqual(r['window_cleanup']['reason'],'document_changed_after_save')

    def test_parent_change_after_close_reports_saved_partial_no_retry(self):
        h,part,saved=self.harness(True);states=iter([{'pose':0},{'pose':1}]);h._completion_parent_states=lambda p:next(states)
        with patch.object(Path,'read_bytes',return_value=b'file'),self.assertRaises(Failure) as error:
            h._finish_saved_part_window('part',saved)
        self.assertEqual(error.exception.payload['code'],'FINISH_WINDOW_PARTIAL');self.assertTrue(error.exception.payload['native_save_succeeded'])
        self.assertFalse(error.exception.payload['retry_automatically']);self.assertEqual(len(h.closed),1)

    def test_close_that_leaves_window_visible_is_not_reported_success(self):
        h,part,saved=self.harness(True);h.sw.CloseDoc=lambda p:h.closed.append(p)
        with self.assertRaises(Failure) as error:h._finish_saved_part_window('part',saved)
        self.assertTrue(error.exception.payload['native_save_succeeded']);self.assertTrue(part.Visible)

    def test_assembly_is_saved_but_kept_open(self):
        h,part,saved=self.harness();saved['kind']=2
        r=h._finish_saved_part_window('part',saved)
        self.assertEqual(h.closed,[]);self.assertEqual(r['window_cleanup']['reason'],'assembly_kept_open_use_explicit_close_when_finished')

    def test_invalid_completion_flag_fails_before_save(self):
        h=types.SimpleNamespace(_edit=lambda *args:self.fail('must validate before native save'))
        with self.assertRaises(Failure):CAD.save(h,'id','state','part.SLDPRT',close_when_finished='true')


if __name__=='__main__':unittest.main()
