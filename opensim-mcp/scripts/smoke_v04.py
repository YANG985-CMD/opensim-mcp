"""Real stdio/native v0.4 regression; optional GUI writes on synthetic fixtures.

Requires wheel/API mode and scripting enabled. Use dedicated test temp/results.
All returned images are decoded and verified; base64 is never printed.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import sys
import time

from PIL import Image
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from opensim_mcp.process_tree import process_alive


async def main(examples,report_path,with_gui):
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ))
    report={'native':True,'gui_requested':with_gui}
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize();tools=await session.list_tools()
            report['tool_count']=len(tools.tools);assert report['tool_count']>=47
            async def call(name,args=None,error=False,media=False):
                print('Checking '+name,file=sys.stderr,flush=True)
                value=await session.call_tool(name,args or {})
                if error:
                    assert value.isError,(name,value);return
                assert not value.isError,(name,value)
                if media:
                    pictures=[c for c in value.content if c.type=='image'];assert pictures
                    for content in pictures:
                        with Image.open(io.BytesIO(base64.b64decode(content.data))) as image:
                            assert image.width>10 and image.height>10;image.verify()
                    metadata=[json.loads(c.text) for c in value.content if c.type=='text']
                    return {'image_count':len(pictures),'metadata':metadata}
                assert isinstance(value.structuredContent,dict),(name,value)
                return value.structuredContent
            report['environment']=await call('get_environment')
            await call('load_model',{'model_path':str(examples/'slider.osim')})
            docs=await call('get_api_documentation',{'symbol':'Model.scale'})
            assert docs['doc']
            components=await call('list_model_components',{'class_name':'Body'})
            assert any(c['path']=='/bodyset/block' for c in components['components'])
            details=await call('get_component_details',{'component_path':'/bodyset/block'})
            assert any(p['name']=='mass' for p in details['properties'])
            syntax=await call('check_opensim_code',{'code':'x=1\nif :\n pass','filename':'study.py'})
            assert not syntax['valid_syntax'] and syntax['diagnostics'][0]['line']==2
            unknown=await call('check_opensim_code',{'code':'result=osim.NotARealOpenSimType()'})
            assert unknown['diagnostics'][0]['kind']=='unknown_api_symbol'
            located=await call('evaluate_opensim_code',{'code':"a=1\nb=2\nraise ValueError('located')"})
            assert located['diagnostics'][0]['line']==3 and located['diagnostics'][0]['source_line'].startswith('raise ')
            point=await call('create_checkpoint',{'label':'baseline'})
            change=await call('set_model_parameter',dict(component_type='body',component_name='block',property_name='mass',value=2.5))
            await call('undo_model_edit',{'expected_revision':change['revision']+1},error=True)
            await call('undo_model_edit',{'expected_revision':change['revision']})
            assert (await call('get_model_component',dict(component_type='body',component_name='block')))['properties']['mass']==1
            await call('redo_model_edit')
            assert (await call('get_model_component',dict(component_type='body',component_name='block')))['properties']['mass']==2.5
            await call('restore_checkpoint',{'checkpoint_id':point['checkpoint_id']})
            assert (await call('get_model_component',dict(component_type='body',component_name='block')))['properties']['mass']==1
            report['discovery_diagnostics_undo_checkpoints']=True
            report['pose_image']=await call('render_model',media=True)
            ik=await call('run_inverse_kinematics',{'model_path':str(examples/'slider.osim'),'marker_path':str(examples/'slider.trc')})
            report['curve']=await call('plot_motion_result',{'result_path':ik['motion_file'],'columns':['slider_tx'],'ylabel':'Translation (m)'},media=True)
            image=report['curve']['metadata'][0]['image_file']
            await call('read_image',{'image_path':image},media=True)
            fit=await call('assess_ik_quality',{'model_path':str(examples/'slider.osim'),'coordinates_path':ik['motion_file'],
                                             'marker_path':str(examples/'slider.trc'),'rms_threshold_m':1e-6})
            assert fit['quality']['threshold_passed'];report['ik_marker_quality']=fit['quality']
            scaling=await call('scale_model',{'model_path':str(examples/'slider.osim'),'subject_mass_kg':2,
                'static_marker_path':str(examples/'slider_scale_static.trc'),
                'measurements':[{'body':'block','axes':['y'],'marker_pairs':[['M1','M2']]}],'max_measurement_error_m':1e-6})
            assert scaling['body_scales']['block']==[1,2,1] and scaling['quality']['mass_error_kg']==0
            report['scale']=scaling['quality']
            reaction=await call('run_joint_reaction',{'model_path':str(examples/'joint_slider.osim'),
                'coordinates_path':str(examples/'muscle_slider_static.mot'),'no_external_loads':True})
            assert abs(reaction['joint_reaction_quality']['slider']['peak_resultant_f_N']-20)<1e-6
            report['joint_reaction']=reaction['joint_reaction_quality']
            so=await call('run_static_optimization',{'model_path':str(examples/'muscle_slider.osim'),
                'coordinates_path':str(examples/'muscle_slider_static.mot'),'no_external_loads':True})
            force_path=next(p for p in so['files'] if p.endswith('_force.sto'))
            driven=await call('run_joint_reaction',{'model_path':str(examples/'muscle_slider.osim'),
                'coordinates_path':str(examples/'muscle_slider_static.mot'),'no_external_loads':True,'forces_path':force_path})
            assert driven['actuator_force_source']=='force_table';report['so_to_joint_reaction_pipeline']=True
            problem=json.loads((examples/'moco_problem.json').read_text())
            moco=await call('run_moco',dict(problem,model_path=str(examples/'moco_slider.osim')))
            assert abs(moco['quality']['objective']-48)<.01;report['moco']=moco['quality']
            submitted=await call('submit_analysis',{'workflow':'ik','parameters':{
                'model_path':str(examples/'slider.osim'),'marker_path':str(examples/'slider.trc')}})
            identifier=submitted['job_id'];deadline=time.monotonic()+30
            while True:
                status=await call('get_job_status',{'job_id':identifier})
                if status['status'] in {'completed','failed','cancelled'}:break
                assert time.monotonic()<deadline;await asyncio.sleep(.1)
            assert status['status']=='completed',status
            assert Path(status['result']['motion_file']).is_file()
            assert '/artifacts/' in status['result']['motion_file'].replace('\\','/')
            report['async_completed']=True
            submitted=await call('submit_analysis',{'workflow':'moco','parameters':dict(problem,model_path=str(examples/'moco_slider.osim'),mesh_intervals=200,refine_mesh=True)})
            deadline=time.monotonic()+30;native_pid=None
            while time.monotonic()<deadline:
                status=await call('get_job_status',{'job_id':submitted['job_id']})
                native_pid=status.get('progress',{}).get('native_pid')
                if native_pid and process_alive(native_pid):break
                assert status['status'] not in {'completed','failed'},status
                await asyncio.sleep(.02)
            assert native_pid
            cancelled=await call('cancel_job',{'job_id':submitted['job_id']})
            assert cancelled['cancelled'] and cancelled['process_tree_stopped'],cancelled
            assert not process_alive(native_pid)
            status=await call('get_job_status',{'job_id':submitted['job_id']})
            assert 'result' not in status
            report['async_native_cancel_confirmed']=True
            assert (await call('list_jobs'))['jobs']
            report['history_job_id']=identifier
            if with_gui:
                attached=await call('connect_gui');assert attached['connected']
                assert attached['gui']['bridge_version'] in {'0.4.0','1.0.0','1.1.0'}
                await call('open_model_in_gui',{'model_path':str(examples/'slider.osim')})
                chosen=await call('select_gui_component',{'component_path':'/bodyset/block'})
                assert any(x.get('object_name')=='block' for x in chosen['selection']),chosen
                current=await call('get_gui_selection');assert current['selection']
                await call('set_gui_coordinate',{'coordinate_name':'slider_tx','value':.04})
                pose=await call('undo_gui_pose');assert abs(pose['coordinate_values']['slider_tx'])<1e-9
                report['gui_image']=await call('capture_gui_image',media=True)
                report['gui']={'version':attached['gui']['opensim_version'],'bridge_version':attached['gui']['bridge_version'],
                               'selection_read_back':True,'pose_undo_verified':True,'image_returned':True}
            await call('close_api_session')
    # New MCP process reads history from the same result root.
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            result=await session.call_tool('get_job_status',{'job_id':report['history_job_id']})
            assert not result.isError and result.structuredContent['status']=='completed'
            report['history_survives_mcp_restart']=True
    report.update(passed=True)
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'tools':report['tool_count'],'async_cancel':True,'history_restart':True,'gui_tested':with_gui}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--examples',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--gui',action='store_true');args=parser.parse_args()
    asyncio.run(main(args.examples.resolve(),args.report.resolve(),args.gui))
