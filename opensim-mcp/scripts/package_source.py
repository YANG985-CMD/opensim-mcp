"""Create a Windows source release, excluding private config, state, runtimes and results."""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    project=Path(__file__).resolve().parents[1]
    from opensim_mcp import __version__
    metadata=tomllib.loads((project/'pyproject.toml').read_text(encoding='utf-8'))
    if metadata['project']['version']!=__version__:
        raise ValueError('pyproject.toml version does not match opensim_mcp.__version__. Refusing to publish.')
    excluded={'.git','.venv','.api-venv','.api46-venv','runtimes','state','results','__pycache__','.pytest_cache'}
    files=[]
    for path in project.rglob('*'):
        relative=path.relative_to(project)
        if any(part in excluded for part in relative.parts):continue
        if not path.is_file() or path.is_symlink():continue
        if path.suffix in {'.pyc','.log','.zip','.writing'} or '.local.' in path.name:continue
        if relative.parts[0]=='config' and 'generated' in path.name:continue
        if any(part in {'build','dist'} for part in relative.parts) and relative.as_posix()!='gui-autobridge/dist/org-opensim-mcp-autobridge.jar':continue
        if relative.as_posix()=='validation/source-sha256.json':continue
        files.append(path)
    hashes={p.relative_to(project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (project/'validation/source-sha256.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    files.append(project/'validation/source-sha256.json')
    args.output.mkdir(parents=True,exist_ok=True)
    archive=args.output/('opensim-mcp-v'+__version__+'-windows11.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for p in sorted(files):output.write(p,'opensim-mcp/'+p.relative_to(project).as_posix())
    with zipfile.ZipFile(archive) as source:
        assert source.testzip() is None
        for p,h in hashes.items():assert hashlib.sha256(source.read('opensim-mcp/'+p)).hexdigest()==h
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(sha+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps({'version':__version__,'zip':str(archive),'files':len(files),'sha256':sha}))


if __name__=='__main__':main()
