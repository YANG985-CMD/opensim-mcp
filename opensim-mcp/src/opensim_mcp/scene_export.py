"""Native pose scene JSON and self-contained SVG/HTML projection viewer."""
from html import escape
import json
import math
import uuid

from .core import InputError


def export_scene(cfg,scene):
    points=[]
    for joint in scene.get('joints',[]):points.extend([joint['parent'],joint['child']])
    points.extend(m['position'] for m in scene.get('markers',[]))
    if not points or len(points)>20000 or any(len(p)!=3 or any(type(v) not in {int,float} or not math.isfinite(v) for v in p) for p in points):raise InputError('Invalid/empty native pose geometry.')
    folder=cfg.results_root/('scene-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    metadata={**scene,'units':'m','coordinate_system':'OpenSim X/Y/Z; Y up','surface_meshes_included':False}
    (folder/'scene.json').write_text(json.dumps(metadata,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    # Three orthogonal projections retain all 3D coordinates without external viewer libraries/scripts.
    svgs=[]
    for a,b,title in [(0,1,'XY'),(2,1,'ZY'),(0,2,'XZ')]:
        minimum=[min(p[i] for p in points) for i in range(3)];maximum=[max(p[i] for p in points) for i in range(3)]
        span=max(maximum[a]-minimum[a],maximum[b]-minimum[b],.1);cx=(maximum[a]+minimum[a])/2;cy=(maximum[b]+minimum[b])/2
        def xy(p):return (250+400*(p[a]-cx)/span,250-400*(p[b]-cy)/span)
        svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500"><rect width="500" height="500" fill="#f3f6fa"/>',
             '<text x="20" y="30" font-family="sans-serif" font-size="20">'+title+' (m; axes proportional)</text>']
        for joint in scene.get('joints',[]):
            x,y=xy(joint['parent']);u,v=xy(joint['child']);svg.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#234b70" stroke-width="4"><title>%s</title></line>'%(x,y,u,v,escape(joint['name'])))
        for marker in scene.get('markers',[]):
            x,y=xy(marker['position']);svg.append('<circle cx="%g" cy="%g" r="4" fill="#d65f32"><title>%s</title></circle>'%(x,y,escape(marker['name'])))
        svg.append('</svg>');text=''.join(svg);(folder/(title+'.svg')).write_text(text,encoding='utf-8');svgs.append(text)
    html='<!doctype html><html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Native pose</title><style>body{font:16px system-ui;margin:30px}main{display:flex;flex-wrap:wrap}svg{width:32%;min-width:300px}pre{white-space:pre-wrap}</style><h1>'+escape(scene['name'])+'</h1><p>Native 3D body-frame/marker coordinates; meters. Three orthogonal projections, no surface meshes.</p><main>'+''.join(svgs)+'</main><details><summary>Native scene coordinates</summary><pre>'+escape(json.dumps(metadata,ensure_ascii=False,indent=2))+'</pre></details></html>'
    (folder/'scene.html').write_text(html,encoding='utf-8')
    return {'scene_file':str(folder/'scene.json'),'html_file':str(folder/'scene.html'),'svg_files':[str(folder/(t+'.svg')) for t in ['XY','ZY','XZ']],
            'revision':scene['revision'],'units':'m','scope':metadata['scope']}
