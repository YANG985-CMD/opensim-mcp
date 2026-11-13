"""Private async worker. Wait for the parent's Windows Job Object start gate."""
import json
from pathlib import Path
import sys
import time
import traceback

from .core import Settings
from .jobs import dispatch
from .progress import report


def main():
    folder=Path(sys.argv[1]);deadline=time.monotonic()+30
    while not (folder/'go').is_file():
        if time.monotonic()>deadline:raise TimeoutError('Process-tree start gate was not opened.')
        time.sleep(.02)
    try:
        report('validating_inputs')
        request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        value=dispatch(Settings.from_env(),request['workflow'],request['parameters'],request.get('submission'))
        result={'ok':True,'value':value}
    except BaseException:
        result={'ok':False,'error':traceback.format_exc()[-24000:]}
    (folder/'result.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    if not result['ok']:raise SystemExit(1)


if __name__=='__main__':main()
