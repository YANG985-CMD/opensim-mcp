"""Explicit SOLIDWORKS 2025 acceptance test through the real MCP stdio protocol.

Creates only new test models. Requires an empty output folder and an explicit
E-drive temporary folder; never discards documents present before this run.
"""
import argparse
import asyncio
import json
import math
import os
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT=Path(__file__).resolve().parents[1]


async def run(scratch,output):
    scratch.mkdir(parents=True,exist_ok=True)
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Use a new or empty output folder')
    output.mkdir(parents=True,exist_ok=True)
    prefix='mcp2025_'+uuid.uuid4().hex[:6]+'_'
    records=[]
    env=dict(os.environ,SWLOCAL_TEMP=str(scratch/'runtime'),SWLOCAL_OUTPUT=str(output),PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    params=StdioServerParameters(command=str(PROJECT/'.venv/Scripts/python.exe'),args=['-B','-u',str(PROJECT/'launch.py')],cwd=str(PROJECT),env=env)
    with (scratch/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                tools=await session.list_tools()
                assert {'sw_box','sw_mate_cylinders','sw_set_dimension','sw_export'}<={t.name for t in tools.tools}

                async def call(name,args=None,error=None):
                    result=await session.call_tool(name,args or {})
                    text='\n'.join(c.text for c in result.content if getattr(c,'type',None)=='text')
                    try: data=json.loads(text)
                    except ValueError: data={'text':text}
                    records.append({'tool':name,'arguments':args or {},'is_error':result.isError,'result':data})
                    (scratch/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(name,'EXPECTED_'+error if error else 'PASS',flush=True)
                    if error:
                        assert result.isError and error in text,(name,text)
                    else:
                        assert not result.isError,(name,text)
                    return data

                def edit(doc,**values):
                    return dict(document_id=doc['document_id'],state=doc['state'],**values)

                async def close(doc,discard=False):
                    await call('sw_close',{'document_id':doc['document_id'],'discard_changes':discard})

                health=await call('sw_health')
                connection=await call('sw_connect')
                assert connection['year']==2025
                before=(await call('sw_documents'))['documents']
                api=await call('sw_api_lookup',{'interface':'ICurve','member_name':'GetLength3'})
                assert api['total_matches']>0

                plate=await call('sw_new_document')
                plate=await call('sw_box',edit(plate,width_mm=40,height_mm=30,depth_mm=8))
                assert abs(plate['volume_mm3']-9600)<.01
                stale=plate.copy()
                plate=await call('sw_through_hole',edit(plate,diameter_mm=6))
                await call('sw_fillet',edit(stale,edge_ids=[0],radius_mm=1),'STALE_STATE')
                vertical=[e['edge_id'] for e in plate['edges'] if e['kind']=='line' and abs(e['length_mm']-8)<1e-5 and abs(e['direction'][2])>.999]
                assert len(vertical)==4
                plate=await call('sw_fillet',edit(plate,edge_ids=vertical,radius_mm=1))
                expected=9600-math.pi*9*8-4*(1-math.pi/4)*8
                assert abs(plate['volume_mm3']-expected)<.01
                plate_volume=plate['volume_mm3']
                await call('sw_features',{'document_id':plate['document_id']})
                plate_path=output/(prefix+'plate.SLDPRT')
                plate=await call('sw_save',edit(plate,path=str(plate_path)))
                await call('sw_export',edit(plate,path=str(output/(prefix+'plate.step'))))
                await close(plate)
                plate=await call('sw_open_document',{'path':str(plate_path)})
                assert abs(plate['volume_mm3']-plate_volume)<.01
                await call('sw_through_hole',edit(plate,diameter_mm=2),'READ_ONLY')
                await close(plate)

                shaft=await call('sw_new_document')
                shaft=await call('sw_cylinder',edit(shaft,diameter_mm=10,depth_mm=40))
                other=await call('sw_new_document')
                await call('sw_box',{'document_id':other['document_id'],'state':shaft['state'],'width_mm':10,'height_mm':10,'depth_mm':10},'STALE_STATE')
                other=await call('sw_box',edit(other,width_mm=10,height_mm=10,depth_mm=10))
                features=await call('sw_features',{'document_id':shaft['document_id']})
                dimension=next(d for f in features['features'] for d in f['dimensions'] if abs(d['value_si']-.04)<1e-6)
                shaft=await call('sw_set_dimension',edit(shaft,dimension_name=dimension['name'],value_si=.05))
                assert abs(shaft['volume_mm3']-math.pi*25*50)<.01
                unchanged=await call('sw_geometry',{'document_id':other['document_id']})
                assert abs(unchanged['volume_mm3']-1000)<.01
                await call('sw_close',{'document_id':other['document_id']},'UNSAVED_DOCUMENT')
                await close(other,True)
                shaft_path=output/(prefix+'shaft.SLDPRT')
                shaft=await call('sw_save',edit(shaft,path=str(shaft_path)))
                await call('sw_export',edit(shaft,path=str(output/(prefix+'shaft.stl'))))
                duplicate=await call('sw_new_document')
                await call('sw_save',edit(duplicate,path=str(output/'collision'/shaft_path.name)),'DOCUMENT_NAME_COLLISION')
                await close(duplicate,True)
                await call('sw_save',edit(shaft,path=str(PROJECT/'outside-output.SLDPRT')),'OUTPUT_SCOPE')
                await call('sw_save',edit(shaft,path=str(plate_path)),'FILE_EXISTS')
                await close(shaft)

                triangle=await call('sw_new_document')
                triangle=await call('sw_polygon',edit(triangle,vertices_mm=[[0,0],[20,0],[0,10]],depth_mm=5))
                assert abs(triangle['volume_mm3']-500)<.01
                await close(triangle,True)

                ring=await call('sw_new_document')
                ring=await call('sw_cylinder',edit(ring,diameter_mm=20,depth_mm=8))
                ring=await call('sw_through_hole',edit(ring,diameter_mm=10))
                assert abs(ring['volume_mm3']-math.pi*75*8)<.01
                ring_path=output/(prefix+'ring.SLDPRT')
                ring=await call('sw_save',edit(ring,path=str(ring_path)))
                await close(ring)

                assembly=await call('sw_new_document',{'kind':'assembly'})
                aid=assembly['document_id']
                assembly=await call('sw_add_component',edit(assembly,path=str(shaft_path),fixed=True))
                a=assembly['inserted_component']
                assembly=await call('sw_add_component',edit(assembly,path=str(ring_path),x_mm=30,z_mm=10,fixed=False))
                b=assembly['inserted_component']
                assert Path(next(c for c in assembly['components'] if c['name']==a)['path']).resolve()==shaft_path.resolve()
                assert Path(next(c for c in assembly['components'] if c['name']==b)['path']).resolve()==ring_path.resolve()
                ga=await call('sw_component_geometry',{'document_id':aid,'component_name':a})
                gb=await call('sw_component_geometry',{'document_id':aid,'component_name':b})
                fa=next(f['face_id'] for f in ga['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-10)<.001)
                fb=next(f['face_id'] for f in gb['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-10)<.001)
                assembly=await call('sw_mate_cylinders',edit(assembly,component_a=a,face_a=fa,component_b=b,face_b=fb))
                assert assembly['verification']['axis_offset_mm']<1e-4
                assert assembly['verification']['axis_angle_deg']<1e-4
                assert abs(next(c for c in assembly['components'] if c['name']==b)['transform'][9])<1e-7
                assembly_path=output/(prefix+'shaft-ring.SLDASM')
                assembly=await call('sw_save',edit(assembly,path=str(assembly_path)))
                await close(assembly)
                reopened=await call('sw_open_document',{'path':str(assembly_path)})
                assert len(reopened['components'])==2
                assert sorted(c['fixed'] for c in reopened['components'])==[False,True]
                assert abs(next(c for c in reopened['components'] if c['name']==b)['transform'][9])<1e-7
                await close(reopened)

                # Parts opened internally for insertion may remain loaded. Close only
                # files created in this run, never a pre-existing user document.
                after=(await call('sw_documents'))['documents']
                own_paths={str(shaft_path),str(ring_path),str(plate_path),str(assembly_path)}
                for doc in after:
                    if doc['path'] in own_paths: await close(doc)
                final=(await call('sw_documents'))['documents']
                assert {(d['title'],d['path']) for d in final}=={(d['title'],d['path']) for d in before}
                summary={'status':'PASS','solidworks_year':connection['year'],'revision':connection['revision'],'bridge_version':health['version'],'tools':len(tools.tools),'mcp_calls':len(records),'expected_errors':sum(bool(r['is_error']) for r in records),'plate_volume_mm3':plate_volume,'mate_verification':assembly['verification'],'output_folder':str(output),'pre_existing_documents_preserved':len(before)}
                (scratch/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-root',required=True,type=Path)
    parser.add_argument('--output-root',type=Path)
    args=parser.parse_args()
    scratch=args.temp_root.resolve()
    allowed=Path(r'E:\simulink\_codex_tmp').resolve()
    if not scratch.is_relative_to(allowed): parser.error('--temp-root must be under E:\\simulink\\_codex_tmp')
    asyncio.run(run(scratch,(args.output_root or scratch/'models').resolve()))
