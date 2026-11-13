"""Scoped official out-of-process API batching, with a recoverable flag lease."""
import json
from pathlib import Path


def process_id(sw):
    value=sw.GetProcessID
    return int(value() if callable(value) else value)


def restore_pending(sw,scratch):
    lease=Path(scratch)/'native_batch.json'
    if lease.exists():
        data=json.loads(lease.read_text(encoding='utf-8'))
        if set(data)!={'pid','previous'} or type(data['pid'])!=int or data['previous'] is not False:raise RuntimeError('Invalid native batch recovery record')
        if process_id(sw)!=data['pid']:raise RuntimeError('A different SOLIDWORKS instance is active; recorded flag recovery remains pending')
        sw.CommandInProgress=False
        lease.unlink()
    restore_display_pending(sw,scratch)
    from .export_options import restore_export_pending
    restore_export_pending(sw,scratch)


def restore_display_pending(sw,scratch):
    lease=Path(scratch)/'pose_display_lease.json'
    if not lease.exists():return
    data=json.loads(lease.read_text(encoding='utf-8'))
    if set(data)!={'pid','views'} or type(data['pid'])!=int or not isinstance(data['views'],list) or len(data['views'])>9:raise RuntimeError('Invalid display recovery record')
    if process_id(sw)!=data['pid']:raise RuntimeError('A different SOLIDWORKS instance is active; recorded display recovery remains pending')
    for row in data['views']:
        if not isinstance(row,dict) or set(row)!={'path','enabled'} or not isinstance(row['path'],str) or not row['path'] or type(row['enabled'])!=bool:raise RuntimeError('Invalid recorded model view')
    for row in data['views']:
        # Only existing, explicitly recorded documents. Never open a file or
        # touch dimensions while recovering a worker's display flags.
        doc=sw.GetOpenDocumentByName(row['path'])
        if doc is None:continue
        view=doc.ActiveView
        if callable(view):view=view()
        if view is None:continue
        binding=getattr(sw,'_binding',None)
        if binding is not None:view=binding.cast(view,'IModelView')
        elif hasattr(view,'_oleobj_'):
            import win32com.client
            view=win32com.client.CastTo(view,'IModelView')
        view.EnableGraphicsUpdate=row['enabled'];doc.GraphicsRedraw2()
    lease.unlink()


class NativeBatch:
    def __init__(self,sw,scratch):self.sw=sw;self.lease=Path(scratch)/'native_batch.json';self.changed=False
    def __enter__(self):
        if self.sw is not None:restore_pending(self.sw,self.lease.parent)
        if self.sw is not None and not bool(self.sw.CommandInProgress):
            self.lease.write_text(json.dumps({'pid':process_id(self.sw),'previous':False}),encoding='utf-8')
            self.changed=True;self.sw.CommandInProgress=True
        return self
    def __exit__(self,*error):
        if self.changed:
            self.sw.CommandInProgress=False
            self.lease.unlink(missing_ok=True)

