"""Explicit native-workflow project bundles; verified import, never execute on import."""
from __future__ import annotations
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid
import zipfile

from . import __version__
from .core import InputError, bounded_read, environment
from .projects import digest, json_bytes, prepare_submission, strict_json, validate_shape
from .session import staged_model

MAX_TOTAL=256*1024**2
RESERVED=re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',re.I)


def safe_name(name):
    if not isinstance(name,str) or len(name)>300 or '\\' in name or ':' in name or '\x00' in name:
        raise InputError('Unsafe bundle entry name.')
    path=PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in {'','.','..'} or p.rstrip(' .')!=p or RESERVED.match(p) or any(ord(c)<32 or c in '*?<>|"' for c in p) for p in name.split('/')):
        raise InputError('Unsafe Windows bundle path.')
    return path


def export_bundle(cfg,project_path):
    snapshot=prepare_submission(cfg,project_path);project=snapshot['project'];files={};sources={}
    for key,asset in snapshot['inputs'].items():
        path=cfg.input_path(asset['path'],Path(asset['path']).suffix.lower());raw=bounded_read(path,64*1024**2)
        if digest(raw)!=asset['sha256']:raise InputError('Input changed during export.')
        # Match native staging: retain safe primitives, remove external display assets.
        data=staged_model(raw) if asset['kind']=='model' else raw
        name='assets/'+key+path.suffix.lower();files[name]=data;project['inputs'][key]['path']=name
        sources[key]={'source_sha256':asset['sha256'],'bundled_sha256':digest(data),'bytes':len(data),
                      'transformation':'native model XML; external display geometry removed, safe primitives retained' if asset['kind']=='model' else 'unchanged'}
    validate_shape(project);files['project.json']=json_bytes(project)
    runtime=environment(cfg)
    files['dependencies.json']=json_bytes({'adapter_version':__version__,'selected_backend':runtime['tool_backend'],
        'opensim_version':runtime['opensim_version'],'server_python':runtime['python'],'mcp':runtime['mcp'],
        'platform':'Windows 11 x64','runtime_binaries_included':False,'requires_native_api_for_scale_moco_profiles':True,
        'model_visuals_included':False,'sources':sources})
    if sum(len(v) for v in files.values())>MAX_TOTAL:raise InputError('Bundle exceeds 256 MiB.')
    manifest={'format':'opensim-mcp-project','bundle_version':1,'files':{k:{'sha256':digest(v),'bytes':len(v)} for k,v in files.items()}}
    files['bundle.json']=json_bytes(manifest)
    with tempfile.TemporaryDirectory(prefix='bundle-export-',dir=cfg.temp_root) as name:
        temporary=Path(name)/'project.zip'
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for key,data in files.items():archive.writestr(key,data)
        folder=cfg.results_root/('bundle-'+uuid.uuid4().hex);folder.mkdir(parents=True)
        target=folder/'project.zip';shutil.copyfile(temporary,target)
        sha=digest(bounded_read(target,MAX_TOTAL));(folder/'project.zip.sha256').write_text(sha+'  project.zip\n',encoding='utf-8')
    return {'bundle_file':str(target),'sha256':sha,'files':len(files),'dependencies':strict_json(files['dependencies.json']),
            'includes_input_data':True,'scope':'Portable native workflow inputs and configuration; no GUI meshes, credentials, scripts or runtime binaries.'}


def inspect_archive(path):
    if path.stat().st_size>MAX_TOTAL:raise InputError('Bundle ZIP exceeds 256 MiB.')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if not 3<=len(entries)<=100:raise InputError('Bundle must contain 3..100 files.')
        names=set();size=0
        for info in entries:
            safe_name(info.filename);folded=info.filename.casefold()
            if folded in names or info.is_dir() or info.flag_bits&1 or (info.external_attr>>16)&0o170000==0o120000:raise InputError('Duplicate, encrypted, directory or link entry rejected.')
            names.add(folded);size+=info.file_size
            if size>MAX_TOTAL or info.file_size>64*1024**2:raise InputError('Bundle expanded-size limit exceeded.')
        files={info.filename:archive.read(info) for info in entries}
    manifest=strict_json(files.get('bundle.json',b'{}'))
    if set(manifest)!={'format','bundle_version','files'} or manifest['format']!='opensim-mcp-project' or type(manifest['bundle_version']) is not int or manifest['bundle_version']!=1:
        raise InputError('Unsupported bundle format.')
    actual={k:{'sha256':digest(v),'bytes':len(v)} for k,v in files.items() if k!='bundle.json'}
    if manifest['files']!=actual:raise InputError('Bundle hash/inventory mismatch.')
    if not {'project.json','dependencies.json'}<=set(actual):raise InputError('Missing bundle metadata.')
    project=validate_shape(strict_json(files['project.json']))
    expected={'project.json','dependencies.json','bundle.json'}
    for key,asset in project.inputs.items():
        path=safe_name(asset.path)
        if len(path.parts)!=2 or path.parts[0]!='assets' or path.name!=key+path.suffix:raise InputError('Bundle asset paths must be assets/<id>.<extension>.')
        if asset.path not in files:raise InputError('Missing project asset.')
        expected.add(asset.path)
    if set(files)!=expected:raise InputError('Untracked bundle entries rejected.')
    dependencies=strict_json(files['dependencies.json'])
    if not isinstance(dependencies,dict):raise InputError('Invalid dependency metadata.')
    return files,project,dependencies


def verify_bundle(cfg,bundle_path):
    path=cfg.input_path(bundle_path,'.zip')
    try:files,project,dependencies=inspect_archive(path)
    except (zipfile.BadZipFile,KeyError,RuntimeError) as exc:raise InputError('Invalid project bundle: '+str(exc)) from exc
    return {'valid':True,'sha256':digest(bounded_read(path,MAX_TOTAL)),'name':project.name,'files':len(files),
            'dependencies':dependencies,'runtime_compatibility':'recorded, not guaranteed; run installed-runtime validation before computation'}


def import_bundle(cfg,bundle_path):
    path=cfg.input_path(bundle_path,'.zip');verification=verify_bundle(cfg,bundle_path)
    files,project,dependencies=inspect_archive(path)
    # Files are data. No setup hooks/scripts/native models are executed during import.
    with tempfile.TemporaryDirectory(prefix='bundle-import-',dir=cfg.temp_root) as name:
        work=Path(name)/'project';work.mkdir()
        for filename,data in files.items():
            target=work.joinpath(*PurePosixPath(filename).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        from dataclasses import replace
        prepare_submission(replace(cfg,allowed_roots=(*cfg.allowed_roots,work)),str(work/'project.json'))
        folder=cfg.results_root/'imported-projects'/uuid.uuid4().hex;folder.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(work,folder)
    return {'project_path':str(folder/'project.json'),'imported':True,'executed':False,'bundle_sha256':verification['sha256'],
            'dependencies':dependencies,'warning':'Dependency hashes detect corruption, not author trust. Review native models and data before execution.'}
