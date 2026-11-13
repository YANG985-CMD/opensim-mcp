"""Cooperating Windows processes share a kernel-owned byte-range lock.

The OS releases it when its owner exits; lock files contain no credentials.
"""
import os,threading,time
from contextlib import contextmanager
from .core import InputError

class FileLock:
    def __init__(self,path,timeout=30):
        self.path=path;self.timeout=timeout;self.local=threading.local()

    @contextmanager
    def held(self):
        if getattr(self.local,'depth',0):
            self.local.depth+=1
            try:yield
            finally:self.local.depth-=1
            return
        if os.name!='nt':raise InputError('Cross-process GUI locking requires Windows.')
        import msvcrt
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('a+b') as stream:
            if stream.seek(0,2)==0:stream.write(b'\0');stream.flush()
            deadline=time.monotonic()+self.timeout
            while True:
                try:
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError as exc:
                    if time.monotonic()>=deadline:raise InputError('GUI busy in another process; wait, then refresh GUI status before editing.') from exc
                    time.sleep(.05)
            self.local.depth=1
            try:yield
            finally:
                self.local.depth=0;stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
