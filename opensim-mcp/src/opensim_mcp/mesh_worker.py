"""VTK mesh reader in its own process; no VTK/NumPy imports in MCP transport."""
import json,sys
from pathlib import Path
import numpy as np
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
from vtkmodules.vtkIOGeometry import vtkOBJReader,vtkSTLReader
from vtkmodules.vtkFiltersCore import vtkTriangleFilter
from vtkmodules.vtkFiltersSources import vtkCubeSource,vtkSphereSource
from vtkmodules.util.numpy_support import vtk_to_numpy

def main(work):
    request=json.loads((work/'meshes.json').read_text(encoding='utf-8'));result=[];total_points=0;total_triangles=0
    for item in request:
        kind=item['type'];scale=np.asarray(item.get('scale',[1.,1.,1.]),dtype=float)
        if kind=='mesh':
            source=work/item['staged_file'];reader={'.obj':vtkOBJReader,'.stl':vtkSTLReader,'.vtp':vtkXMLPolyDataReader}[source.suffix.lower()]();reader.SetFileName(str(source))
        elif kind=='brick':
            reader=vtkCubeSource();h=item['half_lengths'];reader.SetXLength(2*h[0]);reader.SetYLength(2*h[1]);reader.SetZLength(2*h[2])
        else:
            reader=vtkSphereSource();reader.SetRadius(item.get('radius',1.));reader.SetThetaResolution(24);reader.SetPhiResolution(16)
            if kind=='ellipsoid':scale=scale*np.asarray(item['radii'],dtype=float)
        reader.Update()
        if hasattr(reader,'GetErrorCode') and reader.GetErrorCode():raise ValueError('Mesh reader error: '+str(reader.GetErrorCode()))
        triangles=vtkTriangleFilter();triangles.SetInputConnection(reader.GetOutputPort());triangles.PassLinesOff();triangles.PassVertsOff();triangles.Update();poly=triangles.GetOutput()
        n=poly.GetNumberOfPoints();m=poly.GetNumberOfPolys()
        if not 0<n<=100000 or not 0<m<=200000:raise ValueError('Empty/oversize mesh.')
        total_points+=n;total_triangles+=m
        if total_points>300000 or total_triangles>500000:raise ValueError('Total mesh budget exceeded.')
        points=vtk_to_numpy(poly.GetPoints().GetData()).astype(float)*scale
        cells=vtk_to_numpy(poly.GetPolys().GetData()).reshape(-1,4)
        if not np.all(cells[:,0]==3) or not np.isfinite(points).all() or np.max(np.abs(points))>10000:raise ValueError('Invalid mesh positions/triangles.')
        faces=cells[:,1:].astype(int)
        if faces.min()<0 or faces.max()>=len(points):raise ValueError('Invalid triangle index.')
        result.append({k:v for k,v in item.items() if k not in {'staged_file','scale'}}|{'vertices':points.tolist(),'triangles':faces.tolist()})
    (work/'mesh_result.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main(Path(sys.argv[1]))
