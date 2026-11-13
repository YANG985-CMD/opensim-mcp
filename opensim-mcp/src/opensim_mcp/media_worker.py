"""Import NumPy/Matplotlib outside the multithreaded MCP transport process."""
import json
from pathlib import Path
import sys

from .core import Settings
from .media import _plot_motion,_render_model


def main():
    work=Path(sys.argv[1]);request=json.loads((work/'request.json').read_text(encoding='utf-8'))
    cfg=Settings(tuple(Path(p) for p in request['allowed_roots']),work/'published',work/'scratch',None)
    operation=request['operation']
    if operation=='plot':result=_plot_motion(cfg,**request['parameters'])
    elif operation=='model':result=_render_model(cfg,**request['parameters'])
    else:raise ValueError('Unsupported renderer operation.')
    (work/'result.json').write_text(json.dumps(result),encoding='utf-8')


if __name__=='__main__':main()
