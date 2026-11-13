"""Actual stdio, native scene and portable numeric exchange; no MATLAB/SW license required."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from opensim_mcp import __version__

async def main(report):
    root=Path(__file__).resolve().parents[1]
    examples=Path(os.environ.get('OPENSIM_V13_EXAMPLES',str(root/'examples')))
    folder=Path(os.environ['OPENSIM_MCP_RESULTS_ROOT'])/'v13-inputs';folder.mkdir(parents=True,exist_ok=True)
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ,OPENSIM_MCP_ENABLE_SCRIPTS='0'))
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize();names={t.name for t in (await client.list_tools()).tools}
            assert {'attach_visualization_signals','inspect_visualization_workspace'}<=names
            async def call(name,args=None):
                response=await client.call_tool(name,args or {});assert not response.isError,(name,response)
                return response.structuredContent
            env=await call('get_environment');assert env['adapter_version']==__version__ and not env['scripting_enabled']
            await call('load_model',dict(model_path=str(examples/'lower_limb_demo.osim')))
            animated=await call('export_model_animation',dict(motion_path=str(examples/'lower_limb_demo.mot'),geometry_model_path=str(examples/'lower_limb_demo.osim'),max_frames=31))
            scene=json.loads(Path(animated['scene_file']).read_text(encoding='utf-8'));frames=scene['frames'];csv=folder/'signals.csv'
            csv.write_text('time_s,reference,state\n'+'\n'.join(f'{f["time"]:.17g},{f["coordinate_values"]["knee_angle_r"]:.17g},{int(i>=15)}' for i,f in enumerate(frames))+'\n',encoding='utf-8')
            source=dict(schema='opensim_signal_source_v1',path=str(csv),label='Original synthetic test data',time_column='time_s',time_unit='s',time_offset_s=0.,interpolation='none',max_gap_s=1.,model_physics_signature=scene['physics_signature'],channels=[dict(column='reference',label='Reference angle',unit='rad',component=dict(kind='coordinate',name='knee_angle_r')),dict(column='state',label='Gate',unit='1',component=dict(kind='body',name='/bodyset/tibia_r'))])
            bound=await call('attach_visualization_signals',dict(scene_path=animated['scene_file'],signal_sources=[source]))
            checked=await call('inspect_visualization_workspace',dict(project_path=bound['project_file']));assert checked['verified']
            data=json.loads(Path(bound['scene_file']).read_text(encoding='utf-8'))
            assert data['external_signals'][0]['frame_values']==data['external_signals'][0]['values']
            assert checked['signal_provenance'][0]['model_identity']=='matched_physics_signature'
            Path(bound['html_file']).write_text('tampered',encoding='utf-8')
            rejected=await client.call_tool('inspect_visualization_workspace',dict(project_path=bound['project_file']));assert rejected.isError
            # Re-create an intact example after the deliberate corruption test.
            bound=await call('attach_visualization_signals',dict(scene_path=animated['scene_file'],signal_sources=[source]))
            result=dict(passed=True,version=__version__,tool_count=len(names),scripts_enabled=False,native_scene_frames=len(frames),native_scene_meshes=len(scene['meshes']),all_v13_tools_called=True,exact_sample_roundtrip=True,hash_tamper_rejected=True,workspace=bound)
    report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    asyncio.run(asyncio.wait_for(main(args.report),timeout=180))
