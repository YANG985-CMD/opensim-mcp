from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
import os
import subprocess
import sys
import tempfile
import shutil
import time

from .core import InputError,MAX_RESULT,bounded_read,is_under,local_path,read_motion


def plotting(cfg):
    import os
    os.environ['MPLCONFIGDIR']=str(cfg.temp_root/'matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams.update({'text.usetex':False,'svg.fonttype':'none'})
    from matplotlib import pyplot as plt
    return plt


def save_figure(cfg,figure,metadata):
    folder=cfg.results_root/('figure-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    try:
        figure.savefig(folder/'figure.png',dpi=120)
        figure.savefig(folder/'figure.svg')
    finally:
        from matplotlib import pyplot as plt
        plt.close(figure)
    metadata.update(image_file=str(folder/'figure.png'),svg_file=str(folder/'figure.svg'))
    (folder/'provenance.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return metadata


def _plot_motion(cfg,path,columns,title='',ylabel='Value (file units)'):
    target=local_path(path)
    if not (is_under(target,cfg.results_root) or any(is_under(target,r) for r in cfg.allowed_roots)) or target.suffix.lower() not in {'.mot','.sto'}:
        raise InputError('Plot input must be an allowed motion/result file.')
    if not isinstance(columns,list) or not 1<=len(columns)<=8 or len(set(columns))!=len(columns):raise InputError('Select 1..8 unique columns.')
    if any(not isinstance(v,str) or len(v)>200 for v in (title,ylabel)):raise InputError('title/ylabel must be at most 200 characters.')
    table=read_motion(target)
    if set(columns)-set(table['columns']) or 'time' in columns:raise InputError('Select existing non-time columns.')
    plt=plotting(cfg);figure,axis=plt.subplots(figsize=(10,6),layout='constrained')
    # Bucket min/max preserves spikes rather than dropping every nth sample.
    bucket=max(1,len(table['rows'])//1000)
    for name in columns:
        index=table['columns'].index(name);selected=set()
        for start in range(0,len(table['rows']),bucket):
            ids=range(start,min(start+bucket,len(table['rows'])))
            selected.update((min(ids,key=lambda i:table['rows'][i][index]),max(ids,key=lambda i:table['rows'][i][index])))
        ids=sorted(selected)
        axis.plot([table['rows'][i][0] for i in ids],[table['rows'][i][index] for i in ids],label=name)
    axis.set_xlabel('Time (s)',parse_math=False);axis.set_ylabel(ylabel,parse_math=False)
    axis.set_title(title or target.name,parse_math=False);axis.grid(alpha=.25);axis.legend()
    return save_figure(cfg,figure,{'type':'motion_plot','source_sha256':hashlib.sha256(bounded_read(target,MAX_RESULT)).hexdigest(),
                       'columns':columns,'source_rows':len(table['rows']),'decimation':'min/max buckets' if bucket>1 else 'none',
                       'in_degrees':table['in_degrees'],'ylabel':ylabel})


def _render_model(cfg,scene):
    plt=plotting(cfg);figure=plt.figure(figsize=(8,7),layout='constrained');axis=figure.add_subplot(projection='3d')
    points=[]
    # Display OpenSim Y-up as the plot's vertical axis; labels retain native axes.
    for joint in scene['joints']:
        a,b=joint['parent'],joint['child'];points.extend((a,b))
        axis.plot([a[0],b[0]],[a[2],b[2]],[a[1],b[1]],color='#234b70',linewidth=3)
    for marker in scene['markers']:
        p=marker['position'];points.append(p);axis.scatter(p[0],p[2],p[1],color='#dc6b32',s=15)
    if not points:raise InputError('Model has no drawable frame origins or markers.')
    spans=[max(p[i] for p in points)-min(p[i] for p in points) for i in range(3)]
    extent=max(max(spans),.1)*.6
    centers=[(max(p[i] for p in points)+min(p[i] for p in points))/2 for i in range(3)]
    axis.set_xlim(centers[0]-extent,centers[0]+extent);axis.set_ylim(centers[2]-extent,centers[2]+extent);axis.set_zlim(centers[1]-extent,centers[1]+extent)
    axis.set_box_aspect((1,1,1));axis.set_xlabel('X (m)');axis.set_ylabel('Z (m)');axis.set_zlabel('Y (m)')
    axis.set_title(scene['name']+' — body frames / markers',parse_math=False)
    return save_figure(cfg,figure,{'type':'native_pose_geometry','model_name':scene['name'],'revision':scene['revision'],'scope':scene['scope']})


def isolated(cfg,operation,parameters):
    from .process_tree import ProcessTree
    with tempfile.TemporaryDirectory(prefix='media-',dir=cfg.temp_root) as name:
        work=Path(name);(work/'scratch').mkdir();(work/'published').mkdir()
        request={'operation':operation,'parameters':parameters,'allowed_roots':[str(r) for r in (*cfg.allowed_roots,cfg.results_root)]}
        (work/'request.json').write_text(json.dumps(request,allow_nan=False),encoding='utf-8')
        tree=ProcessTree();process=None
        try:
            with (work/'media.log').open('wb') as log:
                process=tree.spawn([sys.executable,'-B','-m','opensim_mcp.media_worker',str(work)],cwd=work,
                    env=dict(os.environ,TEMP=str(work),TMP=str(work),PYTHONDONTWRITEBYTECODE='1'),
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
                deadline=time.monotonic()+30
                while process.poll() is None:
                    if time.monotonic()>deadline:raise TimeoutError('Image rendering exceeded 30 seconds.')
                    if (work/'media.log').stat().st_size>1024*1024:raise InputError('Image renderer log limit exceeded.')
                    time.sleep(.05)
                process.wait();tree.terminate()
            if process.returncode:
                raise InputError('Image renderer failed: '+bounded_read(work/'media.log',1024*1024).decode('utf-8',errors='replace')[-4000:])
            result=json.loads(bounded_read(work/'result.json',24000))
            image=Path(result['image_file']);svg=Path(result['svg_file'])
            for path in (image,svg):
                if not path.resolve().is_relative_to((work/'published').resolve()) or not path.is_file() or path.stat().st_size>8*1024*1024:
                    raise InputError('Invalid renderer output.')
            destination=cfg.results_root/('figure-'+uuid.uuid4().hex);destination.mkdir(parents=True)
            shutil.copyfile(image,destination/'figure.png');shutil.copyfile(svg,destination/'figure.svg')
            result.update(image_file=str(destination/'figure.png'),svg_file=str(destination/'figure.svg'))
            (destination/'provenance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            return result
        finally:
            if process and process.poll() is None:tree.terminate();process.wait(timeout=10)
            tree.close()


def plot_motion(cfg,path,columns,title='',ylabel='Value (file units)'):
    return isolated(cfg,'plot',dict(path=path,columns=columns,title=title,ylabel=ylabel))


def render_model(cfg,scene):
    return isolated(cfg,'model',{'scene':scene})


def image_bytes(cfg,path):
    target=local_path(path)
    if target.suffix.lower()!='.png' or not (is_under(target,cfg.results_root) or any(is_under(target,r) for r in cfg.allowed_roots)):
        raise InputError('Image must be an allowed PNG file.')
    data=bounded_read(target,8*1024*1024)
    import io
    from PIL import Image
    with Image.open(io.BytesIO(data)) as picture:
        if picture.format!='PNG' or picture.width*picture.height>16000000:raise InputError('Image type/dimensions exceed limits.')
        picture.verify()
    return data
