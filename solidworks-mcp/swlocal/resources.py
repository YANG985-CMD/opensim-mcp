"""Read Windows memory margins without starting or closing applications."""
import ctypes
from ctypes import wintypes


class MemoryStatus(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','extended_virtual')]


def memory_margins():
    state=MemoryStatus();state.length=ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):raise ctypes.WinError()
    return {'available_physical_gb':round(state.avail_phys/2**30,3),'available_commit_gb':round(state.avail_page/2**30,3)}


def enough_memory(values):return values['available_physical_gb']>=2 and values['available_commit_gb']>=3
