"""Real MCP/native revolute and prismatic acceptance, with independent pose checks.

Only creates uniquely named files in an empty test output directory. A failed
mutation is never replayed. The durable journal retains the exact failing call.
"""
import argparse,asyncio,json,math,os,sys,hashlib,uuid,shutil
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
sys.path.insert(0,str(Path(__file__).resolve().parent))
from live_assembly import resources
PROJECT=Path(__file__).resolve().parents[1]


async def run(scratch,output,reuse_parts_root=None,reuse_prefix=None):
    scratch.mkdir(parents=True,exist_ok=True)
    if output.exists() and any(output.iterdir()):raise RuntimeError('Use an empty output directory; failed writes are not automatically retried')
    output.mkdir(parents=True,exist_ok=True)
    prefix='kin_'+uuid.uuid4().hex[:7];records=[];paths={};summaries={}
    params=StdioServerParameters(command=str(PROJECT/'.venv/Scripts/python.exe'),args=['-B','-u',str(PROJECT/'launch.py')],cwd=str(PROJECT),env=dict(os.environ,SWLOCAL_TEMP=str(scratch/'runtime'),SWLOCAL_OUTPUT=str(output),PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1'))
    with (scratch/'mcp.log').open('w',encoding='utf-8') as log:
      async with stdio_client(params,errlog=log) as (reader,writer):
       async with ClientSession(reader,writer) as session:
        init=await session.initialize();tools=await session.list_tools()
        async def call(tool,args=None,allowed_error=None):
            pre=resources()
            if pre['available_commit_gb']<3 or pre['available_physical_gb']<2:raise RuntimeError('Resource margin too low; no next native operation issued')
            result=await session.call_tool(tool,args or {})
            text='\n'.join(c.text for c in result.content if c.type=='text')
            try:data=json.loads(text)
            except ValueError:data={'text':text}
            record={'tool':tool,'arguments':args or {},'is_error':bool(result.isError),'result':data,'resources':resources()};records.append(record)
            (scratch/'calls.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'tool':tool,'error':bool(result.isError),'call':len(records)},ensure_ascii=True),flush=True)
            if result.isError and not (allowed_error and allowed_error in text):raise RuntimeError(text)
            return data
        def edit(doc,**kw):return dict(document_id=doc['document_id'],state=doc['state'],**kw)
        def ref(comp,plane):return {'component':comp,'plane_name':plane}
        async def save(doc,path):return await call('sw_save',edit(doc,path=str(path)))
        async def close_own(doc):
            await call('sw_close',{'document_id':doc['document_id'],'discard_changes':True})
        async def geo(doc,comp):return await call('sw_component_geometry',{'document_id':doc['document_id'],'component_name':comp})
        def cylinder(g,diameter):return next(f['face_id'] for f in g['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-diameter)<1e-4)
        def plane(g,axis):return next(p['plane_name'] for p in g['reference_planes'] if abs(p['normal'][axis])>.99999)
        async def mate(doc,kind,a,b,**kw):return await call('sw_add_mate',edit(doc,mate_type=kind,reference_a=a,reference_b=b,**kw))
        connection=await call('sw_connect',{'start_if_needed':True});before=connection['documents']
        assert init.serverInfo.name=='solidworks-mcp'
        assert {'sw_set_mate_position','sw_create_joint','sw_scan_motion'}<={t.name for t in tools.tools}
        for role,dia,depth,hole in [('shaft',10,180,0),('arm',24,8,10),('slider',24,8,10)]:
            if reuse_parts_root is not None:
                source=reuse_parts_root/(reuse_prefix+'_'+role+'.SLDPRT')
                paths[role]=output/(prefix+'_'+role+'.SLDPRT');shutil.copy2(source,paths[role])
                assert hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(paths[role].read_bytes()).digest()
                d=await call('sw_open_document',{'path':str(paths[role])})
                expected=math.pi*((dia/2)**2-(hole/2)**2)*depth-(math.pi*1.5**2*depth if role=='arm' else 0)
                assert d['body_count']==1 and abs(d['volume_mm3']-expected)<.001
                if role=='shaft':
                    mass=await call('sw_mass_properties',{'document_id':d['document_id']});assert mass['all_parts_have_assigned_materials'] and .02<mass['mass_kg']<.08
                await close_own(d)
                continue
            d=await call('sw_new_document',{'kind':'part'})
            d=await call('sw_cylinder',edit(d,diameter_mm=dia,depth_mm=depth))
            if hole:d=await call('sw_through_hole',edit(d,diameter_mm=hole))
            if role=='arm':d=await call('sw_through_hole',edit(d,diameter_mm=3,x_mm=8))
            if role=='shaft':
                materials=await call('sw_materials',{'query':'6061','maximum':10});assert materials['materials']
                material=materials['materials'][0]
                d=await call('sw_set_material',edit(d,**material))
                assert d['mass_properties']['all_parts_have_assigned_materials']
                assert .02<d['mass_properties']['mass_kg']<.08
            paths[role]=output/(prefix+'_'+role+'.SLDPRT');d=await save(d,paths[role]);await close_own(d)
        for joint in ['revolute','prismatic']:
            d=await call('sw_new_document',{'kind':'assembly'})
            d=await call('sw_add_component',edit(d,path=str(paths['shaft']),fixed=True));base=d['inserted_component']
            d=await call('sw_add_component',edit(d,path=str(paths['arm' if joint=='revolute' else 'slider']),x_mm=30,z_mm=10 if joint=='revolute' else 80,fixed=True));moving=d['inserted_component']
            d=await call('sw_set_component_fixed',edit(d,component_name=moving,fixed=False))
            ga=await geo(d,base);gb=await geo(d,moving)
            d=await mate(d,'concentric',{'component':base,'face_id':cylinder(ga,10)},{'component':moving,'face_id':cylinder(gb,10)},lock_rotation=joint=='prismatic',name=joint+'_axis')
            ga=await geo(d,base);gb=await geo(d,moving)
            if joint=='revolute':
                d=await mate(d,'distance',ref(base,plane(ga,2)),ref(moving,plane(gb,2)),value=10,name='hip_axial_position')
                ga=await geo(d,base);gb=await geo(d,moving)
                d=await mate(d,'limit_angle',ref(base,plane(ga,0)),ref(moving,plane(gb,1)),value=90,minimum=69,maximum=113,name='hip_ROM_69_113_deg')
            else:
                d=await mate(d,'limit_distance',ref(base,plane(ga,2)),ref(moving,plane(gb,2)),value=80,minimum=10,maximum=150,name='carriage_10_150_mm')
            status=await call('sw_assembly_status',{'document_id':d['document_id']})
            moving_status=next(c for c in status['components'] if c['name']==moving)
            assert not moving_status['fixed'] and moving_status['native_constraint_status'] not in (4,5,6),moving_status
            moves=[]
            driven_name='hip_ROM_69_113_deg' if joint=='revolute' else 'carriage_10_150_mm'
            for target in ([69,100,80,113,90] if joint=='revolute' else [10,100,60,150,80]):
                d=await call('sw_set_mate_position',edit(d,mate_name=driven_name,value=target));t=next(c['transform'] for c in d['components'] if c['name']==moving);angle=math.degrees(math.atan2(t[1],t[0]));z=t[11]*1000
                if joint=='revolute':
                    assert abs(z-10)<1e-4,z
                    assert -21.001<=angle<=23.001,angle
                    assert abs(angle-(target-90))<1e-4,(angle,target)
                else:
                    assert 9.999<=z<=150.001,z
                    assert max(abs(t[i]-([1,0,0,0,1,0,0,0,1][i])) for i in range(9))<1e-6
                    assert abs(z-target)<1e-4,(z,target)
                moves.append({'native_mate_position':target,'angle_deg':angle,'z_mm':z,'pose_verified':True})
            for target in ([68,114] if joint=='revolute' else [9,151]):
                await call('sw_set_mate_position',edit(d,mate_name=driven_name,value=target),allowed_error='MATE_LIMIT')
                fresh=await call('sw_geometry',{'document_id':d['document_id']});assert fresh['state']==d['state'];d=fresh
            # Independently try prohibited transverse motion. No pose override.
            d=await call('sw_move_component',edit(d,component_name=moving,translation_mm=[10,0,0]))
            assert not d['request_achieved'] and abs(d['achieved_transform'][9])<1e-7
            interference=await call('sw_check_interference',{'document_id':d['document_id']})
            assert interference['count']==0,interference
            path=output/(prefix+'_'+joint+'.SLDASM');d=await save(d,path)
            components=d['components'];mate_names=[r['name'] for r in d['mates']]
            await close_own(d)
            d=await call('sw_open_document',{'path':str(path),'editable':True})
            persisted=lambda rows:{c['name']:{k:v for k,v in c.items() if k!='native_part_update_stamp'} for c in rows}
            assert persisted(d['components'])==persisted(components) # update stamps are session-local, not persisted geometry
            assert [r['name'] for r in d['mates']]==mate_names
            reopened_status=await call('sw_assembly_status',{'document_id':d['document_id']})
            assert not next(c for c in reopened_status['components'] if c['name']==moving)['fixed']
            d=await call('sw_set_mate_position',edit(d,mate_name=driven_name,value=100))
            t=next(c['transform'] for c in d['components'] if c['name']==moving)
            assert abs((math.degrees(math.atan2(t[1],t[0])) if joint=='revolute' else t[11]*1000)-(10 if joint=='revolute' else 100))<1e-4
            summaries[joint]={'assembly':str(path),'moves':moves,'reopened_mates':reopened_status['mates'],'reopened_components':reopened_status['components']}
            await close_own(d)
        # Positive interference control: native volume, not a bounding-box test.
        d=await call('sw_new_document',{'kind':'part'});d=await call('sw_box',edit(d,width_mm=10,height_mm=10,depth_mm=10));p=output/(prefix+'_cube.SLDPRT');d=await save(d,p);await close_own(d)
        d=await call('sw_new_document',{'kind':'assembly'});d=await call('sw_add_component',edit(d,path=str(p),fixed=True));a=d['inserted_component'];d=await call('sw_add_component',edit(d,path=str(p),x_mm=5,fixed=False));b=d['inserted_component']
        interference=await call('sw_check_interference',{'document_id':d['document_id']})
        assert len(interference['interferences'])==1 and abs(interference['interferences'][0]['volume_mm3']-500)<1e-3,interference
        d=await mate(d,'lock',{'component':a},{'component':b},name='rigid_offset_pair')
        status=await call('sw_assembly_status',{'document_id':d['document_id']})
        assert next(c for c in status['components'] if c['name']==b)['native_constraint_status']==3
        path=output/(prefix+'_rigid_pair.SLDASM');d=await save(d,path);await close_own(d)
        summaries['rigid_pair']={'assembly':str(path),'interference':interference,'status':status}
        final=await call('sw_documents')
        own_paths={str(p.resolve()) for p in paths.values()}|{str(p.resolve())}
        for doc in final['documents']:
            if doc['path'] in own_paths:await close_own(doc)
        final=await call('sw_documents')
        assert {(d['path'],d['title']) for d in before}=={(d['path'],d['title']) for d in final['documents']}
        report={'status':'PASS','server_name':init.serverInfo.name,'tool_count':len(tools.tools),'revision':connection['revision'],'cases':summaries,'calls':len(records),'preexisting_documents_preserved':True}
        (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (scratch/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':'PASS','calls':len(records),'output':str(output)},ensure_ascii=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--temp-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--reuse-parts-root',type=Path);p.add_argument('--reuse-prefix');args=p.parse_args()
    if not args.temp_root.resolve().is_relative_to(Path(r'E:\simulink\_codex_tmp').resolve()):p.error('Temporary data must remain on the designated E drive root')
    if bool(args.reuse_parts_root)!=bool(args.reuse_prefix):p.error('Reuse directory and prefix must be supplied together')
    asyncio.run(run(args.temp_root,args.output_root,args.reuse_parts_root,args.reuse_prefix))
