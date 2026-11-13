"""Verified side-by-side source releases and reversible single-server activation."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tomllib
import uuid
import zipfile

from .bundles import safe_name
from .core import InputError, bounded_read, local_path
from .pipeline import atomic_json, now
from .projects import strict_json

MAX_RELEASE=64*1024**2
PRIVATE={'.git','.venv','.api-venv','.api46-venv','runtimes','state','results','__pycache__'}


def digest(data):return hashlib.sha256(data).hexdigest()


def verify_release(archive_path,expected_sha256):
    archive=local_path(archive_path)
    if not isinstance(expected_sha256,str) or not re.fullmatch('[0-9a-fA-F]{64}',expected_sha256):raise InputError('An explicitly trusted release SHA256 is required.')
    raw=bounded_read(archive,MAX_RELEASE)
    if digest(raw)!=expected_sha256.lower():raise InputError('Release ZIP SHA256 mismatch.')
    try:
        with zipfile.ZipFile(archive) as z:
            inventory=z.infolist();names=set();total=0;files={}
            if not 10<=len(inventory)<=1000:raise InputError('Unsupported release inventory size.')
            for item in inventory:
                p=safe_name(item.filename)
                if not p.parts or p.parts[0]!='opensim-mcp' or len(p.parts)<2:raise InputError('Release root must be opensim-mcp/.')
                relative='/'.join(p.parts[1:]);folded=relative.casefold()
                if folded in names or item.is_dir() or item.flag_bits&1 or (item.external_attr>>16)&0o170000==0o120000:raise InputError('Duplicate, directory, encrypted or linked release entry.')
                if any(part in PRIVATE for part in p.parts) or '.local.' in relative or (relative.startswith('config/') and 'generated' in relative):raise InputError('Private state/runtime in source release.')
                names.add(folded);total+=item.file_size
                if total>MAX_RELEASE or item.file_size>20*1024**2:raise InputError('Expanded release size exceeded.')
                files[relative]=z.read(item)
    except (zipfile.BadZipFile,RuntimeError) as exc:raise InputError('Invalid source ZIP: '+str(exc)) from exc
    manifest=strict_json(files.get('validation/source-sha256.json',b'{}'))
    if manifest!={name:digest(data) for name,data in files.items() if name!='validation/source-sha256.json'}:raise InputError('Release source inventory/hash mismatch.')
    required={'install.cmd','scripts/install.ps1','pyproject.toml','src/opensim_mcp/__init__.py','config/codex.example.toml'}
    if not required<=files.keys():raise InputError('Missing source release entry points.')
    version=tomllib.loads(files['pyproject.toml'].decode('utf-8'))['project']['version']
    match=re.search(rb'__version__\s*=\s*[\'"]([^\'"]+)[\'"]',files['src/opensim_mcp/__init__.py'])
    if not match or match.group(1).decode()!=version or not re.fullmatch(r'\d+\.\d+\.\d+',version):raise InputError('Release version metadata mismatch.')
    return {'valid':True,'version':version,'sha256':digest(raw),'files':len(files)},files


def extract_release(archive_path,expected_sha256,destination):
    info,files=verify_release(archive_path,expected_sha256);target=local_path(destination)
    if target.exists() or target.parent==target or not target.parent.is_dir():raise InputError('Destination must be a new folder under an existing parent.')
    # No executable is run by verification/extraction. A trusted release installer
    # must still be invoked explicitly by the upgrade orchestration.
    target.mkdir()
    try:
        for name,data in files.items():
            path=target.joinpath(*name.split('/'));path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    except BaseException:
        shutil.rmtree(target);raise
    return dict(info,destination=str(target),native_or_installer_executed=False)


def merger(project):
    spec=importlib.util.spec_from_file_location('opensim_register',project/'scripts/register_codex.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module.merge


def block_for(server):
    # JSON basic string syntax is a TOML-compatible subset for these values.
    def value(v):
        if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
        if isinstance(v,list):return '['+', '.join(value(x) for x in v)+']'
        if isinstance(v,(int,float)) and not isinstance(v,bool):return str(v)
        if isinstance(v,bool):return str(v).lower()
        raise InputError('Unsupported Codex server value.')
    rows=['[mcp_servers.opensim_mcp]']
    for k,v in server.items():
        if k!='env':rows.append(json.dumps(k)+' = '+value(v))
    rows+=['','[mcp_servers.opensim_mcp.env]']
    for k,v in server.get('env',{}).items():rows.append(json.dumps(k)+' = '+value(v))
    return '\n'.join(rows)+'\n'


def config_file(path=None):return local_path(path or Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml')


def activate_release(project_path,config_path,journal_root):
    project=local_path(project_path);config=config_file(config_path);journal=local_path(journal_root)
    generated=tomllib.loads((project/'config/opensim_mcp.generated.toml').read_text(encoding='utf-8-sig'))['mcp_servers']['opensim_mcp']
    existing=config.read_text(encoding='utf-8');before=tomllib.loads(existing)['mcp_servers']['opensim_mcp']
    for key in ('command',):
        if not Path(generated[key]).is_file():raise InputError('New release must be installed and verified before activation.')
    old_env=before.get('env',{})
    if old_env.get('OPENSIM_MCP_API_SDK') or old_env.get('OPENSIM_MCP_TOOL_BACKEND','api')!='api':raise InputError('Automatic switching supports the primary wheel/API profile; regenerate legacy configuration explicitly.')
    after=dict(before);after.update(command=generated['command'],args=generated['args']);env=dict(old_env)
    env['OPENSIM_MCP_API_PYTHON']=generated['env']['OPENSIM_MCP_API_PYTHON'];env['OPENSIM_MCP_API_SDK']='';env['OPENSIM_MCP_TOOL_BACKEND']='api'
    after['env']=env
    replacement=merger(project)(existing,block_for(after))
    identifier=uuid.uuid4().hex;record={'update_id':identifier,'created_utc':now(),'status':'prepared','previous_server':before,
        'new_server':after,'config_path':str(config),'new_project':str(project),'scope':'Codex opensim_mcp configuration only; user data and installed old release remain in place.'}
    path=journal/(identifier+'.json');atomic_json(path,record)
    # Persistent recovery journal precedes the single configuration write.
    config.write_text(replacement,encoding='utf-8');record['status']='activated';atomic_json(path,record)
    return {'activated':True,'update_id':identifier,'record_file':str(path),'restart_codex_required':True,'preserved_old_release':True,'preserved_input_result_temp_and_scripting_settings':True}


def rollback_release(record_path):
    path=local_path(record_path);record=strict_json(bounded_read(path,1024**2));config=config_file(record['config_path'])
    existing=config.read_text(encoding='utf-8');current=tomllib.loads(existing)['mcp_servers']['opensim_mcp']
    if current!=record['new_server']:raise InputError('Server configuration changed after activation; refusing to overwrite it.')
    if not Path(record['previous_server']['command']).is_file():raise InputError('Previous interpreter is unavailable; no configuration was changed.')
    project=local_path(record['new_project']);replacement=merger(project)(existing,block_for(record['previous_server']))
    config.write_text(replacement,encoding='utf-8');record.update(status='rolled_back',rollback_utc=now());atomic_json(path,record)
    return {'rolled_back':True,'update_id':record['update_id'],'restart_codex_required':True}
