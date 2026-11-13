import unittest,types
from swlocal.reference_views import reference_view_plan,ReferenceViewTools
from swlocal.cad import Failure


class ReferenceViewTests(unittest.TestCase):
    def test_exact_names_and_repeated_reference_file_are_checked_before_closing(self):
        snap={'components':[{'name':'a','path':'one.SLDPRT'},{'name':'b','path':'one.SLDPRT'},{'name':'c','path':'two.SLDPRT'}]}
        self.assertEqual(reference_view_plan(snap,['a','b','c']),[('a','one.SLDPRT'),('c','two.SLDPRT')])
        for names in ([],['a','a'],['a','missing']):
            with self.assertRaises(ValueError):reference_view_plan(snap,names)
    def test_unsaved_part_is_skipped_without_close_or_save(self):
        snap={'kind':2,'components':[{'name':'a','path':'one.SLDPRT'}],'mates':[]};asm=types.SimpleNamespace(GetSaveFlag=True)
        part=types.SimpleNamespace(GetPathName='one.SLDPRT',GetSaveFlag=True,Visible=True)
        h=ReferenceViewTools();h._edit=lambda *a:(asm,snap);h._component=lambda *a:types.SimpleNamespace(GetModelDoc2=part);h.sw=types.SimpleNamespace(GetDocuments=[])
        h._activate=lambda doc:None;h.snapshot=lambda doc:snap
        result=h.close_reference_views('assembly','state',['a']);self.assertEqual(result['closed_reference_windows'],[]);self.assertEqual(result['skipped_reference_windows'][0]['reason'],'unsaved_changes_preserved')
    def test_hidden_unsaved_document_blocks_native_close(self):
        snap={'kind':2,'components':[{'name':'a','path':'one.SLDPRT'}],'mates':[]};asm=types.SimpleNamespace(GetSaveFlag=False)
        part=types.SimpleNamespace(GetPathName='one.SLDPRT',GetSaveFlag=False,Visible=True)
        h=ReferenceViewTools();h._edit=lambda *a:(asm,snap);h._component=lambda *a:types.SimpleNamespace(GetModelDoc2=part);h.sw=types.SimpleNamespace(GetDocuments=[types.SimpleNamespace(GetSaveFlag=True,Visible=False)])
        with self.assertRaises(Failure) as error:h.close_reference_views('assembly','state',['a'])
        self.assertEqual(error.exception.payload['code'],'UNSAVED_HIDDEN_DOCUMENT');self.assertFalse(error.exception.payload['edit_may_be_partial'])
