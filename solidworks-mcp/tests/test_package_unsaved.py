import os,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from swlocal.organization import OrganizationTools
from swlocal import cad as n

class Advanced:
    def __init__(self,paths):self.paths=paths
    def SetPrefixSuffixToAll(self,*args):pass
    def GetItemsNameAndPath(self,*args):return tuple(range(len(self.paths))),tuple(p.name for p in self.paths),tuple(str(p.parent) for p in self.paths)
    def ModifyItemsNameAndPath(self,ids,names,dirs):
        self.paths=[Path(d)/s for d,s in zip(dirs.value,names.value)];return 0

class Harness(OrganizationTools):
    def __init__(self,root,dirty=True,part_dirty=False):
        self.root=root;self.paths=[root/'Source.SLDASM',root/'Part.SLDPRT']
        for p in self.paths:p.write_bytes(b'SOURCE'+b'x'*160)
        self.modified=dirty;self.calls=[];self.advanced=Advanced(self.paths.copy())
        self.part=types.SimpleNamespace(GetType=lambda:1,GetSaveFlag=lambda:part_dirty)
        self.comp=types.SimpleNamespace(GetModelDoc2=lambda:self.part)
        self.model=types.SimpleNamespace(GetSaveFlag=lambda:self.modified,SetSaveFlag=self.restore,
            GetComponents=lambda top:[self.comp],Extension=types.SimpleNamespace(GetAdvancedSaveAsOptions=lambda value:self.advanced))
        self.before=dict(path=str(self.paths[0]),state='same',components=[{'path':str(self.paths[1])}])
        self.binding=types.SimpleNamespace(cast=lambda obj,interface:obj)
    def restore(self):self.modified=True;self.calls.append('restore_dirty')
    def _edit(self,*args):return self.model,self.before.copy()
    def _output_path(self,*args):pass
    def _check_name_collision(self,*args):pass
    def snapshot(self,*args):return self.before.copy()
    def save_copy(self,obj,name,args,count):
        self.calls.append(name);self.assert_copy_mode=args[2]==3 and self.advanced.SaveAllAsCopy
        for p in self.advanced.paths:p.write_bytes(b'COPY'+b'y'*170)
        self.modified=False;return True,0,0
    def names(self):return [{'source_path':str(p),'file_name':('NEW-ASM-001_Copy.SLDASM' if p.suffix=='.SLDASM' else 'NEW-HIP-001_Part.SLDPRT')} for p in self.paths]

class UnsavedPackageTests(unittest.TestCase):
    def test_dirty_source_requires_explicit_copy_authorization(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as name:
            h=Harness(Path(name))
            with self.assertRaises(n.Failure):h.package_assembly('doc','same',str(Path(name)/'out'),h.names())
            self.assertEqual(h.calls,[]);self.assertTrue(h.modified)
    def test_explicit_copy_keeps_original_bytes_and_unsaved_flag(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as name:
            h=Harness(Path(name));before=[p.read_bytes() for p in h.paths]
            with patch.object(n,'out_call',side_effect=h.save_copy):r=h.package_assembly('doc','same',str(Path(name)/'out'),h.names(),True)
            self.assertTrue(h.assert_copy_mode);self.assertTrue(h.modified)
            self.assertEqual([p.read_bytes() for p in h.paths],before)
            self.assertTrue(r['source_unsaved_flag_unchanged']);self.assertTrue(r['unsaved_assembly_state_included'])
    def test_unsaved_parts_are_never_implicitly_included(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as name:
            h=Harness(Path(name),part_dirty=True)
            with self.assertRaises(n.Failure):h.package_assembly('doc','same',str(Path(name)/'out'),h.names(),True)
            self.assertEqual(h.calls,[])
    def test_copy_never_overwrites_a_nonempty_destination(self):
        with tempfile.TemporaryDirectory(dir=os.environ['SWLOCAL_TEMP']) as name:
            h=Harness(Path(name));out=Path(name)/'out';out.mkdir();(out/'existing').write_text('keep')
            with self.assertRaises(n.Failure):h.package_assembly('doc','same',str(out),h.names(),True)
            self.assertEqual((out/'existing').read_text(),'keep');self.assertEqual(h.calls,[])

if __name__=='__main__':unittest.main()
