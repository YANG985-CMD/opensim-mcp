"""Actual workflow phases, not estimated solver completion percentages."""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
import uuid


def report(phase,**values):
    value=os.environ.get('OPENSIM_MCP_PROGRESS_FILE')
    if not value:return
    path=Path(value);temp=path.with_name(uuid.uuid4().hex+'.writing')
    temp.write_text(json.dumps({'phase':phase,'updated_unix':time.time(),'solver_fraction':None,**values}),encoding='utf-8')
    # Windows readers can briefly prevent replacement. Telemetry must never
    # abort a solver or leave a just-started native process unmonitored.
    try:
        for attempt in range(10):
            try:temp.replace(path);return
            except PermissionError:time.sleep(.01*(attempt+1))
    finally:temp.unlink(missing_ok=True)
