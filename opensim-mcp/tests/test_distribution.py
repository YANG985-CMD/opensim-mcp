"""No complete Python source tree in the public installer; retain trusted verification."""
import hashlib,importlib.util,json,subprocess,sys,zipfile
from pathlib import Path
import pytest

PROJECT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    root=tmp_path_factory.mktemp('compiled-distribution')
    spec=importlib.util.spec_from_file_location('build_distribution',PROJECT/'scripts/build_installer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.build(PROJECT,root/'release',root/'build')
    archive=Path(result['archive']);unpacked=root/'unpacked'
    with zipfile.ZipFile(archive) as z:z.extractall(unpacked)
    return result,unpacked/'opensim-mcp'

def test_binary_distribution_has_only_jython_python_source_and_no_private_files(binary):
    result,root=binary
    assert result['python_source_files']==['src/opensim_mcp/gui_bridge.py']
    assert result['compiled_modules']>=69 and not result['full_source_included']
    assert not any(set(p.relative_to(root).parts)&{'.git','.github','tests','state','results','runtimes','.venv'} for p in root.rglob('*'))
    assert (root/'src/opensim_mcp/server.pyc').read_bytes()[:4]==importlib.util.MAGIC_NUMBER

def test_distribution_manifest_covers_all_public_files(binary):
    result,root=binary
    expected=json.loads((root/'validation/source-sha256.json').read_text(encoding='utf-8'))
    actual={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.relative_to(root).as_posix()!='validation/source-sha256.json'}
    assert actual==expected
    assert hashlib.sha256(Path(result['archive']).read_bytes()).hexdigest()==result['sha256']

def probe(binary,code):
    _,root=binary
    script='import sys;sys.path.insert(0,'+repr(str(root/'src'))+');'+code
    return subprocess.run([sys.executable,'-I','-B','-c',script],check=True,text=True,capture_output=True).stdout

def test_sourceless_import_fingerprint_and_release_verification(binary):
    result,root=binary
    code='from opensim_mcp.pipeline import source_hash;from opensim_mcp.releases import verify_release;assert source_hash()!='+repr(hashlib.sha256(b'').hexdigest())+';info,_=verify_release('+repr(result['archive'])+','+repr(result['sha256'])+');assert info["format"]=="cpython312-bytecode";print(info["valid"])'
    assert probe(binary,code).strip()=='True'

def test_sourceless_native_worker_paths_are_compiled(binary):
    _,root=binary
    code='import os;os.environ["OPENSIM_MCP_API_PYTHON"]=sys.executable;os.environ["OPENSIM_MCP_TOOL_BACKEND"]="api";from pathlib import Path;from opensim_mcp.core import Settings,native_command;root=Path('+repr(str(root))+');cmd=native_command(Settings((root/"examples",),root/"results",root/"work",None),["--version"]);assert Path(cmd[2]).suffix==".pyc" and Path(cmd[2]).is_file();print("compiled")'
    assert probe(binary,code).strip()=='compiled'

def test_bytecode_limit_and_runtime_script_disclosure(binary):
    _,root=binary;meta=json.loads((root/'distribution.json').read_text(encoding='utf-8'))
    assert meta['python']=='3.12' and meta['legacy_python38_supported'] is False
    assert 'not encryption' in meta['format']
    assert 'src/opensim_mcp/gui_bridge.py' in meta['readable_integration_files']
