"""Compare oriented STL triangles, allowing verified planar re-triangulation."""
import collections,math,struct
from pathlib import Path


def oriented_triangles(path):
    data=Path(path).read_bytes()
    if len(data)>=84 and len(data)==84+50*struct.unpack_from('<I',data,80)[0]:
        values=[tuple(tuple(round(v,5) for v in struct.unpack_from('<3f',data,84+50*i+12+12*j)) for j in range(3)) for i in range(struct.unpack_from('<I',data,80)[0])]
    else:
        points=[tuple(round(float(v),5) for v in line.split()[1:4]) for line in data.decode('ascii').splitlines() if line.strip().startswith('vertex ')]
        if len(points)%3:raise ValueError('Invalid STL vertex count')
        values=[tuple(points[i:i+3]) for i in range(0,len(points),3)]
    if not values:raise ValueError('Empty STL')
    return [min(t[i:]+t[:i] for i in range(3)) for t in values]


def compare_triangles(old,new,surface_tolerance_mm=0.):
    if not math.isfinite(surface_tolerance_mm) or not 0<=surface_tolerance_mm<=.01:raise ValueError('Explicit surface tolerance must be in 0..0.01 mm')
    ca=collections.Counter(old);cb=collections.Counter(new);a=list((ca-cb).elements());b=list((cb-ca).elements())
    proof={'old_triangles':len(old),'new_triangles':len(new),'exact_oriented_matches':sum((ca&cb).values()),'old_retriangulated_triangles':len(a),'new_retriangulated_triangles':len(b),'quantization_mm':1e-5,'planar_patches':[]}
    if len(a)+len(b)>10000:raise ValueError('Too many nonmatching triangles for bounded planar verification')
    if not a and not b:return {**proof,'equivalent':True,'within_tessellation_tolerance':True,'surface_difference_bound_mm':0.}
    nonplanar=False;surface_bound=0.
    all_tri=[('old',t) for t in a]+[('new',t) for t in b];parent=list(range(len(all_tri)));vertices={}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,(_,t) in enumerate(all_tri):
        for p in t:
            if p in vertices:parent[find(i)]=find(vertices[p])
            else:vertices[p]=i
    groups=collections.defaultdict(lambda:{'old':[],'new':[]})
    for i,(side,t) in enumerate(all_tri):groups[find(i)][side].append(t)
    def boundary(ts):
        edges=collections.Counter()
        for t in ts:
            for i in range(3):
                edge=(t[i],t[(i+1)%3]);rev=edge[::-1]
                if edges[rev]:edges[rev]-=1
                else:edges[edge]+=1
        return +edges
    def cross(t):
        u=[t[1][i]-t[0][i] for i in range(3)];v=[t[2][i]-t[0][i] for i in range(3)]
        return [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    norm=lambda v:math.sqrt(sum(x*x for x in v))
    for rows in groups.values():
        aa=rows['old'];bb=rows['new']
        if not aa or not bb or boundary(aa)!=boundary(bb):raise ValueError('STL patch boundaries/winding changed')
        va={p for t in aa for p in t};vb={p for t in bb for p in t}
        if va!=vb:raise ValueError('STL patch vertices changed')
        normal=cross(aa[0]);nn=norm(normal)
        if nn<1e-10:raise ValueError('Degenerate planar patch')
        normal=[x/nn for x in normal];origin=aa[0][0]
        heights=[sum((p[i]-origin[i])*normal[i] for i in range(3)) for p in va];off=max(abs(v) for v in heights);bound=max(heights)-min(heights);curved=off>1e-4
        if curved and bound>surface_tolerance_mm:raise ValueError('Re-triangulated surface difference bound exceeds explicit tolerance')
        nonplanar|=curved;surface_bound=max(surface_bound,bound);areas=[];projected=[]
        for ts in (aa,bb):
            total=0.;projected_area=0.
            for t in ts:
                c=cross(t);n=norm(c)
                dot=sum(c[i]*normal[i] for i in range(3))
                if n<1e-10 or dot/n<(0.9 if curved else 1-1e-6):raise ValueError('STL patch normal/winding changed')
                total+=.5*n;projected_area+=.5*dot
            areas.append(total);projected.append(projected_area)
        error=abs(areas[0]-areas[1])
        if abs(projected[0]-projected[1])>1e-7 or not curved and error>max(1e-4,areas[0]*1e-6):raise ValueError('STL patch projected area changed')
        # Positive projected triangle orientation plus identical oriented boundary
        # proves both patches cover the same projected region. Each surface is
        # a piecewise-linear height graph over it, within the shared vertex
        # height interval. Pair points at the same projection: this bounds both
        # directed surface distances without claiming identical curved meshes.
        proof['planar_patches'].append({'old_triangles':len(aa),'new_triangles':len(bb),'shared_vertices':len(va),'oriented_boundary_edges':sum(boundary(aa).values()),'maximum_off_plane_mm':off,'area_error_mm2':error,'projected_area_error_mm2':abs(projected[0]-projected[1]),'surface_difference_bound_mm':bound,'curved_patch':curved,'boundary_vertices_and_winding_identical':True})
    return {**proof,'equivalent':not nonplanar,'within_tessellation_tolerance':True,'explicit_surface_tolerance_mm':surface_tolerance_mm,'surface_difference_bound_mm':surface_bound,'scope':'Oriented triangles quantized to 0.00001 mm. Identical patch vertices and oriented boundaries; positive projected triangles and equal projected areas. Curved patches are not claimed identical: their shared height interval bounds bidirectional surface distance. Not printability or strength.'}


def compare_stl(old_path,new_path,surface_tolerance_mm=0.):return compare_triangles(oriented_triangles(old_path),oriented_triangles(new_path),surface_tolerance_mm)
