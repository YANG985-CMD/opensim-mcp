import json
from pathlib import Path

import pytest

from opensim_mcp import analysis
from opensim_mcp.core import InputError, Settings
from opensim_mcp.gui import GuiBridge
from opensim_mcp.session import ApiSession

EXAMPLES=Path(__file__).resolve().parents[1]/"examples"


@pytest.fixture
def cfg(tmp_path):
    temp=tmp_path/"scratch";temp.mkdir()
    return Settings((EXAMPLES,),tmp_path/"results",temp,None,5)


@pytest.mark.parametrize("kwargs",[
    {}, {"no_external_loads":"true"}, {"no_external_loads":True,"start_time":.05},
    {"no_external_loads":True,"end_time":10}, {"no_external_loads":True,"lowpass_cutoff_hz":5},
    {"no_external_loads":True,"lowpass_cutoff_hz":-1},
    {"external_forces":[{"name":"missing_data"}]},
    {"loads_path":str(EXAMPLES/"muscle_slider_loads.sto"),"no_external_loads":True},
    {"loads_path":str(EXAMPLES/"muscle_slider_loads.sto"),"external_forces":[{"name":"bad"}]},
    {"loads_path":str(EXAMPLES/"muscle_slider_loads.sto"),"external_forces":[{"name":"bad","applied_to_body":"missing","force_identifier":"assist_v","point_identifier":"assist_p"}]},
])
def test_analysis_rejects_before_native(cfg,monkeypatch,kwargs):
    monkeypatch.setattr(analysis,"execute",lambda *a,**k:pytest.fail("invalid input reached native execution"))
    with pytest.raises(InputError):
        analysis.run_analysis(cfg,"id",str(EXAMPLES/"muscle_slider.osim"),str(EXAMPLES/"muscle_slider_static.mot"),**kwargs)
    assert not cfg.results_root.exists()


def test_external_load_column_validation():
    from opensim_mcp.core import read_motion,xml_model
    _,model=xml_model((EXAMPLES/"muscle_slider.osim").read_bytes())
    table=read_motion(EXAMPLES/"muscle_slider_loads.sto")
    forces=json.loads((EXAMPLES/"external_forces.json").read_text())
    assert analysis.validate_loads(model,table,forces)[0]["force_identifier"]=="assist_v"
    forces[0]["force_identifier"]="missing"
    with pytest.raises(InputError):analysis.validate_loads(model,table,forces)


def test_api_unconfigured_and_scripting_disabled(cfg,monkeypatch):
    monkeypatch.delenv("OPENSIM_MCP_API_PYTHON",raising=False)
    monkeypatch.delenv("OPENSIM_MCP_ENABLE_SCRIPTS",raising=False)
    api=ApiSession(cfg)
    with pytest.raises(InputError,match="API_PYTHON"):api.call("status")
    with pytest.raises(InputError,match="disabled"):api.evaluate("result=1")
    assert api.process is None


def test_gui_requires_real_heartbeat_and_blocks_outside_paths(cfg,tmp_path):
    gui=GuiBridge(cfg)
    setup=gui.prepare()
    assert setup["connected"] is False
    assert Path(setup["bootstrap_script"]).is_file()
    with pytest.raises(InputError,match="not connected"):gui.call("status")
    with pytest.raises(InputError):gui.input(str(tmp_path/"outside.osim"),".osim")


def test_gui_configuration_change_is_explicit(cfg):
    gui=GuiBridge(cfg);gui.prepare()
    other=Settings(cfg.allowed_roots,cfg.results_root/"different",cfg.temp_root,None)
    with pytest.raises(InputError,match="roots changed"):GuiBridge(other).prepare()


def test_gui_bootstrap_preserves_unicode_paths_for_jython(cfg,tmp_path):
    import ast
    unicode_cfg=Settings(cfg.allowed_roots,cfg.results_root,tmp_path/"中文临时目录",None)
    bootstrap=Path(GuiBridge(unicode_cfg).prepare()["bootstrap_script"])
    source=bootstrap.read_text(encoding="ascii")
    assignment=ast.parse(source).body[0]
    assert assignment.value.value==str(bootstrap.parent/"bridge_config.json")
    assert assignment.value.kind=="u"


def test_gui_heartbeat_identity_and_expiry(cfg):
    import time
    gui=GuiBridge(cfg)
    setup=gui.prepare()
    heartbeat=gui.folder/"heartbeat.json"
    heartbeat.write_text(json.dumps({"bridge_id":"other","time":time.time()}))
    assert not gui.connected()
    heartbeat.write_text(json.dumps({"bridge_id":setup["bridge_id"],"time":time.time()-11}))
    assert not gui.connected()
    heartbeat.write_text(json.dumps({"bridge_id":setup["bridge_id"],"time":time.time()}))
    assert gui.connected()


def test_api_tool_backend_requires_configured_interpreter(cfg,monkeypatch):
    from opensim_mcp.core import native_command
    monkeypatch.setenv("OPENSIM_MCP_TOOL_BACKEND","api")
    monkeypatch.delenv("OPENSIM_MCP_API_PYTHON",raising=False)
    with pytest.raises(InputError,match="API_PYTHON"):native_command(cfg,["--version"])
    monkeypatch.setenv("OPENSIM_MCP_TOOL_BACKEND","unexpected")
    with pytest.raises(InputError,match="cli or api"):native_command(cfg,["--version"])


def test_gui_bridge_has_no_python27_dict_comprehension():
    # Real GUI uses Jython 2.5.2. Check the known grammar regression without
    # requiring a GUI/JVM in adapter-only CI.
    import ast
    source=(Path(__file__).resolve().parents[1]/"src/opensim_mcp/gui_bridge.py").read_text()
    parsed=ast.parse(source)
    assert not any(isinstance(node,(ast.DictComp,ast.SetComp,ast.JoinedStr)) for node in ast.walk(parsed))
