import hashlib
import json
from pathlib import Path
import shutil
import tomllib
import zipfile
import pytest
from opensim_mcp.core import InputError
from opensim_mcp.releases import verify_release,extract_release,activate_release,rollback_release,block_for

ROOT=Path(__file__).resolve().parents[1]

def archive(tmp_path,extra=None):
    files={'install.cmd':b'installer','scripts/install.ps1':b'install','pyproject.toml':b'[project]\nversion="0.8.1"',
      'src/opensim_mcp/__init__.py':b'__version__="0.8.1"','config/codex.example.toml':b'# example',
      **{f'examples/{i}.txt':b'example' for i in range(5)}}
    files.update(extra or {})
    files['validation/source-sha256.json']=json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in files.items()}).encode()
    p=tmp_path/'release.zip'
    with zipfile.ZipFile(p,'w') as z:
        for k,v in files.items():z.writestr('opensim-mcp/'+k,v)
    return p,hashlib.sha256(p.read_bytes()).hexdigest()

def test_verified_extract_never_overwrites_or_executes(tmp_path):
    p,sha=archive(tmp_path);target=tmp_path/'new'
    assert extract_release(str(p),sha,str(target))['native_or_installer_executed'] is False
    with pytest.raises(InputError):extract_release(str(p),sha,str(target))
    with pytest.raises(InputError,match='SHA256'):verify_release(str(p),'0'*64)

@pytest.mark.parametrize('name',['../outside','state/secret.json','config/key.local.toml','examples/CON.txt'])
def test_release_rejects_private_and_unsafe_paths(tmp_path,name):
    p,sha=archive(tmp_path,{name:b'secret'})
    with pytest.raises(InputError):verify_release(str(p),sha)

def installed(tmp_path):
    p=tmp_path/'new';(p/'config').mkdir(parents=True);(p/'scripts').mkdir();(p/'examples').mkdir()
    shutil.copyfile(ROOT/'scripts/register_codex.py',p/'scripts/register_codex.py')
    executable=p/'python.exe';executable.touch()
    new={'command':str(executable),'args':['-B','-m','opensim_mcp.server'],'env':{'OPENSIM_MCP_API_PYTHON':str(executable)}}
    (p/'config/opensim_mcp.generated.toml').write_text(block_for(new),encoding='utf-8')
    old=tmp_path/'old-python.exe';old.touch()
    previous={'command':str(old),'args':['old'],'env':{'OPENSIM_MCP_ALLOWED_ROOTS':json.dumps([str(tmp_path)]),
        'OPENSIM_MCP_RESULTS_ROOT':'keep-results','OPENSIM_MCP_TEMP_ROOT':'keep-temp','OPENSIM_MCP_ENABLE_SCRIPTS':'1'}}
    cfg=tmp_path/'codex.toml';cfg.write_text('model="keep"\n[mcp_servers.other]\ncommand="keep-other"\n'+block_for(previous),encoding='utf-8')
    return p,cfg,previous

def test_activation_and_rollback_preserve_user_data_settings_and_other_servers(tmp_path):
    p,cfg,previous=installed(tmp_path);result=activate_release(str(p),str(cfg),str(tmp_path/'journal'))
    current=tomllib.loads(cfg.read_text(encoding='utf-8'));assert current['model']=='keep'
    assert current['mcp_servers']['other']['command']=='keep-other'
    env=current['mcp_servers']['opensim_mcp']['env'];assert env['OPENSIM_MCP_ENABLE_SCRIPTS']=='1' and env['OPENSIM_MCP_RESULTS_ROOT']=='keep-results'
    assert rollback_release(result['record_file'])['rolled_back']
    assert tomllib.loads(cfg.read_text(encoding='utf-8'))['mcp_servers']['opensim_mcp']==previous

def test_rollback_refuses_concurrent_server_config_changes(tmp_path):
    p,cfg,_=installed(tmp_path);result=activate_release(str(p),str(cfg),str(tmp_path/'journal'))
    cfg.write_text(cfg.read_text(encoding='utf-8').replace('keep-results','changed'),encoding='utf-8')
    before=cfg.read_bytes()
    with pytest.raises(InputError,match='changed'):rollback_release(result['record_file'])
    assert cfg.read_bytes()==before
