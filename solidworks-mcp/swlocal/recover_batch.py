"""Bounded helper: restore recorded batch/display flags, never geometry."""
import sys
from pathlib import Path
import pythoncom
import win32com.client
from .native_batch import restore_pending


def main():
    lease=Path(sys.argv[1]).resolve(strict=True)
    if lease.name not in ('native_batch.json','pose_display_lease.json','stl_preferences.json') or not lease.is_relative_to(Path(r'E:\simulink\_codex_tmp').resolve()):raise RuntimeError('Recovery file outside the runtime scope')
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        sw=win32com.client.GetActiveObject('SldWorks.Application')
        restore_pending(sw,lease.parent)
    finally:pythoncom.CoUninitialize()

if __name__=='__main__':main()
