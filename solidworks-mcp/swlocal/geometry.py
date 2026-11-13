"""Pure geometry checks; lengths at the public boundary are millimetres."""
import math


def validate_rigid_transform(values):
    if not isinstance(values,(list,tuple)) or len(values)!=16:raise ValueError('Use a 16-number native rigid transform; SI translation in metres')
    t=[float(x) for x in values]
    if any(not math.isfinite(x) for x in t) or any(abs(x)>5 for x in t[9:12]):raise ValueError('Transform is nonfinite or outside ±5 m')
    if abs(t[12]-1)>1e-8 or any(abs(x)>1e-8 for x in t[13:]):raise ValueError('Scaling and unused transform entries are not permitted')
    for i in range(3):
        for j in range(3):
            dot=sum(t[3*i+k]*t[3*j+k] for k in range(3))
            if abs(dot-(1 if i==j else 0))>1e-6:raise ValueError('Rotation axes must be orthonormal')
    det=t[0]*(t[4]*t[8]-t[5]*t[7])-t[1]*(t[3]*t[8]-t[5]*t[6])+t[2]*(t[3]*t[7]-t[4]*t[6])
    if abs(det-1)>1e-6:raise ValueError('Reflections are not rigid rotations')
    return t


def validate_mate_values(kind,value,minimum,maximum,alignment,lock_rotation,flip,name):
    kinds={'coincident':0,'concentric':1,'perpendicular':2,'parallel':3,'distance':5,'angle':6,'limit_distance':5,'limit_angle':6,'lock':16}
    if kind not in kinds or alignment not in ('aligned','anti_aligned','closest'):raise ValueError('Unsupported mate or alignment')
    if type(lock_rotation)!=bool or type(flip)!=bool:raise ValueError('Mate flags must be boolean')
    if lock_rotation and kind!='concentric':raise ValueError('lock_rotation is only valid for concentric mates')
    if not isinstance(name,str) or len(name)>100 or any(c in name for c in '@\\/\r\n'):raise ValueError('Invalid mate name')
    values=[float(x) for x in (value,minimum,maximum)]
    if any(not math.isfinite(x) for x in values):raise ValueError('Mate values must be finite')
    angle=kind.endswith('angle');limit=kind.startswith('limit_');cap=180 if angle else 5000
    if kind in ('distance','angle','limit_distance','limit_angle'):
        if not 0<=values[0]<=cap:raise ValueError('Native mate distance/angle must be nonnegative and bounded; use offset datums for signed motion')
        if limit and not 0<=values[1]<values[2]<=cap:raise ValueError('Require 0 <= minimum < maximum within native range')
        if limit and not values[1]<=values[0]<=values[2]:raise ValueError('Initial value must lie inside the limits')
    elif any(values):raise ValueError('This mate type does not use numeric values')
    if not limit and (values[1] or values[2]):raise ValueError('Bounds are only accepted for limit mates')
    scale=math.pi/180 if angle else .001
    return {'native_type':kinds[kind],'native_alignment':{'aligned':0,'anti_aligned':1,'closest':2}[alignment],
      'distance':0. if angle else values[0]*scale,'angle':values[0]*scale if angle else 0.,
      'distance_min':values[1]*scale if limit and not angle else 0.,'distance_max':values[2]*scale if limit and not angle else 0.,
      'angle_min':values[1]*scale if limit and angle else 0.,'angle_max':values[2]*scale if limit and angle else 0.}


