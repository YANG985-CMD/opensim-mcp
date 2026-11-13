"""Merge only the opensim_mcp block, preserving unrelated parsed configuration values."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import tomllib
import uuid


def merge(existing,block):
    original=tomllib.loads(existing);replacement=tomllib.loads(block)
    if set(replacement)!={'mcp_servers'} or set(replacement['mcp_servers'])!={'opensim_mcp'}:raise ValueError('Expected only opensim_mcp configuration.')
    lines=[];skip=False
    for line in existing.splitlines(keepends=True):
        stripped=line.strip()
        if stripped.startswith('[') and not stripped.startswith('[['):
            # Identify table headers using the TOML parser, including quoted keys.
            try:table=tomllib.loads(stripped+'\n')
            except tomllib.TOMLDecodeError:table={}
            server=table.get('mcp_servers')
            skip=isinstance(server,dict) and set(server)=={'opensim_mcp'}
        if not skip:lines.append(line)
    value=''.join(lines).rstrip()+'\n\n'+block.strip()+'\n'
    parsed=tomllib.loads(value);expected=dict(original);servers=dict(expected.get('mcp_servers',{}))
    servers['opensim_mcp']=replacement['mcp_servers']['opensim_mcp'];expected['mcp_servers']=servers
    if parsed!=expected:raise ValueError('Unsupported TOML layout: automatic merge would change unrelated values.')
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--block',type=Path,required=True);parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--config',type=Path);args=parser.parse_args()
    config=args.config or Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
    existing=config.read_text(encoding='utf-8') if config.exists() else ''
    value=merge(existing,args.block.read_text(encoding='utf-8-sig'))
    args.backup_dir.mkdir(parents=True,exist_ok=True)
    if existing:(args.backup_dir/('config-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.toml')).write_text(existing,encoding='utf-8')
    config.parent.mkdir(parents=True,exist_ok=True)
    # User config is a formal deliverable, written only after parse/preservation checks.
    config.write_text(value,encoding='utf-8');print('Registered opensim_mcp; preserved unrelated configuration. Restart Codex.')


if __name__=='__main__':main()
