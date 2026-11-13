"""Real MCP native two-scene workbench, strict saved state and integrity regression."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from opensim_mcp import __version__

async def main(report):
    root=Path(os.environ.get('OPENSIM_V14_EXAMPLES',str(Path(__file__).resolve().parents[1]/'examples')))
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ,OPENSIM_MCP_ENABLE_SCRIPTS='0'))
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as client:
            await client.initialize();tools={t.name for t in (await client.list_tools()).tools};assert 'create_visualization_workbench' in tools
            async def call(name,args):
                response=await client.call_tool(name,args);assert not response.isError,(name,response);return response.structuredContent
            await call('load_model',dict(model_path=str(root/'lower_limb_demo.osim')))
            native=await call('export_model_animation',dict(motion_path=str(root/'lower_limb_demo.mot'),geometry_model_path=str(root/'lower_limb_demo.osim'),max_frames=31))
            scenes=[dict(path=native['scene_file'],label=label,time_offset_s=0.) for label in ('Reference','Repeat')]
            wb=await call('create_visualization_workbench',dict(scenes=scenes,max_time_delta_s=0.));assert wb['matched_frames']==[31,31]
            checked=await call('inspect_visualization_workspace',dict(project_path=wb['project_file']));assert checked['verified']
            view=dict(schema='opensim_view_state_v1',workbench_id=wb['workbench_id'],frame=7,camera=dict(yaw=1.,pitch=.3,zoom=3.),selected=dict(scene=0,component=dict(kind='body',name='/bodyset/tibia_r')),hidden=[[],[]],opacity=.7,layers=dict(surfaces=True,muscles=True,markers=False,skeleton=False),curve='coordinate:knee_angle_r',measurement=dict(scene=0,points=[dict(kind='frame',name='/ground'),dict(kind='frame',name='/bodyset/tibia_r')]),note='MCP saved state regression')
            state=Path(wb['project_file']).parent/'saved-view.json';state.write_text(json.dumps(view),encoding='utf-8')
            restored=await call('create_visualization_workbench',dict(scenes=scenes,max_time_delta_s=0.,view_state_path=str(state)));assert restored['workbench_id']==wb['workbench_id']
            view['workbench_id']='stale';state.write_text(json.dumps(view),encoding='utf-8')
            rejected=await client.call_tool('create_visualization_workbench',dict(scenes=scenes,max_time_delta_s=0.,view_state_path=str(state)));assert rejected.isError
            Path(wb['html_file']).write_text('tampered',encoding='utf-8')
            corrupt=await client.call_tool('inspect_visualization_workspace',dict(project_path=wb['project_file']));assert corrupt.isError
    result=dict(passed=True,version=__version__,tool_count=len(tools),native_frames=31,two_scene_exact_time_matching=True,saved_state_accepted=True,stale_state_rejected=True,tamper_rejected=True,scripting_enabled=False)
    report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args();asyncio.run(asyncio.wait_for(main(a.report),timeout=180))
