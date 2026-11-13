"""Observed runtime capabilities, explicit supported/tested version profiles."""
import json
import os
from pathlib import Path
import platform
import re
import struct
import sys
import tempfile
from .core import execute


def check_runtime(cfg,native_solver=False):
    checks=[]
    def add(name,status,detail):checks.append(dict(name=name,status=status,detail=detail))
    build=int(platform.version().split('.')[-1]) if os.name=='nt' else 0
    add('windows_x64','pass' if os.name=='nt' and build>=22000 and struct.calcsize('P')==8 else 'error',platform.platform())
    add('server_python','pass' if sys.version_info[:2]==(3,12) else 'warning',platform.python_version()+'; primary lock/profile is CPython 3.12 x64')
    runtime=None
    try:
        with tempfile.TemporaryDirectory(prefix='compatibility-',dir=cfg.temp_root) as name:
            work=Path(name);execute(cfg,['--capabilities'],work,min(30,cfg.timeout),force_api=True)
            lines=(work/'cli.log').read_text(encoding='utf-8',errors='replace').splitlines()
            runtime=json.loads(next(line for line in reversed(lines) if line.startswith('{')))
        version=runtime['opensim_version'];primary=bool(re.match(r'^(?:version\s+)?4\.6(?:\D|$)',version)) and runtime['python'].startswith('3.12.')
        legacy=bool(re.match(r'^(?:version\s+)?4\.3(?:\D|$)',version)) and runtime['python'].startswith('3.8.')
        add('api_version','pass' if primary else 'warning',version+('; primary tested API profile' if primary else '; legacy core profile' if legacy else '; unvalidated version combination'))
        expected_numpy='2.5.4' if primary else '1.20.3' if legacy else None
        add('api_numpy','pass' if expected_numpy and runtime['numpy']==expected_numpy else 'warning',runtime['numpy']+'; tested NumPy: '+str(expected_numpy or 'no validated profile'))
        add('marker_placer','pass' if runtime['marker_placer'] else 'warning','Observed MarkerPlacer symbol availability, not a native placement test.')
        add('moco_profiles','pass' if runtime['moco_track'] and runtime['moco_inverse'] and runtime['moco_casadi'] else 'warning','Observed MocoTrack/Inverse/CasADi symbol availability, not a solver execution test.')
        if native_solver:
            with tempfile.TemporaryDirectory(prefix='solver-probe-',dir=cfg.temp_root) as name:
                work=Path(name);execute(cfg,['--solver-probe'],work,min(60,cfg.timeout),force_api=True)
                lines=(work/'cli.log').read_text(encoding='utf-8',errors='replace').splitlines();probe=json.loads(next(line for line in reversed(lines) if line.startswith('{')))
            add('native_moco_solver','pass' if probe.get('solver_success') else 'error',probe)
    except Exception as exc:add('native_api','error',str(exc)[-2000:])
    add('gui_distribution','info','GUI core and API runtime are separate. Installed GUI bridge reports actual GUI core; final 4.6 GUI is not assumed.')
    status='error' if any(c['status']=='error' for c in checks) else ('warning' if any(c['status']=='warning' for c in checks) else 'pass')
    return {'status':status,'checks':checks,'api_runtime':runtime,'scope':('Import/capability checks plus an actual tiny native Moco/IPOPT solve. Study-specific workflows need their own regressions.' if native_solver else 'Import/capability checks only. A successful native solve requires the included smoke/regression suite.')}
