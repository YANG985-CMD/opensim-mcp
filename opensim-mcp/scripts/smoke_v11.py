"""Real stdio integration for all seven v1.1 tools, scripts disabled."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from opensim_mcp import __version__

async def main(report):
    examples=Path(__file__).resolve().parents[1]/'examples';fixture=Path(os.environ['OPENSIM_MCP_RESULTS_ROOT'])/'v11-inputs';fixture.mkdir(parents=True,exist_ok=True)
    motion=fixture/'motion.mot';motion.write_text('Quadratic\nversion=1\nnRows=41\nnColumns=2\ninDegrees=no\nendheader\ntime slider_tx\n'+'\n'.join(f'{i/40:.15g} {.5*(i/40)**2:.15g}' for i in range(41))+'\n')
    assist=fixture/'assist.sto';assist.write_text('Assist\nversion=1\nnRows=41\nnColumns=2\ninDegrees=no\nendheader\ntime force\n'+'\n'.join(f'{i/40:.15g} .25' for i in range(41))+'\n')
    events=fixture/'events.mot';events.write_text('Events\nversion=1\nnRows=11\nnColumns=2\ninDegrees=no\nendheader\ntime up\n'+'\n'.join(f'{i/10} {v}' for i,v in enumerate([100,100,0,0,100,100,100,0,0,100,100]))+'\n')
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ,OPENSIM_MCP_ENABLE_SCRIPTS='0'))
    result={}
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize();names={t.name for t in (await session.list_tools()).tools}
            required={'assemble_wearable_model','prepare_wearable_motion','compare_wearable_inverse_dynamics','resample_coordinate_motion','inspect_gait_cycles','assess_moco_mesh_study','audit_moco_trajectory'}
            assert required<=names
            async def call(name,args=None):
                response=await session.call_tool(name,args or {});assert not response.isError,(name,response);return response.structuredContent
            env=await call('get_environment');assert env['adapter_version']==__version__ and not env['scripting_enabled']
            cycles=await call('inspect_gait_cycles',dict(loads_path=str(events),vertical_force_column='up'));assert cycles['cycles'][0]['start_time']==.4
            sampled=await call('resample_coordinate_motion',dict(coordinates_path=str(motion),frequency_hz=20.));assert sampled['output_rows']==21
            link=dict(name='cuff',parent_frame='/bodyset/block',mesh_path=str(examples/'Geometry/block.obj'),mesh_units='m',mass_kg=.5,mass_center_m=[0.,0.,0.],inertia_kg_m2=[.001,.001,.001,0.,0.,0.],joint_type='WeldJoint')
            assembly=await call('assemble_wearable_model',dict(model_path=str(examples/'slider.osim'),links=[link]));assert abs(assembly['quality']['added_device_mass_kg']-.5)<1e-10
            adapted=await call('prepare_wearable_motion',dict(assembly_report_path=assembly['report_file'],coordinates_path=str(motion)))
            comparison=await call('compare_wearable_inverse_dynamics',dict(baseline_model_path=str(examples/'slider.osim'),assembly_report_path=assembly['report_file'],coordinates_path=adapted['motion_file'],no_external_loads=True,
                assistance_path=str(assist),assistance_mapping=[dict(coordinate='slider_tx',column='force',unit='N')]))
            assert abs(comparison['metrics']['slider_tx_force']['remaining_generalized_demand']['rms']-1.25)<1e-5
            study=await call('run_moco_convergence',dict(profile='moco_inverse',parameters=dict(model_path=str(examples/'muscle_slider.osim'),coordinates_path=str(examples/'muscle_slider_static.mot'),initial_time=0.,final_time=1.,no_external_loads=True,ignore_tendon_compliance=True),mesh_interval_values_s=[.1,.05]))
            limits=study['comparisons'][-1];quality=await call('assess_moco_mesh_study',dict(study_report_path=study['report_file'],state_rms_limits={n:1e-4 for n in limits['states']},control_rms_limits={n:1e-4 for n in limits['controls']}))
            assert quality['status']=='configured_checks_passed'
            run=study['runs'][-1]['result'];files={Path(f).name:f for f in run['files']}
            audit=await call('audit_moco_trajectory',dict(model_path=str(examples/'muscle_slider.osim'),coordinates_path=str(examples/'muscle_slider_static.mot'),states_path=files['states.sto'],controls_path=files['controls.sto'],no_external_loads=True,ignore_tendon_compliance=True))
            assert abs(audit['quality']['actuator_output']['/forceset/puller']['rms']-20.)<1e-4
            result.update(passed=True,version=__version__,tool_count=len(names),scripts_enabled=False,all_v11_tools_called=True,analytic_remaining_demand_N=1.25,
                synthetic_all_state_control_mesh_checks=True,native_muscle_force_N=audit['quality']['actuator_output']['/forceset/puller']['rms'])
    report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args();asyncio.run(asyncio.wait_for(main(a.report),timeout=240))
