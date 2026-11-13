"""Native muscle parameters and a serialization-based physics identity."""
import hashlib,json,math
from pathlib import Path
from xml.etree import ElementTree as ET

def fingerprint(model):
    root=ET.fromstring(model.dump())
    ignored={'attached_geometry','VisibleObject','FrameGeometry','Appearance','credits','publications'}
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag in ignored:parent.remove(child)
    for node in root.iter():
        node.text=(node.text or '').strip() or None;node.tail=None
    return hashlib.sha256(ET.tostring(root,encoding='utf-8')).hexdigest()

def metadata(osim,parameters):
    model=osim.Model('model.osim');model.initSystem();muscles={}
    if model.getMuscles().getSize()>300:raise ValueError('At most 300 muscles are supported.')
    for i in range(model.getMuscles().getSize()):
        m=model.getMuscles().get(i)
        entry=dict(max_isometric_force_N=float(m.getMaxIsometricForce()),optimal_fiber_length_m=float(m.getOptimalFiberLength()),
                   tendon_slack_length_m=float(m.getTendonSlackLength()),pennation_angle_rad=float(m.getPennationAngleAtOptimalFiberLength()))
        if any(not math.isfinite(v) for v in entry.values()) or any(entry[k]<=0 for k in ('max_isometric_force_N','optimal_fiber_length_m')):raise ValueError('Invalid native muscle parameters.')
        muscles[m.getName()]=entry
    data=dict(muscles=muscles,physics_signature=fingerprint(model),coordinate_types={model.getCoordinateSet().get(i).getName():model.getCoordinateSet().get(i).getMotionType() for i in range(model.getCoordinateSet().getSize())})
    Path('muscle_metadata.json').write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
    return dict(outputs=['muscle_metadata.json'],muscle_count=len(muscles),opensim_version=osim.GetVersionAndDate())
