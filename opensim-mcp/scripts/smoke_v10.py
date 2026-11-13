"""Real MCP v1.0 features with arbitrary scripting disabled, including server restart."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from opensim_mcp import __version__

async def main(report):
    root=Path(__file__).resolve().parents[1]/'examples';evidence={};fixture=Path(os.environ['OPENSIM_MCP_RESULTS_ROOT'])/'v10-inputs';fixture.mkdir(parents=True,exist_ok=True)
    motion=fixture/'motion.mot';motion.write_text('v1 structured viewer\nversion=1\nnRows=11\nnColumns=3\ninDegrees=no\nendheader\ntime slider_tx extension_tx\n'+'\n'.join(f'{i/10:.12g} {i/100:.12g} {i/200:.12g}' for i in range(11))+'\n',encoding='utf-8')
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ,OPENSIM_MCP_ENABLE_SCRIPTS='0'))
    snapshot=None
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize();tools=await session.list_tools();names={t.name for t in tools.tools};evidence['tool_count']=len(names)
            assert {'edit_model_topology','get_model_state','get_recovery_status','recover_api_session','ensure_gui_connection','reconfigure_gui_bridge','export_model_animation'}<=names
            async def call(name,parameters=None):
                response=await session.call_tool(name,parameters or {});assert not response.isError,(name,response);return response.structuredContent
            env=await call('get_environment');assert env['adapter_version']==__version__ and not env['scripting_enabled']
            loaded=await call('load_model',dict(model_path=str(root/'muscle_slider_dynamic.osim')))
            state=await call('get_model_state');assert any(s['path'].endswith('/activation') for s in state['states'])
            operations=[dict(op='add_body',name='extension',mass=1.,mass_center=[0.,0.,0.],inertia=[.01,.01,.01,0.,0.,0.],geometry={'type':'sphere','radius':.06}),
                dict(op='add_joint',name='extension_slide',joint_type='SliderJoint',parent_frame='/bodyset/block',child_body='extension',location_in_parent=[0.,.2,0.],coordinate={'name':'extension_tx','range':[-.5,.5],'default_value':0.})]
            preview=await call('edit_model_topology',dict(operations=operations,expected_revision=loaded['revision']));assert not preview['committed']
            committed=await call('edit_model_topology',dict(operations=operations,expected_revision=loaded['revision'],dry_run=False));assert committed['api']['counts']['bodies']==2
            scene=await call('export_model_animation',dict(motion_path=str(motion),max_frames=11));assert scene['mesh_count']==1 and Path(scene['html_file']).is_file();evidence['viewer']=scene
            undone=await call('undo_model_edit',dict(expected_revision=committed['revision']));assert undone['counts']['bodies']==1
            redo=await call('redo_model_edit',dict(expected_revision=undone['revision']));assert redo['counts']['bodies']==2
            rollback=await call('rollback_edit_transaction',dict(transaction_id=committed['transaction_id'],expected_revision=redo['revision']));assert rollback['restore']['api']['counts']['bodies']==1
            recovery=await call('get_recovery_status');snapshot=recovery['current_owner_latest'];assert snapshot
            connection=await call('ensure_gui_connection',dict(launch_if_closed=False,wait_seconds=0));evidence['gui_observed_without_launch_or_model_write']=not connection['launched']
            await call('close_api_session')
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize();restored=await session.call_tool('recover_api_session',dict(snapshot_id=snapshot));assert not restored.isError
            assert restored.structuredContent['api']['counts']['bodies']==1
            denied=await session.call_tool('recover_api_session',dict(snapshot_id=snapshot));assert denied.isError
            await session.call_tool('close_api_session',{})
    evidence.update(passed=True,version=__version__,new_tools_work_with_arbitrary_scripts_disabled=True,full_state_recovery_after_mcp_restart=True,topology_preview_commit_undo_rollback=True)
    report.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,version=__version__,tools=evidence['tool_count'],scripts_enabled=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args();asyncio.run(asyncio.wait_for(main(a.report),timeout=240))
