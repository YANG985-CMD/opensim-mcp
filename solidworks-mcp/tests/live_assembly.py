"""One bounded assembly acceptance case, with memory/GDI observations.

Creates two uniquely named native parts and one assembly. Never discards any
document. Stops on the first error without replaying the write operation.
"""
import argparse
import asyncio
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import uuid

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import win32api
import win32process

PROJECT=Path(__file__).resolve().parents[1]


class MemoryStatus(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','extended_virtual')]


def resources():
    state=MemoryStatus();state.length=ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise ctypes.WinError()
    result={'available_physical_gb':round(state.avail_phys/2**30,3),'commit_limit_gb':round(state.total_page/2**30,3),'available_commit_gb':round(state.avail_page/2**30,3),'solidworks':[]}
    listing=subprocess.check_output(['tasklist','/FI','IMAGENAME eq SLDWORKS.exe','/FO','CSV','/NH'],creationflags=subprocess.CREATE_NO_WINDOW)
    get_gui=ctypes.windll.user32.GetGuiResources
    get_gui.argtypes=[wintypes.HANDLE,wintypes.DWORD];get_gui.restype=wintypes.DWORD
    for line in listing.splitlines():
        if not line.lower().startswith(b'"sldworks.exe",'): continue
        pid=int(line.split(b',')[1].strip(b'"'))
        handle=win32api.OpenProcess(0x410,False,pid)
        try:
            info=win32process.GetProcessMemoryInfo(handle)
            result['solidworks'].append({'pid':pid,'working_set_gb':round(info['WorkingSetSize']/2**30,3),'private_commit_gb':round(info.get('PrivateUsage',info['PagefileUsage'])/2**30,3),'gdi_objects':get_gui(int(handle),0)})
        finally:handle.Close()
    return result


async def run(scratch,output):
    scratch.mkdir(parents=True,exist_ok=True)
    if output.exists() and any(output.iterdir()):raise RuntimeError('Use an empty output folder')
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    saved_hashes={}
    prefix='assembly_'+uuid.uuid4().hex[:8]
    params=StdioServerParameters(command=str(PROJECT/'.venv/Scripts/python.exe'),args=['-B','-u',str(PROJECT/'launch.py')],cwd=str(PROJECT),env=dict(os.environ,SWLOCAL_TEMP=str(scratch/'runtime'),SWLOCAL_OUTPUT=str(output),PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1'))
    with (scratch/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()

                async def call(name,args=None,allowed_error=None):
                    before=resources()
                    if before['available_commit_gb']<3 or before['available_physical_gb']<2 or any(p['gdi_objects']>=8500 for p in before['solidworks']):
                        raise RuntimeError('Resource margin too low; no next operation was issued')
                    result=await session.call_tool(name,args or {})
                    content='\n'.join(c.text for c in result.content if getattr(c,'type',None)=='text')
                    try:data=json.loads(content)
                    except ValueError:data={'text':content}
                    after=resources()
                    records.append({'tool':name,'arguments':args or {},'is_error':result.isError,'expected_error':allowed_error if result.isError and allowed_error and allowed_error in content else None,'result':data,'resources_before':before,'resources_after':after})
                    (scratch/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(name,'ERROR' if result.isError else 'PASS',json.dumps(after),flush=True)
                    if result.isError and (not allowed_error or allowed_error not in content):raise RuntimeError(content)
                    return data

                def edit(doc,**kw):return dict(document_id=doc['document_id'],state=doc['state'],**kw)
                async def close(doc):await call('sw_close',{'document_id':doc['document_id']})

                async def close_own_readonly(doc):
                    # Only exact files just created by this run qualify. Never
                    # infer ownership from a title or merely being read-only.
                    path=Path(doc['path']).resolve()
                    if doc['editable'] or str(path) not in saved_hashes:raise RuntimeError('Not a read-only verification document owned by this run')
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=saved_hashes[str(path)]:raise RuntimeError('Saved file changed during verification')
                    result=await call('sw_close',{'document_id':doc['document_id']},allowed_error='UNSAVED_DOCUMENT')
                    if 'text' in result:
                        fresh=await call('sw_geometry',{'document_id':doc['document_id']})
                        if fresh['state']!=doc['state'] or fresh['path']!=doc['path']:raise RuntimeError('Verification document changed; not discarding')
                        await call('sw_close',{'document_id':doc['document_id'],'discard_changes':True})

                connection=await call('sw_connect',{'start_if_needed':True})
                before=connection['documents']
                paths={}
                volumes={}
                for role in ('shaft','ring'):
                    doc=await call('sw_new_document',{'kind':'part'})
                    doc=await call('sw_cylinder',edit(doc,diameter_mm=10 if role=='shaft' else 20,depth_mm=50 if role=='shaft' else 8))
                    if role=='ring':doc=await call('sw_through_hole',edit(doc,diameter_mm=10))
                    expected=math.pi*25*50 if role=='shaft' else math.pi*75*8
                    assert abs(doc['volume_mm3']-expected)<.01
                    paths[role]=output/(prefix+'_'+role+'.SLDPRT')
                    saved=await call('sw_save',edit(doc,path=str(paths[role])))
                    saved_hashes[str(paths[role].resolve())]=saved['sha256']
                    await close(saved)
                    reopened=await call('sw_open_document',{'path':str(paths[role])})
                    assert Path(reopened['path']).resolve()==paths[role].resolve()
                    assert abs(reopened['volume_mm3']-expected)<.01
                    volumes[role]=reopened['volume_mm3']
                    await close_own_readonly(reopened)

                assembly=await call('sw_new_document',{'kind':'assembly'})
                assembly=await call('sw_add_component',edit(assembly,path=str(paths['shaft']),fixed=True))
                a=assembly['inserted_component']
                assembly=await call('sw_add_component',edit(assembly,path=str(paths['ring']),x_mm=30,z_mm=10,fixed=False))
                b=assembly['inserted_component']
                assert abs(next(c for c in assembly['components'] if c['name']==b)['transform'][9]-.03)<1e-8
                ga=await call('sw_component_geometry',{'document_id':assembly['document_id'],'component_name':a})
                gb=await call('sw_component_geometry',{'document_id':assembly['document_id'],'component_name':b})
                fa=next(f['face_id'] for f in ga['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-10)<.001)
                fb=next(f['face_id'] for f in gb['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-10)<.001)
                assembly=await call('sw_mate_cylinders',edit(assembly,component_a=a,face_a=fa,component_b=b,face_b=fb))
                verification=assembly['verification']
                assert verification['axis_angle_deg']<1e-4 and verification['axis_offset_mm']<1e-4
                assembly_path=output/(prefix+'.SLDASM')
                saved=await call('sw_save',edit(assembly,path=str(assembly_path)))
                saved_hashes[str(assembly_path.resolve())]=saved['sha256']
                await close(saved)
                reopened=await call('sw_open_document',{'path':str(assembly_path)})
                assert len(reopened['components'])==2
                actual={c['name']:c for c in reopened['components']}
                assert Path(actual[a]['path']).resolve()==paths['shaft'].resolve()
                assert Path(actual[b]['path']).resolve()==paths['ring'].resolve()
                assert actual[a]['fixed'] and not actual[b]['fixed']
                for axis in range(3):assert abs(actual[a]['transform'][9+axis])<1e-8
                assert abs(actual[b]['transform'][9])<1e-8 and abs(actual[b]['transform'][10])<1e-8
                assert abs(actual[b]['transform'][11]-.01)<1e-8
                features=await call('sw_features',{'document_id':reopened['document_id']})
                assert any('mate' in f['type'].lower() and f['type']!='MateGroup' for f in features['features'])
                await close_own_readonly(reopened)
                docs=(await call('sw_documents'))['documents']
                own_paths={str(p) for p in paths.values()}
                for d in docs:
                    if d['path'] in own_paths:
                        fresh=await call('sw_geometry',{'document_id':d['document_id']})
                        expected_volume=volumes['shaft' if Path(d['path']).resolve()==paths['shaft'].resolve() else 'ring']
                        if abs(fresh['volume_mm3']-expected_volume)>.01:raise RuntimeError('Child geometry changed during verification')
                        await close_own_readonly(fresh)
                final=(await call('sw_documents'))['documents']
                assert {(d['title'],d['path']) for d in before}=={(d['title'],d['path']) for d in final}
                all_resources=[r['resources_after'] for r in records]
                sw_resources=[p for r in all_resources for p in r['solidworks']]
                summary={'status':'PASS','year':connection['year'],'revision':connection['revision'],'calls':len(records),'native_files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [*paths.values(),assembly_path]],'volumes_mm3':volumes,'mate_verification':verification,'mate_features':[f for f in features['features'] if 'mate' in f['type'].lower()],'peak_sw_private_commit_gb':max(p['private_commit_gb'] for p in sw_resources),'peak_sw_gdi_objects':max(p['gdi_objects'] for p in sw_resources),'minimum_available_physical_gb':min(r['available_physical_gb'] for r in all_resources),'minimum_available_commit_gb':min(r['available_commit_gb'] for r in all_resources),'pre_existing_documents_preserved':len(before),'remaining_documents':len(final)}
                (scratch/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args()
    if not args.temp_root.resolve().is_relative_to(Path(r'E:\simulink\_codex_tmp').resolve()):parser.error('Temporary folder must be under E:\\simulink\\_codex_tmp')
    asyncio.run(run(args.temp_root.resolve(),args.output_root.resolve()))
