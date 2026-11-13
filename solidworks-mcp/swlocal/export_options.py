"""Scoped STL settings. IDs verified against the installed 2025 swconst.tlb."""
import json
from pathlib import Path

# Binary, no info dialog, retain native origin, one assembly file,
# no second implicit interference operation, no preview dialog.
STL_TOGGLES={69:True,70:False,71:True,72:True,73:False,191:False}
STL_INTEGERS={211:0} # swExportStlUnits = swMM


def restore_export_pending(sw,scratch):
    lease=Path(scratch)/'stl_preferences.json'
    if not lease.exists():return
    from .native_batch import process_id
    data=json.loads(lease.read_text(encoding='utf-8'))
    if set(data)!={'pid','toggles','integers'} or type(data['pid'])!=int or data['pid']!=process_id(sw):raise RuntimeError('STL preference recovery belongs to another native process')
    toggles=data['toggles'];integers=data['integers']
    if not isinstance(toggles,dict) or set(toggles)!={str(k) for k in STL_TOGGLES} or any(type(v)!=bool for v in toggles.values()):raise RuntimeError('Invalid recorded STL toggles')
    if not isinstance(integers,dict) or set(integers)!={'211'} or type(integers['211'])!=int or not 0<=integers['211']<=4:raise RuntimeError('Invalid recorded STL units')
    for key,value in toggles.items():
        sw.SetUserPreferenceToggle(int(key),value)
        if bool(sw.GetUserPreferenceToggle(int(key)))!=value:raise RuntimeError('STL toggle restoration failed')
    for key,value in integers.items():
        sw.SetUserPreferenceIntegerValue(int(key),value)
        if int(sw.GetUserPreferenceIntegerValue(int(key)))!=value:raise RuntimeError('STL unit restoration failed')
    lease.unlink()


class StlOptions:
    def __init__(self,sw,scratch):self.sw=sw;self.scratch=Path(scratch)
    def __enter__(self):
        from .native_batch import process_id
        restore_export_pending(self.sw,self.scratch)
        data={'pid':process_id(self.sw),'toggles':{str(k):bool(self.sw.GetUserPreferenceToggle(k)) for k in STL_TOGGLES},'integers':{str(k):int(self.sw.GetUserPreferenceIntegerValue(k)) for k in STL_INTEGERS}}
        (self.scratch/'stl_preferences.json').write_text(json.dumps(data),encoding='utf-8')
        try:
            for key,value in STL_TOGGLES.items():
                self.sw.SetUserPreferenceToggle(key,value)
                if bool(self.sw.GetUserPreferenceToggle(key))!=value:raise RuntimeError('STL export toggle was not accepted')
            for key,value in STL_INTEGERS.items():
                self.sw.SetUserPreferenceIntegerValue(key,value)
                if int(self.sw.GetUserPreferenceIntegerValue(key))!=value:raise RuntimeError('STL export unit was not accepted')
        except Exception:
            restore_export_pending(self.sw,self.scratch);raise
        return self
    def __exit__(self,*error):restore_export_pending(self.sw,self.scratch)
