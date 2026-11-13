"""Real native/MCP integration checks, with optional GUI checks on synthetic data.

Requires a configured API/CLI backend, API interpreter and ENABLE_SCRIPTS=1. GUI
checks require an active bridge (startup plugin or manual bootstrap). All input models
are originals shipped with this repository, not participant data.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(examples:Path,with_gui:bool):
    params=StdioServerParameters(command=sys.executable,args=["-B","-m","opensim_mcp.server"],env=dict(os.environ))
    original=hashlib.sha256((examples/"slider.osim").read_bytes()).hexdigest()
    report={"native":True,"gui_requested":with_gui}
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            tools=await session.list_tools()
            report["tools"]=sorted(tool.name for tool in tools.tools)
            assert len(report["tools"])>=47
            async def call(name,args=None,expect_error=False):
                value=await session.call_tool(name,args or {})
                if expect_error:
                    assert value.isError,(name,value)
                    return
                if value.isError:raise RuntimeError(name+": "+value.model_dump_json())
                assert isinstance(value.structuredContent,dict)
                return value.structuredContent
            report["environment"]=await call("get_environment")
            status=await call("get_api_session")
            report["api_version"]=status["opensim_version"]
            report["api_python"]=status["python"]
            await call("load_model",{"model_path":str(examples/"slider.osim")})
            changed=await call("set_model_parameter",{"component_type":"body","component_name":"block","property_name":"mass","value":2.5})
            assert changed["after"]["mass"]==2.5
            await call("set_model_parameter",{"component_type":"body","component_name":"block","property_name":"mass","value":-1},True)
            component=await call("get_model_component",{"component_type":"body","component_name":"block"})
            assert component["properties"]["mass"]==2.5
            first=await call("evaluate_opensim_code",{"code":"counter=41; print('capture-check'); result=model.getName()"})
            second=await call("evaluate_opensim_code",{"code":"result=counter+1"})
            assert first["stdout"].strip()=="capture-check" and second["result"]==42
            scripted=await call("run_opensim_script",{"script_path":str(examples/"session_demo.py")})
            assert scripted["result"]["coordinates"]==1
            failed=await call("evaluate_opensim_code",{"code":"print('before-failure'); raise ValueError('intentional script test')"})
            assert failed["status"]=="failed" and "intentional script test" in failed["error"] and "before-failure" in failed["stdout"]
            saved=await call("save_model")
            assert Path(saved["model_file"]).is_file()
            report["api"]={"persistent_variable":second["result"],"edited_mass_kg":component["properties"]["mass"],
                           "invalid_edit_rejected":True,"script_output_and_exception_captured":True}
            ik=await call("run_inverse_kinematics",{"model_path":str(examples/"slider.osim"),"marker_path":str(examples/"slider.trc")})
            report["ik_rows"]=ik["rows"]
            model=str(examples/"muscle_slider.osim");motion=str(examples/"muscle_slider_static.mot")
            loads=json.loads((examples/"external_forces.json").read_text())
            report["analyses"]={}
            for tool in ("run_inverse_dynamics","run_static_optimization"):
                for assisted in (False,True):
                    args={"model_path":model,"coordinates_path":motion}
                    if assisted:args.update(loads_path=str(examples/"muscle_slider_loads.sto"),external_forces=loads)
                    else:args["no_external_loads"]=True
                    result=await call(tool,args)
                    force=next(path for path in result["files"] if (path.endswith("inverse_dynamics.sto") or path.endswith("_force.sto")))
                    summary=await call("read_motion_result",{"result_path":force,"preview_rows":0})
                    label="slider_tx_force" if tool=="run_inverse_dynamics" else "puller"
                    expected=15 if assisted else 20
                    assert summary["row_count"]==11
                    assert max(abs(summary["ranges"][label][key]-expected) for key in ("min","max"))<1e-6
                    report["analyses"][tool+("_assisted" if assisted else "_unassisted")]=expected
            geometry=await call("run_muscle_analysis",{"model_path":model,"coordinates_path":motion})
            for suffix in ("_Length.sto","_MomentArm_slider_tx.sto"):
                path=next(path for path in geometry["files"] if path.endswith(suffix))
                summary=await call("read_motion_result",{"result_path":path,"preview_rows":0})
                assert abs(summary["ranges"]["puller"]["min"]-1)<1e-8 and abs(summary["ranges"]["puller"]["max"]-1)<1e-8
            report["analyses"]["muscle_path_length_m"]=1
            report["analyses"]["muscle_moment_arm_translation"]=1
            if with_gui:
                connected=await call("connect_gui")
                assert connected["connected"],connected
                await call("open_model_in_gui",{"model_path":str(examples/"slider.osim")})
                await call("load_motion_in_gui",{"motion_path":ik["motion_file"]})
                await call("set_gui_coordinate",{"coordinate_name":"slider_tx","value":.04})
                pulled=await call("sync_gui_model",{"direction":"pull"})
                assert abs(pulled["api"]["coordinate_values"]["slider_tx"]-.04)<1e-10
                edited=await call("set_model_parameter",{"component_type":"body","component_name":"block","property_name":"mass","value":3.0,"sync_gui":True})
                assert edited["gui_synchronized"],edited
                gui_before=await call("get_current_model")
                report["gui_version"]=gui_before.get("opensim_version")
                report["gui_process"]=gui_before.get("gui_process")
                assert abs(gui_before["coordinate_values"]["slider_tx"]-.04)<1e-10
                await call("set_gui_coordinate",{"coordinate_name":"slider_tx","value":.03,"expected_signature":gui_before["signature"]})
                await call("set_gui_coordinate",{"coordinate_name":"slider_tx","value":.02,"expected_signature":gui_before["signature"]},True)
                pulled_again=await call("sync_gui_model",{"direction":"pull"})
                component=await call("get_model_component",{"component_type":"body","component_name":"block"})
                assert component["properties"]["mass"]==3.0
                assert abs(pulled_again["api"]["coordinate_values"]["slider_tx"]-.03)<1e-10
                report["gui"]={"connected":True,"roundtrip_mass_kg":3,"roundtrip_pose_m":.03,"stale_write_rejected":True,
                               "sync_mode":"new_active_model_version"}
            await call("evaluate_opensim_code",{"code":"import time; time.sleep(10)","timeout_seconds":1},True)
            reset=await call("get_api_session")
            assert reset["model_loaded"] is False
            report["api"]["timeout_restarts_empty_session"]=True
            await call("close_api_session")
    assert hashlib.sha256((examples/"slider.osim").read_bytes()).hexdigest()==original
    report["source_unchanged"]=True
    report["passed"]=True
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples",type=Path,required=True)
    parser.add_argument("--gui",action="store_true")
    args=parser.parse_args()
    asyncio.run(main(args.examples.resolve(),args.gui))