def incremental_transform(current,translation_mm=None,axis_world=None,angle_deg=0.,pivot_mm=None):
    def vector(v,default,label,cap):
        v=default if v is None else v
        if not isinstance(v,(list,tuple)) or len(v)!=3:raise ValueError(label+' needs exactly three numbers')
        r=[float(x) for x in v]
        if any(not math.isfinite(x) or abs(x)>cap for x in r):raise ValueError(label+' is nonfinite or outside its bound')
        return r
    translation=vector(translation_mm,[0,0,0],'Translation',5000)
    pivot=vector(pivot_mm,[0,0,0],'Pivot',5000)
    angle=float(angle_deg)
    if not math.isfinite(angle) or abs(angle)>360:raise ValueError('Incremental angle must be within ±360 degrees')
    if angle and axis_world is None:raise ValueError('An explicit world rotation axis is required')
    axis=vector(axis_world,[0,0,1],'Axis',1e6);length=math.sqrt(sum(v*v for v in axis))
    if length<1e-12:raise ValueError('Zero rotation axis')
    x,y,z=[v/length for v in axis];c=math.cos(math.radians(angle));s=math.sin(math.radians(angle));t=1-c
    r=[[t*x*x+c,t*x*y-s*z,t*x*z+s*y],[t*x*y+s*z,t*y*y+c,t*y*z-s*x],[t*x*z-s*y,t*y*z+s*x,t*z*z+c]]
    result=list(map(float,current));old=[[current[i*3+j] for i in range(3)] for j in range(3)]
    new=[[sum(r[i][k]*old[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    result[:9]=[new[j][i] for i in range(3) for j in range(3)]
    p=[current[9+i]-pivot[i]/1000 for i in range(3)]
    result[9:12]=[sum(r[i][k]*p[k] for k in range(3))+pivot[i]/1000+translation[i]/1000 for i in range(3)]
    if any(abs(v)>5 for v in result[9:12]):raise ValueError('Resulting position is outside ±5000 mm')
    return result


def relative_component_pose(a,b):
    """B expressed in A, using SW's flattened axis vectors and SI translation."""
    ra=[[float(a[j*3+i]) for j in range(3)] for i in range(3)]
    rb=[[float(b[j*3+i]) for j in range(3)] for i in range(3)]
    rotation=[sum(ra[k][i]*rb[k][j] for k in range(3)) for i in range(3) for j in range(3)]
    delta=[float(b[9+i])-float(a[9+i]) for i in range(3)]
    return rotation+[sum(ra[k][i]*delta[k] for k in range(3)) for i in range(3)]


def coaxial_error(point_a, direction_a, point_b, direction_b):
    """Measure unoriented axis angle and lateral distance, in the input units."""
    def unit(vector):
        length=math.sqrt(sum(float(v)**2 for v in vector))
        if not math.isfinite(length) or length<1e-12:
            raise ValueError('Invalid cylinder axis')
        return [float(v)/length for v in vector]
    a,b=unit(direction_a),unit(direction_b)
    dot=max(-1.,min(1.,abs(sum(a[i]*b[i] for i in range(3)))))
    angle=math.degrees(math.acos(dot))
    delta=[float(point_b[i])-float(point_a[i]) for i in range(3)]
    along=sum(delta[i]*a[i] for i in range(3))
    distance=math.sqrt(sum((delta[i]-along*a[i])**2 for i in range(3)))
    return {'axis_angle_deg':angle,'axis_offset_mm':distance}


def finite_positive(value, label):
    v = float(value)
    if not math.isfinite(v) or not 0 < v <= 5000:
        raise ValueError(f"{label} must be finite, positive and at most 5000 mm")
    return v


def direction_from_bounds(bounds, origin, normal, mode="auto"):
    """Return FeatureCut4 Dir and double-ended flag using signed solid bounds.

    SOLIDWORKS cut defaults opposite the sketch normal; Dir=True reverses it.
    A through cut may span both sides. This never retries an unknown mutation.
    """
    if mode == "positive":
        return True, False
    if mode == "negative":
        return False, False
    points = [(x,y,z) for x in (bounds[0],bounds[3]) for y in (bounds[1],bounds[4]) for z in (bounds[2],bounds[5])]
    signed = [sum((p[i]-origin[i])*normal[i] for i in range(3)) for p in points]
    low, high = min(signed), max(signed)
    tol = 1e-7
    if low >= -tol and high > tol:
        return True, False
    if high <= tol and low < -tol:
        return False, False
    if low < -tol and high > tol:
        return False, True
    raise ValueError("Solid does not extend away from the sketch plane")


def polygon_area(vertices):
    if not 3 <= len(vertices) <= 128:
        raise ValueError("A polygon needs 3 to 128 vertices")
    pts = [(float(p[0]),float(p[1])) for p in vertices]
    if any(not math.isfinite(v) or abs(v)>5000 for p in pts for v in p):
        raise ValueError("Polygon coordinates must be finite and within 5000 mm")
    if len(set(pts)) != len(pts):
        raise ValueError("Duplicate polygon vertices")
    def orient(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def between(a,b,c):
        return min(a[0],b[0])-1e-9<=c[0]<=max(a[0],b[0])+1e-9 and min(a[1],b[1])-1e-9<=c[1]<=max(a[1],b[1])+1e-9
    def intersects(a,b,c,d):
        o=[orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)]
        return (o[0]*o[1]<0 and o[2]*o[3]<0) or any(abs(v)<1e-9 and between(*triple) for v,triple in zip(o,[(a,b,c),(a,b,d),(c,d,a),(c,d,b)]))
    n=len(pts)
    for i in range(n):
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1): continue
            if intersects(pts[i],pts[(i+1)%n],pts[j],pts[(j+1)%n]):
                raise ValueError("Self-intersecting polygon")
    area=abs(sum(pts[i][0]*pts[(i+1)%n][1]-pts[(i+1)%n][0]*pts[i][1] for i in range(n)))/2
    if area<1e-6:
        raise ValueError("Degenerate polygon")
    return pts, area
