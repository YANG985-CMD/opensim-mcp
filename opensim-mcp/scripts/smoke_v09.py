"""Real MCP C3D/force-plate/native IK-ID, full muscle pipeline and RRA integration."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from opensim_mcp.core import read_motion

async def main(report):
    root=Path(__file__).resolve().parents[1]/'examples';evidence={}
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ))
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as client:
            await client.initialize();listing=await client.list_tools();assert len(listing.tools)>=73;evidence['tool_count']=len(listing.tools)
            async def call(name,parameters=None):
                response=await client.call_tool(name,parameters or {});assert not response.isError,(name,response);return response.structuredContent
            data=await call('import_c3d_trial',dict(c3d_path=str(root/'slider_forceplate.c3d'),source_to_opensim_rotation=[[1.,0.,0.],[0.,0.,1.],[0.,-1.,0.]],
                plate_mappings=[dict(plate_index=0,name='right',body='block')],force_sign=-1.))
            trial=await call('validate_trial_inputs',dict(model_path=str(root/'slider.osim'),marker_path=data['marker_path'],loads_path=data['loads_path'],external_forces=data['external_forces'],force_units={'force':'N','point':'m','torque':'Nm'}));assert trial['valid']
            ik=await call('run_inverse_kinematics',dict(model_path=str(root/'slider.osim'),marker_path=data['marker_path']))
            motion=read_motion(Path(ik['motion_file']));idx=motion['columns'].index('slider_tx');error=max(abs(row[idx]-.1*row[0]) for row in motion['rows']);assert error<1e-6
            inverse=await call('run_inverse_dynamics',dict(model_path=str(root/'slider.osim'),coordinates_path=ik['motion_file'],loads_path=data['loads_path'],external_forces=data['external_forces']))
            table=read_motion(Path(next(f for f in inverse['files'] if f.endswith('inverse_dynamics.sto'))));i=table['columns'].index('slider_tx_force');assert max(abs(row[i]+5.) for row in table['rows'])<1e-4
            evidence['c3d_to_ik_id']={'ik_analytic_max_error_m':error,'expected_force_N':-5.,'rows':len(table['rows']),'explicit_rotation_sign_and_platform_mapping':True}
            project=await call('create_biomechanics_project',dict(name='Complete synthetic muscle pipeline',model_path=str(root/'muscle_slider_markers.osim'),static_marker_path=str(root/'slider_scale_static.trc'),movement_marker_path=str(root/'slider_scale_static.trc'),
                subject_mass_kg=2.,body_scales={'block':[1.,1.,1.]},movable_markers=['M2'],marker_weights={'M1':1.,'M2':1.,'M3':1.},lowpass_cutoff_hz=2.,no_external_loads=True,max_marker_movement_m=.11,quality_limits={'marker_rms_m':1e-5}))
            assert (await call('validate_project',dict(project_path=project['project_path'])))['valid']
            job=await call('run_project',dict(project_path=project['project_path']))
            for _ in range(2400):
                status=await call('get_job_status',dict(job_id=job['job_id']))
                if status['status'] in {'completed','failed','cancelled'}:break
                await asyncio.sleep(.1)
            assert status['status']=='completed',status;evidence['eight_stage_muscle_pipeline']=status['result']
            residual=await call('run_residual_reduction',dict(model_path=str(root/'slider.osim'),coordinates_path=ik['motion_file'],actuators=[dict(name='FX',coordinate='slider_tx',role='residual',unit='N',optimal_force=1.,min_control=-1000.,max_control=1000.)],task_weights={'slider_tx':1.},no_external_loads=True,lowpass_cutoff_hz=2.))
            assert residual['quality']['native_completed'] and residual['quality']['coordinate_fit']['slider_tx']['max_abs']<1e-5;evidence['rra']=residual
    evidence['passed']=True;report.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,tools=evidence['tool_count'],c3d_native_ik_id=True,full_muscle_pipeline=True,rra=True)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args();asyncio.run(main(a.report))
