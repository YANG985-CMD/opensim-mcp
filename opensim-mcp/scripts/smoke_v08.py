"""Real MCP project portability, atomic edit/undo/rollback, geometry and new native tools."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(report_path):
    root=Path(__file__).resolve().parents[1];examples=root/'examples';evidence={}
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ))
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize();listing=await session.list_tools();evidence['tool_count']=len(listing.tools)
            assert evidence['tool_count']>=65
            async def call(name,parameters=None,expect_error=False):
                result=await session.call_tool(name,parameters or {})
                if expect_error:assert result.isError,(name,result);return
                assert not result.isError,(name,result)
                return result.structuredContent
            compatibility=await call('check_version_compatibility');assert compatibility['status']=='pass',compatibility
            evidence['compatibility']=compatibility
            status=await call('load_model',{'model_path':str(examples/'slider.osim')});revision=status['revision']
            edits=[dict(component_type='body',component_name='block',property_name='mass',value=2.),
                   dict(component_type='marker',component_name='M2',property_name='location',value=[0.,.2,0.])]
            preview=await call('apply_model_edits',dict(edits=edits,expected_revision=revision))
            assert preview['candidate_mass_kg']==2. and not preview['committed']
            assert (await call('get_api_session'))['revision']==revision
            bad=[edits[0],dict(edits[1],component_name='missing')]
            await call('apply_model_edits',dict(edits=bad,expected_revision=revision,dry_run=False),True)
            assert (await call('get_model_component',dict(component_type='body',component_name='block')))['properties']['mass']==1.
            committed=await call('apply_model_edits',dict(edits=edits,expected_revision=revision,dry_run=False,label='atomic test'))
            assert committed['revision']==revision+1
            assert (await call('list_edit_transactions'))['transactions'][0]['status']=='committed'
            await call('apply_model_edits',dict(edits=edits,expected_revision=revision,dry_run=False),True)
            undo=await call('undo_model_edit',dict(expected_revision=committed['revision']))
            assert undo['total_mass_kg']==1.
            redo=await call('redo_model_edit',dict(expected_revision=undo['revision']));assert redo['total_mass_kg']==2.
            rollback=await call('rollback_edit_transaction',dict(transaction_id=committed['transaction_id'],expected_revision=redo['revision']))
            assert rollback['restore']['api']['total_mass_kg']==1.
            evidence['transaction_preview_failure_atomic_single_undo_durable_rollback']=True
            scene=await call('export_model_scene');assert Path(scene['html_file']).is_file();evidence['scene']=scene
            assert (await call('validate_project',dict(project_path=str(examples/'project.json'))))['valid']
            bundle=await call('export_project_bundle',dict(project_path=str(examples/'project.json')))
            assert (await call('verify_project_bundle',dict(bundle_path=bundle['bundle_file'])))['valid']
            imported=await call('import_project_bundle',dict(bundle_path=bundle['bundle_file']));assert imported['executed'] is False
            submitted=await call('run_project',dict(project_path=imported['project_path']))
            for _ in range(1200):
                job=await call('get_job_status',dict(job_id=submitted['job_id']))
                if job['status'] in {'completed','failed','cancelled'}:break
                await asyncio.sleep(.1)
            assert job['status']=='completed',job
            report=await call('get_project_run',dict(run_id=submitted['job_id']))
            assert Path(report['html_file']).is_file() and report['quality_status']=='configured_checks_passed'
            evidence['imported_project_native_pipeline']=job['result']
            placement=await call('place_model_markers',dict(model_path=str(examples/'slider.osim'),static_marker_path=str(examples/'slider_scale_static.trc'),movable_markers=['M2'],marker_weights={'M1':1.,'M2':1.,'M3':1.},max_marker_movement_m=.11))
            assert abs(placement['quality']['max_marker_shift_m']-.1)<1e-6
            inverse=await call('run_moco_inverse',dict(model_path=str(examples/'moco_slider.osim'),coordinates_path=str(examples/'muscle_slider_static.mot'),initial_time=0.,final_time=1.,no_external_loads=True,mesh_interval=.1))
            assert inverse['quality']['solver_success']
            await call('close_api_session')
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize();result=await session.call_tool('list_edit_transactions',{})
            assert result.structuredContent['transactions'][0]['status']=='rolled_back'
    evidence.update(passed=True,journal_survives_server_restart=True)
    report_path.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps({'passed':True,'tools':evidence['tool_count']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args();asyncio.run(main(args.report))
