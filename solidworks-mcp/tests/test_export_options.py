import json,os,tempfile,types,unittest
from pathlib import Path
from swlocal.export_options import StlOptions,STL_TOGGLES,restore_export_pending


class StlTests(unittest.TestCase):
    def scratch(self):
        root=Path(os.environ.get('SWLOCAL_TEMP',r'E:\simulink\_codex_tmp\solidworks_test_runtime'));root.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)
    def test_success_and_export_error_restore_all_user_preferences(self):
        for fail in (False,True):
            with self.scratch() as p:
                toggles={k:not v for k,v in STL_TOGGLES.items()};old=dict(toggles);units={211:2}
                sw=types.SimpleNamespace(GetProcessID=lambda:123,GetUserPreferenceToggle=lambda k:toggles[k],SetUserPreferenceToggle=lambda k,v:toggles.update({k:v}),GetUserPreferenceIntegerValue=lambda k:units[k],SetUserPreferenceIntegerValue=lambda k,v:units.update({k:v}))
                try:
                    with StlOptions(sw,p):
                        self.assertEqual(toggles,STL_TOGGLES);self.assertEqual(units[211],0)
                        if fail:raise RuntimeError('native exporter failed')
                except RuntimeError:
                    if not fail:raise
                self.assertEqual(toggles,old);self.assertEqual(units[211],2);self.assertFalse((Path(p)/'stl_preferences.json').exists())
    def test_recovery_refuses_non_stl_setting_ids(self):
        with self.scratch() as p:
            lease=Path(p)/'stl_preferences.json';lease.write_text(json.dumps({'pid':123,'toggles':{'999999':False},'integers':{'211':0}}),encoding='utf-8')
            with self.assertRaises(RuntimeError):restore_export_pending(types.SimpleNamespace(GetProcessID=lambda:123),p)
            self.assertTrue(lease.exists())
