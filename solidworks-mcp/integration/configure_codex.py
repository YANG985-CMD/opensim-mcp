"""Migrate only solidworks/solidworks-mcp, preserving every other setting."""
import argparse
import copy
import datetime
import json
import re
import tomllib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER='solidworks-mcp'
ALIASES=('solidworks','solidworks-mcp')


def literal(value):
    value=str(value).replace('\\','/')
    if "'" in value or '\n' in value or '\r' in value: raise ValueError('Unsupported path character')
    return "'"+value+"'"


def block(output):
    return f'''[mcp_servers.solidworks-mcp]
command = {literal(ROOT/'.venv/Scripts/python.exe')}
args = ['-B', '-u', {literal(ROOT/'launch.py')}]
cwd = {literal(ROOT)}
startup_timeout_sec = 120
tool_timeout_sec = 150
enabled = true

[mcp_servers.solidworks-mcp.env]
PYTHONIOENCODING = 'utf-8'
PYTHONUTF8 = '1'
PYTHONDONTWRITEBYTECODE = '1'
TEMP = 'E:/simulink/_codex_tmp/solidworks_local_runtime'
TMP = 'E:/simulink/_codex_tmp/solidworks_local_runtime'
SWLOCAL_TEMP = 'E:/simulink/_codex_tmp/solidworks_local_runtime'
SWLOCAL_OUTPUT = {literal(output)}
SWLOCAL_YEAR = '2025'
SWLOCAL_TYPELIB = 'D:/SW2025/SOLIDWORKS/sldworks.tlb'
SWLOCAL_TIMEOUT = '120'
'''


def replacement(source,new_block):
    pattern=re.compile(r'^\[([^\]\r\n]+)\][ \t]*$',re.M)
    headers=list(pattern.finditer(source))
    pieces=[source[:headers[0].start()] if headers else source]
    inserted=False
    for i,header in enumerate(headers):
        end=headers[i+1].start() if i+1<len(headers) else len(source)
        name=header.group(1)
        if any(name=='mcp_servers.'+alias or name.startswith('mcp_servers.'+alias+'.') for alias in ALIASES):
            if not inserted: pieces.append(new_block+'\n');inserted=True
        else: pieces.append(source[header.start():end])
    if not inserted: pieces.append('\n'+new_block)
    return ''.join(pieces)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--temp-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,default=ROOT.parent/'SolidWorks输出')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    scratch=args.temp_root.resolve()
    if not scratch.is_relative_to(Path(r'E:\simulink\_codex_tmp').resolve()): parser.error('Temporary files must be under E:\\simulink\\_codex_tmp')
    scratch.mkdir(parents=True,exist_ok=True)
    original=args.config.read_bytes()
    source=original.decode('utf-8-sig')
    old=tomllib.loads(source)
    servers=old.get('mcp_servers',{})
    if all(alias in servers for alias in ALIASES) and servers[ALIASES[0]]!=servers[ALIASES[1]]:
        raise RuntimeError('Both server names exist with different settings; refusing ambiguous migration')
    if 'solidworks' in servers and SERVER not in servers:
        # Rename the existing entry, preserving any user-specific environment,
        # tools policy and timeouts instead of replacing it with defaults.
        candidate=re.sub(r'(?m)^(\[mcp_servers\.)solidworks(?=[.\]])',r'\g<1>'+SERVER,source)
        new_block=block(args.output_root.resolve())
    elif SERVER in servers:
        candidate=source
        if 'solidworks' in servers: candidate=replacement(source,block(args.output_root.resolve()))
        new_block=block(args.output_root.resolve())
    else:
        new_block=block(args.output_root.resolve());candidate=replacement(source,new_block)
    new=tomllib.loads(candidate)
    old_other,new_other=copy.deepcopy(old),copy.deepcopy(new)
    for alias in ALIASES:
        old_other.get('mcp_servers',{}).pop(alias,None)
        new_other.get('mcp_servers',{}).pop(alias,None)
    if old_other!=new_other: raise RuntimeError('Refusing to change settings outside the renamed server')
    previous=servers.get('solidworks',servers.get(SERVER))
    if previous is not None and new['mcp_servers'][SERVER]!=previous:raise RuntimeError('Server settings changed during rename')
    (scratch/'config.candidate.toml').write_text(candidate,encoding='utf-8')
    (ROOT/'integration/codex-server.toml').write_text(new_block,encoding='utf-8')
    if args.apply:
        # Refuse a concurrent configuration update instead of overwriting it.
        if args.config.read_bytes()!=original: raise RuntimeError('Configuration changed during validation; run again')
        stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup=scratch/f'config.before-{stamp}.toml'
        backup.write_bytes(original)
        try:
            args.config.write_text(candidate,encoding='utf-8')
            assert tomllib.loads(args.config.read_text(encoding='utf-8'))==new
        except Exception:
            args.config.write_bytes(original)
            raise
    print(json.dumps({'applied':args.apply,'server':SERVER,'command':new['mcp_servers'][SERVER]['command'],'other_servers_preserved':len(new.get('mcp_servers',{}))-1},ensure_ascii=False))


if __name__=='__main__': main()
