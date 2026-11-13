import importlib.util
import json
from pathlib import Path
import tomllib
import pytest
from opensim_mcp.core import InputError,Settings
from opensim_mcp.compatibility import check_runtime

spec=importlib.util.spec_from_file_location('register_codex',Path(__file__).resolve().parents[1]/'scripts/register_codex.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_codex_registration_preserves_other_servers_settings_and_quoted_header():
    before='model="custom"\n[mcp_servers.other]\ncommand="keep"\n[mcp_servers."opensim_mcp"]\ncommand="old"\n[mcp_servers."opensim_mcp".env]\nX="old"\n[features]\nflag=true\n'
    block='[mcp_servers.opensim_mcp]\ncommand="new"\n[mcp_servers.opensim_mcp.env]\nX="new"\n'
    result=tomllib.loads(module.merge(before,block));assert result['model']=='custom'
    assert result['mcp_servers']['other']['command']=='keep' and result['features']['flag']
    assert result['mcp_servers']['opensim_mcp']['env']['X']=='new'


def test_unsupported_codex_layout_fails_without_guessing():
    before='mcp_servers.opensim_mcp.command="old"\n'
    with pytest.raises(ValueError):module.merge(before,'[mcp_servers.opensim_mcp]\ncommand="new"')


def test_unavailable_native_runtime_is_error_not_compatible(tmp_path,monkeypatch):
    def reject(*args,**kwargs):raise InputError('native DLL missing')
    monkeypatch.setattr('opensim_mcp.compatibility.execute',reject)
    result=check_runtime(Settings((tmp_path,),tmp_path/'results',tmp_path,None))
    assert result['status']=='error' and any(c['name']=='native_api' and c['status']=='error' for c in result['checks'])


@pytest.mark.parametrize('numpy_version,expected_status',[('2.5.4','pass'),('0.0.0','warning')])
def test_runtime_numpy_must_match_the_tested_profile(tmp_path,monkeypatch,numpy_version,expected_status):
    def capabilities(cfg,args,work,timeout,force_api=False):
        assert force_api and args==['--capabilities']
        data=dict(opensim_version='version 4.6-2026-06-22-85aaf64',python='3.12.13',numpy=numpy_version,
                  moco_track=True,moco_inverse=True,moco_casadi=True,marker_placer=True)
        (work/'cli.log').write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr('opensim_mcp.compatibility.execute',capabilities)
    result=check_runtime(Settings((tmp_path,),tmp_path/'results',tmp_path,None))
    assert next(c for c in result['checks'] if c['name']=='api_numpy')['status']==expected_status
