"""Three connected native parts: limited rotation + keyed axial slide.

Uses previously verified parts, never overwrites them. Proves propagation to
the carriage and save/reopen pose control through actual MCP stdio tools.
"""
import argparse,asyncio,json,math,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
sys.path.insert(0,str(Path(__file__).resolve().parent))
from live_assembly import resources
ROOT=Path(__file__).resolve().parents[1]

async def run(output,scratch,free=False):
    scratch.mkdir(parents=True,exist_ok=True)
    acceptance=json.loads((output/'verification.json').read_text(encoding='utf-8'))
    assert acceptance['status']=='PASS'
    prefix=Path(acceptance['cases']['revolute']['assembly']).stem.removesuffix('_revolute')
    path=output/('自由机构_转动与滑动.SLDASM' if free else '连接机构_转动与滑动.SLDASM')
    if path.exists():raise RuntimeError('Refusing to overwrite a prior linked assembly')
    records=[];poses=[]
    params=StdioServerParameters(command=str(ROOT/'.venv/Scripts/python.exe'),args=['-B','-u',str(ROOT/'launch.py')],cwd=str(ROOT),env=dict(os.environ,SWLOCAL_TEMP=str(scratch/'runtime'),SWLOCAL_OUTPUT=str(output)))
    with (scratch/'mcp.log').open('w',encoding='utf-8') as log:
      async with stdio_client(params,errlog=log) as (r,w):
       async with ClientSession(r,w) as session:
        init=await session.initialize();listed=await session.list_tools()
        assert init.serverInfo.name=='solidworks-mcp' and {'sw_set_mate_position','sw_create_joint','sw_scan_motion'}<={t.name for t in listed.tools}
        async def call(tool,args=None):
            memory=resources()
            if memory['available_commit_gb']<3 or memory['available_physical_gb']<2:raise RuntimeError('Resources low; no next operation issued')
            rr=await session.call_tool(tool,args or {});txt='\n'.join(c.text for c in rr.content if c.type=='text')
            try:data=json.loads(txt)
            except ValueError:data={'text':txt}
            records.append({'tool':tool,'arguments':args or {},'is_error':bool(rr.isError),'result':data,'resources':memory})
            (scratch/'calls.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'tool':tool,'call':len(records),'error':bool(rr.isError)}),flush=True)
            if rr.isError:raise RuntimeError(txt)
            return data
        def edit(d,**kw):return dict(document_id=d['document_id'],state=d['state'],**kw)
        def ref(comp,plane):return {'component':comp,'plane_name':plane}
        async def geo(d,comp):return await call('sw_component_geometry',{'document_id':d['document_id'],'component_name':comp})
        def face(g):return next(f['face_id'] for f in g['faces'] if f['kind']=='cylinder' and abs(f['diameter_mm']-10)<1e-5)
        def plane(g,axis):return next(p['plane_name'] for p in g['reference_planes'] if abs(p['normal'][axis])>.99999)
        con=await call('sw_connect',{'start_if_needed':False});prior=con['documents']
        d=await call('sw_new_document',{'kind':'assembly'})
        d=await call('sw_add_component',edit(d,path=str(output/(prefix+'_arm.SLDPRT')),fixed=True));base=d['inserted_component']
        d=await call('sw_add_component',edit(d,path=str(output/(prefix+'_shaft.SLDPRT')),fixed=False));guide=d['inserted_component']
        ga=await geo(d,base);gb=await geo(d,guide)
        d=await call('sw_add_mate',edit(d,mate_type='concentric',reference_a={'component':base,'face_id':face(ga)},reference_b={'component':guide,'face_id':face(gb)},name='bearing_axis'))
        ga=await geo(d,base);gb=await geo(d,guide)
        d=await call('sw_add_mate',edit(d,mate_type='coincident',reference_a=ref(base,plane(ga,2)),reference_b=ref(guide,plane(gb,2)),name='shaft_axial_stop'))
        if not free:
            ga=await geo(d,base);gb=await geo(d,guide)
            d=await call('sw_add_mate',edit(d,mate_type='limit_angle',reference_a=ref(base,plane(ga,0)),reference_b=ref(guide,plane(gb,1)),value=90,minimum=69,maximum=113,name='joint_rotation'))
        d=await call('sw_add_component',edit(d,path=str(output/(prefix+'_arm.SLDPRT')),z_mm=80,fixed=False));carriage=d['inserted_component']
        if free:
            for axis in [0,1]:
                gb=await geo(d,guide);gc=await geo(d,carriage)
                d=await call('sw_add_mate',edit(d,mate_type='coincident',reference_a=ref(guide,plane(gb,axis)),reference_b=ref(carriage,plane(gc,axis)),name='carriage_guide_'+str(axis)))
        else:
            gb=await geo(d,guide);gc=await geo(d,carriage)
            d=await call('sw_add_mate',edit(d,mate_type='concentric',reference_a={'component':guide,'face_id':face(gb)},reference_b={'component':carriage,'face_id':face(gc)},lock_rotation=True,name='keyed_carriage_axis'))
            gb=await geo(d,guide);gc=await geo(d,carriage)
            d=await call('sw_add_mate',edit(d,mate_type='limit_distance',reference_a=ref(guide,plane(gb,2)),reference_b=ref(carriage,plane(gc,2)),value=80,minimum=10,maximum=150,name='carriage_travel'))
        async def pose(d,q,s):
            if free:
                transform=next(c['transform'] for c in d['components'] if c['name']==guide)
                old_q=math.degrees(math.atan2(transform[1],transform[0]))
                d=await call('sw_move_component',edit(d,component_name=guide,axis_world=[0,0,1],angle_deg=q-old_q,pivot_mm=[0,0,0]))
                assert d['request_achieved'],d
                transform=next(c['transform'] for c in d['components'] if c['name']==carriage)
                d=await call('sw_move_component',edit(d,component_name=carriage,translation_mm=[0,0,s-transform[11]*1000]))
                assert d['request_achieved'],d
            else:
                d=await call('sw_set_mate_position',edit(d,mate_name='joint_rotation',value=90+q))
                d=await call('sw_set_mate_position',edit(d,mate_name='carriage_travel',value=s))
            c={c['name']:c for c in d['components']};a=c[guide]['transform'];b=c[carriage]['transform'];z=c[base]['transform']
            error=max(abs(a[i]-b[i]) for i in range(9))
            actual_q=math.degrees(math.atan2(a[1],a[0]));actual_s=1000*(b[11]-a[11])
            assert c[base]['fixed'] and not c[guide]['fixed'] and not c[carriage]['fixed']
            assert error<1e-6 and abs(actual_q-q)<1e-4 and abs(actual_s-s)<1e-4
            assert max(abs(v) for v in a[9:12])<1e-6 and max(abs(v) for v in b[9:11])<1e-6
            assert z==[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]
            poses.append({'requested_angle_deg':q,'actual_angle_deg':actual_q,'requested_slide_mm':s,'actual_slide_mm':actual_s,'carriage_follows_guide_rotation_error':error,'components':c})
            return d
        for q,s in [(-21,10),(23,150),(15,70),(0,80)]:d=await pose(d,q,s)
        interference=await call('sw_check_interference',{'document_id':d['document_id']});assert interference['count']==0
        persisted=lambda rows:{c['name']:{k:v for k,v in c.items() if k!='native_part_update_stamp'} for c in rows}
        d=await call('sw_save',edit(d,path=str(path)));saved_components=persisted(d['components'])
        await call('sw_close',{'document_id':d['document_id']})
        d=await call('sw_open_document',{'path':str(path),'editable':True})
        assert d['configuration'] and persisted(d['components'])==saved_components
        d=await pose(d,15,70)
        d=await call('sw_save',edit(d,path=str(path)))
        await call('sw_close',{'document_id':d['document_id']})
        final=await call('sw_documents');old={(x['title'],x['path']) for x in prior};now={(x['title'],x['path']) for x in final['documents']}
        assert old.issubset(now)
        report={'status':'PASS','assembly_path':str(path),'sha256':d['sha256'],'server':init.serverInfo.name,'tool_count':len(listed.tools),'calls':len(records),'poses':poses,'interference':interference,'saved_reopened_and_driven':True,'original_documents_preserved':True,'scope':'Native connected kinematic acceptance mechanism; not the full exoskeleton, not a force or energy simulation.'}
        report['free_motion']=free;report['has_native_range_limits']=not free
        (output/('自由机构_验证.json' if free else '连接机构_验证.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':'PASS','assembly':str(path),'calls':len(records)},ensure_ascii=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-root',type=Path,required=True);p.add_argument('--temp-root',type=Path,required=True);p.add_argument('--free',action='store_true');a=p.parse_args()
    if not a.temp_root.resolve().is_relative_to(Path(r'E:\simulink\_codex_tmp').resolve()):p.error('Temporary data must be under the designated E drive root')
    asyncio.run(run(a.output_root,a.temp_root,a.free))
