from types import SimpleNamespace
import pytest
from opensim_mcp.native_animation import muscle_path_points

class Vector:
    def __init__(self,*values):self.values=values
    def get(self,index):return self.values[index]

class Array:
    def __init__(self,values):self.values=values
    def getSize(self):return len(self.values)
    def get(self,index):return self.values[index]

class Point:
    def __init__(self,*values):self.location=Vector(*values)
    def getLocationInGround(self,state):return self.location

class Wrap(Point):
    def __init__(self,points):self.points=Array([Vector(*v) for v in points])
    def getWrapPath(self,state):return self.points
    def getParentFrame(self):return self
    def findStationLocationInGround(self,state,point):return Vector(point.get(0)+10,point.get(1)+20,point.get(2)+30)

OSIM=SimpleNamespace(PathWrapPoint=SimpleNamespace(safeDownCast=lambda p:p if isinstance(p,Wrap) else None))
def sample(points,**kwargs):
    path=SimpleNamespace(getCurrentPath=lambda state:Array(points))
    return muscle_path_points(OSIM,path,None,**kwargs)

def test_wrap_surface_is_transformed_to_ground_and_coincident_endpoints_are_removed():
    assert sample([Point(10,20,30),Wrap([(0,0,0),(1,0,0),(1,1,0)]),Point(11,21,30),Point(12,21,30)])==[
        [10,20,30],[11,20,30],[11,21,30],[12,21,30]]

def test_native_active_points_are_used_without_inventing_conditional_or_fixed_points():
    assert sample([Point(1,2,3),Point(4,5,6)])==[[1,2,3],[4,5,6]]

@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_nonfinite_muscle_locations_are_rejected(value):
    with pytest.raises(ValueError,match='Nonfinite'):sample([Point(0,0,0),Point(value,0,0)])

def test_large_wrap_surface_is_rejected_before_sampling_and_degenerate_paths_fail():
    with pytest.raises(ValueError,match='budget'):sample([Point(0,0,0),Wrap([(i,0,0) for i in range(10)])],max_points=5)
    with pytest.raises(ValueError,match='distinct'):sample([Point(0,0,0),Point(0,0,0)])
