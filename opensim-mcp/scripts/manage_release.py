"""Local release lifecycle CLI. Never selects a GitHub repository or publishes."""
import argparse
import json
from opensim_mcp.releases import verify_release,extract_release,activate_release,rollback_release

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    for name in ('verify','extract'):
        q=s.add_parser(name);q.add_argument('--archive',required=True);q.add_argument('--sha256',required=True)
        if name=='extract':q.add_argument('--destination',required=True)
    q=s.add_parser('activate');q.add_argument('--project',required=True);q.add_argument('--config');q.add_argument('--journal',required=True)
    q=s.add_parser('rollback');q.add_argument('--record',required=True)
    a=p.parse_args()
    if a.command=='verify':value=verify_release(a.archive,a.sha256)[0]
    elif a.command=='extract':value=extract_release(a.archive,a.sha256,a.destination)
    elif a.command=='activate':value=activate_release(a.project,a.config,a.journal)
    else:value=rollback_release(a.record)
    print(json.dumps(value,ensure_ascii=False))

if __name__=='__main__':main()
