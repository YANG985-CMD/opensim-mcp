import json
from pathlib import Path

def run(osim,p):
    original=osim.Model('model.osim');original.initSystem();count=original.getMuscles().getSize()
    before={original.getMuscles().get(i).getName():original.getMuscles().get(i).getConcreteClassName() for i in range(count)}
    processor=osim.ModelProcessor('model.osim')
    if p['replace_muscles']:processor.append(osim.ModOpReplaceMusclesWithDeGrooteFregly2016())
    if p['ignore_tendon_compliance']:processor.append(osim.ModOpIgnoreTendonCompliance())
    if p['ignore_passive']:processor.append(osim.ModOpIgnorePassiveFiberForcesDGF())
    model=processor.process();model.initSystem();model.printToXML('model.osim')
    outputs=['model.osim']
    if p['definitions']:
        from native_profiles import configure_actuators
        configured=configure_actuators(osim,p);outputs=configured['outputs']
    reopened=osim.Model('model.osim');reopened.initSystem()
    after={reopened.getMuscles().get(i).getName():reopened.getMuscles().get(i).getConcreteClassName() for i in range(reopened.getMuscles().getSize())}
    if set(before)!=set(after):raise ValueError('Muscle identities changed unexpectedly.')
    quality=dict(native_reopened=True,muscles_before=before,muscles_after=after,explicit_reserves_added=len(p['definitions']),
        muscle_model_changed=p['replace_muscles'],tendon_compliance_ignored=p['ignore_tendon_compliance'],passive_fiber_force_ignored=p['ignore_passive'])
    Path('moco_model.json').write_text(json.dumps(quality,indent=2),encoding='utf-8');outputs.append('moco_model.json')
    return dict(outputs=outputs,quality=quality,opensim_version=osim.GetVersionAndDate(),scope='Explicit model-class/physics transformations on a copy. Revalidate muscle properties and output forces; no claim of physiological equivalence.')
