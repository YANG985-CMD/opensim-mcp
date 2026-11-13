"""Own a new test extraction; run install and deliberate failures there only.

Requires an already installed adapter to verify the trusted source archive.
Does not modify the user's real Codex configuration or an existing environment.
"""
from __future__ import annotations
import argparse,json,os,subprocess
from pathlib import Path
from opensim_mcp.releases import extract_release

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--workdir',required=True,type=Path);args=p.parse_args();root=args.workdir.resolve()
    if root.exists() or not root.parent.is_dir() or root.parent==root:raise ValueError('Choose a NEW dedicated task directory under an existing temporary parent.')
    root.mkdir();project=root/'安装复现 空格';runtime=root/'安装运行 空格';codex=root/'test-codex';codex.mkdir()
    extract_release(args.archive,args.sha256,str(project));config=codex/'config.toml';config.write_text('model="preserve"\n[mcp_servers.other]\ncommand="preserve"\n',encoding='utf-8');before=config.read_bytes()
    env=dict(os.environ,TEMP=str(root),TMP=str(root),CODEX_HOME=str(codex),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
    ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File'];checks={}
    def run(name,command,failure=False):
        log=root/(name+'.log')
        with log.open('wb') as stream:result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
        if (result.returncode!=0)!=failure:raise RuntimeError(name+' unexpected exit; inspect '+str(log))
        if config.read_bytes()!=before:raise RuntimeError('Unrelated test Codex settings changed.')
        checks[name]=dict(exit_code=result.returncode,expected_failure=failure);print(name+' expected result confirmed',flush=True)
    cold=root/'cold-offline';extract_release(args.archive,args.sha256,str(cold))
    run('cold-offline',ps+[str(cold/'scripts/install.ps1'),'-TempRoot',str(root/'cold-runtime'),'-Offline'],True)
    run('online-install',ps+[str(project/'scripts/install.ps1'),'-TempRoot',str(runtime),'-WithTests','-SkipCodexRegistration'])
    run('offline-repair',ps+[str(project/'scripts/install.ps1'),'-TempRoot',str(runtime),'-Offline','-Repair','-WithTests','-SkipCodexRegistration'])
    native=project/'.api46-venv/Lib/site-packages/opensim/casadi_nlpsol_ipopt.dll';backup=native.with_suffix('.dll.test-backup');native.rename(backup)
    try:
        run('missing-solver-doctor',ps+[str(project/'scripts/doctor.ps1'),'-TempRoot',str(runtime)],True)
        run('failed-solver-no-registration',ps+[str(project/'scripts/install.ps1'),'-TempRoot',str(runtime),'-Offline'],True)
    finally:
        if backup.exists():backup.rename(native)
    # uv was either already available or bootstrapped inside this owned project.
    import shutil
    uv=shutil.which('uv') or str(project/'runtimes/tools/uv.exe')
    run('remove-ezc3d',[uv,'pip','uninstall','--python',str(project/'.venv/Scripts/python.exe'),'ezc3d'])
    run('missing-dependency-doctor',ps+[str(project/'scripts/doctor.ps1'),'-TempRoot',str(runtime)],True)
    run('offline-dependency-repair',ps+[str(project/'scripts/install.ps1'),'-TempRoot',str(runtime),'-Offline','-Repair','-WithTests','-SkipCodexRegistration'])
    run('final-doctor',ps+[str(project/'scripts/doctor.ps1'),'-TempRoot',str(runtime)])
    report=dict(passed=True,checks=checks,unrelated_test_codex_preserved=True,actual_user_codex_untouched=True,
        clean_windows11_vm_executed=False,scope='Fresh-directory and fault-injection tests on the current OS. A fresh OS/VM must be provided and confirmed separately.')
    (root/'installation-matrix.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
