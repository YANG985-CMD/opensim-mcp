"""Windows Job Objects: terminate a whole isolated workflow, including children.

The child must wait for its start gate before spawning descendants. Handles are
not inherited. Windows closes the kill-on-close job if the MCP server exits.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import os
import subprocess
import time


class BasicLimit(ctypes.Structure):
    _fields_=[('ProcessTime',ctypes.c_longlong),('JobTime',ctypes.c_longlong),
              ('Flags',w.DWORD),('MinWorkingSet',ctypes.c_size_t),('MaxWorkingSet',ctypes.c_size_t),
              ('ActiveProcessLimit',w.DWORD),('Affinity',ctypes.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]


class IO(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]


class ExtendedLimit(ctypes.Structure):
    _fields_=[('Basic',BasicLimit),('IO',IO),('ProcessMemory',ctypes.c_size_t),
              ('JobMemory',ctypes.c_size_t),('PeakProcessMemory',ctypes.c_size_t),('PeakJobMemory',ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_=[(name,ctypes.c_longlong) for name in ('User','Kernel','PeriodUser','PeriodKernel')]+[
        (name,w.DWORD) for name in ('PageFaults','Total','Active','Terminated')]


class ThreadEntry(ctypes.Structure):
    _fields_=[('Size',w.DWORD),('Usage',w.DWORD),('ThreadID',w.DWORD),('OwnerPID',w.DWORD),
              ('BasePriority',w.LONG),('DeltaPriority',w.LONG),('Flags',w.DWORD)]


class ProcessTree:
    def __init__(self):
        if os.name!='nt':
            raise RuntimeError('Reliable asynchronous cancellation requires Windows 11 Job Objects.')
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        signatures={
            'CreateJobObjectW':([ctypes.c_void_p,w.LPCWSTR],w.HANDLE),
            'SetInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD],w.BOOL),
            'AssignProcessToJobObject':([w.HANDLE,w.HANDLE],w.BOOL),
            'TerminateJobObject':([w.HANDLE,w.UINT],w.BOOL),
            'QueryInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p],w.BOOL),
            'CloseHandle':([w.HANDLE],w.BOOL),
            'CreateToolhelp32Snapshot':([w.DWORD,w.DWORD],w.HANDLE),
            'Thread32First':([w.HANDLE,ctypes.POINTER(ThreadEntry)],w.BOOL),
            'Thread32Next':([w.HANDLE,ctypes.POINTER(ThreadEntry)],w.BOOL),
            'OpenThread':([w.DWORD,w.BOOL,w.DWORD],w.HANDLE),
            'ResumeThread':([w.HANDLE],w.DWORD),
            'OpenProcess':([w.DWORD,w.BOOL,w.DWORD],w.HANDLE),
            'WaitForSingleObject':([w.HANDLE,w.DWORD],w.DWORD),
        }
        for name,(args,result) in signatures.items():
            getattr(k,name).argtypes=args;getattr(k,name).restype=result
        self.k=k
        self.handle=k.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=ExtendedLimit();limits.Basic.Flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            self.close();raise ctypes.WinError(ctypes.get_last_error())

    def assign(self,process):
        if not self.k.AssignProcessToJobObject(self.handle,w.HANDLE(int(process._handle))):
            process.kill();process.wait()
            raise RuntimeError('Cannot establish a Windows process-tree cancellation boundary: '+str(ctypes.WinError(ctypes.get_last_error())))

    def spawn(self,command,**kwargs):
        # A venv python.exe is itself a native redirector. Assigning it after a
        # normal Popen can miss the base interpreter it already spawned.
        kwargs['creationflags']=kwargs.get('creationflags',0)|0x4  # CREATE_SUSPENDED
        process=subprocess.Popen(command,**kwargs)
        try:
            self.assign(process)
            snapshot=self.k.CreateToolhelp32Snapshot(0x4,0)  # TH32CS_SNAPTHREAD
            if snapshot==w.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
            try:
                entry=ThreadEntry();entry.Size=ctypes.sizeof(entry)
                found=False;more=self.k.Thread32First(snapshot,ctypes.byref(entry))
                while more:
                    if entry.OwnerPID==process.pid:
                        thread=self.k.OpenThread(0x2,False,entry.ThreadID)
                        if not thread:raise ctypes.WinError(ctypes.get_last_error())
                        try:
                            if self.k.ResumeThread(thread)==0xFFFFFFFF:raise ctypes.WinError(ctypes.get_last_error())
                        finally:self.k.CloseHandle(thread)
                        found=True;break
                    more=self.k.Thread32Next(snapshot,ctypes.byref(entry))
                if not found:raise RuntimeError('Could not locate the suspended initial thread.')
            finally:self.k.CloseHandle(snapshot)
            return process
        except BaseException:
            self.terminate();process.wait(timeout=10);raise

    def active_count(self):
        info=Accounting()
        if not self.k.QueryInformationJobObject(self.handle,1,ctypes.byref(info),ctypes.sizeof(info),None):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.Active

    def terminate(self,timeout=10):
        if self.handle:
            # Accounting can reach ActiveProcesses=0 before all process objects
            # are signalled. Retain synchronizable handles before termination.
            size=8+ctypes.sizeof(ctypes.c_size_t)*4096;buffer=ctypes.create_string_buffer(size)
            handles=[]
            if not self.k.QueryInformationJobObject(self.handle,3,buffer,size,None):
                raise ctypes.WinError(ctypes.get_last_error())
            count=ctypes.cast(ctypes.byref(buffer,4),ctypes.POINTER(w.DWORD))[0]
            identifiers=(ctypes.c_size_t*count).from_buffer(buffer,8)
            for pid in identifiers:
                handle=self.k.OpenProcess(0x100000,False,pid)
                if handle:handles.append(handle)
            try:
                if not self.k.TerminateJobObject(self.handle,1):raise ctypes.WinError(ctypes.get_last_error())
                deadline=time.monotonic()+timeout
                while self.active_count() or any(self.k.WaitForSingleObject(h,0)==258 for h in handles):
                    if time.monotonic()>=deadline:raise TimeoutError('Windows process tree has not stopped; cancellation is not confirmed.')
                    time.sleep(.02)
            finally:
                for handle in handles:self.k.CloseHandle(handle)

    def close(self):
        if getattr(self,'handle',None):
            self.k.CloseHandle(self.handle);self.handle=None


def process_alive(pid):
    if os.name!='nt':return False
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.WaitForSingleObject.restype=w.DWORD
    k.CloseHandle.argtypes=[w.HANDLE]
    handle=k.OpenProcess(0x100000,False,pid)
    if not handle:return False
    try:return k.WaitForSingleObject(handle,0)==258
    finally:k.CloseHandle(handle)
