"""Standalone support report. Shell repair installs only the pinned dependency profiles."""
import argparse
from importlib.metadata import PackageNotFoundError,version
import json
from pathlib import Path
import sys
from . import __version__
from .core import Settings
from .compatibility import check_runtime
from .projects import digest,strict_json


def source_integrity(project):
    path=project/'validation/source-sha256.json'
    if not path.is_file():return {'status':'not_assessed','reason':'No release source manifest.'}
    expected=strict_json(path.read_bytes());mismatches=[]
    for name,sha in expected.items():
        target=project/name
        if not target.resolve().is_relative_to(project.resolve()) or not target.is_file() or digest(target.read_bytes())!=sha:mismatches.append(name)
    return {'status':'pass' if not mismatches else 'warning','checked_files':len(expected),'mismatches':mismatches,
            'note':'Differences can be local edits. Repair does not overwrite source; restore an official verified release explicitly.'}


def diagnose(cfg,project):
    dependencies={}
    for name,required in [('mcp','1.29.1'),('pydantic','2.14.1'),('defusedxml','0.7.1'),('matplotlib','3.11.2'),('ezc3d','1.7.2'),('vtk','9.7.1')]:
        try:actual=version(name)
        except PackageNotFoundError:actual=None
        dependencies[name]={'required':required,'actual':actual,'matches':actual==required}
    compatibility=check_runtime(cfg,native_solver=True)
    return {'adapter_version':__version__,'dependency_status':'pass' if all(v['matches'] for v in dependencies.values()) else 'error',
            'dependencies':dependencies,'compatibility':compatibility,'source_integrity':source_integrity(project),
            'paths':{'results':str(cfg.results_root),'temporary':str(cfg.temp_root),'inputs':[str(p) for p in cfg.allowed_roots]},
            'repair_scope':'Pinned main/API packages and missing configured directories; GUI/native binaries, user models, scripts and source edits are never auto-replaced.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    result=diagnose(Settings.from_env(),Path(__file__).resolve().parents[2])
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'version':__version__,'dependencies':result['dependency_status'],'compatibility':result['compatibility']['status'],'source_integrity':result['source_integrity']['status'],'report':str(args.report)}))
    if result['dependency_status']=='error' or result['compatibility']['status']=='error':raise SystemExit(1)


if __name__=='__main__':main()
