"""Real stdio conversion, native wearable readback and independent dynamics.

Only original analytic fixtures; isolated API and temporary result roots.
No persistent user/API/GUI session edits or arbitrary-code MCP calls.
"""
import argparse,asyncio,json,math,os,subprocess,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


def analytic_source():
    # Uniform 2 kg 0.2 x 0.3 x 0.4 m brick, source COM [10,20,30] mm.
    central=[2*(.3**2+.4**2)/12,2*(.2**2+.4**2)/12,2*(.2**2+.3**2)/12]
    c=[.01,.02,.03];m=2.
    matrix=[[central[i]*(1 if i==j else 0)+m*((sum(v*v for v in c) if i==j else 0)-c[i]*c[j])
             for j in range(3)] for i in range(3)]
    return dict(mass=2000.,mass_unit='g',center_of_mass=[10.,20.,30.],length_unit='mm',
        inertia=[matrix[i][j]*(1 if i==j else -1)*1e6 for i in range(3) for j in range(3)],
        inertia_unit='kg_mm2',inertia_reference='source_origin',inertia_convention='positive_products',
        source_frame='analytic brick CAD frame',source_description='Uniform analytic 2 kg brick, 0.2 x 0.3 x 0.4 m; not real hardware')


async def main(report):
    root=Path(__file__).resolve().parents[1];examples=root/'examples'
    # Full arbitrary rotation produces off-diagonal terms to catch sign errors.
    a,b=.4,-.7;ca,sa,cb,sb=math.cos(a),math.sin(a),math.cos(b),math.sin(b)
    rotation=[[ca*cb,-sa,ca*sb],[sa*cb,ca,sa*sb],[-sb,0.,cb]]
    transform=dict(target_frame='analytic device body',rotation_source_to_target=rotation,
                   translation_source_origin_in_target_m=[.1,-.2,.05])
    source=analytic_source();params=StdioServerParameters(command=sys.executable,args=['-B','-m','opensim_mcp.server'],env=dict(os.environ,OPENSIM_MCP_ENABLE_SCRIPTS='0'))
    journal=[]
    async with stdio_client(params) as (reader,writer):
      async with ClientSession(reader,writer) as client:
        await client.initialize();tools={t.name for t in (await client.list_tools()).tools}
        assert 'convert_body_mass_properties' in tools and len(tools)==94
        async def call(name,args):
            response=await client.call_tool(name,args)
            journal.append(dict(tool=name,is_error=bool(response.isError)))
            assert not response.isError,(name,response)
            return response.structuredContent
        converted=await call('convert_body_mass_properties',dict(properties=source,frame_transform=transform))
        body=converted['body_parameters']
        expected=[2*(.3**2+.4**2)/12,2*(.2**2+.4**2)/12,2*(.2**2+.3**2)/12]
        expected_matrix=[[sum(rotation[i][k]*expected[k]*rotation[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
        assert max(abs(converted['inertia_matrix_kg_m2'][i][j]-expected_matrix[i][j]) for i in range(3) for j in range(3))<1e-14
        link=dict(name='analytic_device',parent_frame='/bodyset/block',mesh_path=str(examples/'Geometry/block.obj'),
                  mesh_units='m',joint_type='WeldJoint',**body)
        # This mesh is illustrative, intentionally not a mass-geometry match.
        assembly=await call('assemble_wearable_model',dict(model_path=str(examples/'slider.osim'),links=[link]))
        assert assembly['quality']['reopened_mass_com_inertia_verified']
        actual=assembly['reopened_body_mass_properties'][0]
        assert max(abs(a-b) for a,b in zip(actual['inertia_kg_m2'],body['inertia_kg_m2']))<1e-14
        assert abs(assembly['quality']['added_device_mass_kg']-2)<1e-12
        folder=Path(os.environ['OPENSIM_MCP_RESULTS_ROOT'])/'mass-properties-inputs';folder.mkdir(exist_ok=False,parents=True)
        motion=folder/'acceleration.mot';motion.write_text('Original q=0.5*t*t, acceleration=1 m/s2\nversion=1\nnRows=41\nnColumns=2\ninDegrees=no\nendheader\ntime\tslider_tx\n'+'\n'.join(f'{i/40:.15g}\t{.5*(i/40)**2:.15g}' for i in range(41))+'\n',encoding='utf-8')
        compared=await call('compare_wearable_inverse_dynamics',dict(baseline_model_path=str(examples/'slider.osim'),
             assembly_report_path=assembly['report_file'],coordinates_path=str(motion),no_external_loads=True))
        # Independent parse of the actual output, without relying on the metric
        # label: every interior added-mass generalized force must equal m*a.
        from opensim_mcp.core import read_motion
        table=read_motion(Path(compared['comparison_file']));columns=table['columns']
        baseline_index=columns.index('slider_tx_force_baseline');combined_index=columns.index('slider_tx_force_combined')
        added_values=[row[combined_index]-row[baseline_index] for row in table['rows'][5:-5]]
        assert max(abs(v-2.) for v in added_values)<1e-5,(columns,added_values)
        invalid=dict(source,inertia=[1.,1.,3.,0.,0.,0.],inertia_unit='kg_m2',inertia_reference='center_of_mass')
        rejected=await client.call_tool('convert_body_mass_properties',dict(properties=invalid,frame_transform=transform));assert rejected.isError
    # Independent Simbody-native kinetic energy at a non-principal angular
    # velocity also catches signs that a total-mass-only test would miss.
    payload=report.parent/'native-energy-input.json';payload.write_text(json.dumps(dict(body=body,expected_inertia=expected_matrix)),encoding='utf-8')
    script=report.parent/'native_energy_check.py'
    script.write_text('''import json,sys,opensim as o
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text());b=p['body']
m=o.Model();m.setGravity(o.Vec3(0,0,0))
body=o.Body('test',b['mass_kg'],o.Vec3(*b['mass_center_m']),o.Inertia(*b['inertia_kg_m2']))
joint=o.BallJoint('ball',m.getGround(),o.Vec3(0,0,0),o.Vec3(0,0,0),
                  body,o.Vec3(*b['mass_center_m']),o.Vec3(0,0,0))
m.addBody(body);m.addJoint(joint);s=m.initSystem();w=[.7,-.4,.9]
for i in range(3):joint.upd_coordinates(i).setSpeedValue(s,w[i])
m.realizeVelocity(s)
velocity=body.getVelocityInGround(s);omega=velocity.get(0);v=velocity.get(1)
c=b['mass_center_m'];expected_w=[float(omega.get(i)) for i in range(3)]
cross_c=[[0,-c[2],c[1]],[c[2],0,-c[0]],[-c[1],c[0],0]]
# v_COM = v_origin + omega cross c = v_origin - cross(c)*omega.
vcom=[float(v.get(i))-sum(cross_c[i][j]*expected_w[j] for j in range(3)) for i in range(3)]
expected=.5*sum(expected_w[i]*p['expected_inertia'][i][j]*expected_w[j] for i in range(3) for j in range(3))
expected+=.5*b['mass_kg']*sum(x*x for x in vcom)
actual=m.getMatterSubsystem().calcKineticEnergy(s)
assert abs(actual-expected)<1e-10,(actual,expected)
print(json.dumps(dict(native_kinetic_energy_J=actual,analytic_kinetic_energy_J=expected,opensim_version=o.GetVersionAndDate())))
''',encoding='utf-8')
    native=subprocess.run([os.environ['OPENSIM_MCP_API_PYTHON'],'-B',str(script),str(payload)],check=True,text=True,capture_output=True,timeout=60)
    energy=json.loads(native.stdout.strip().splitlines()[-1])
    result=dict(passed=True,version='1.4.1',tools=len(tools),scripting_enabled=False,
        converted=converted,native_reopened=actual,added_mass_id_force_N=sum(added_values)/len(added_values),
        expected_added_force_N=2.,invalid_inertia_rejected=True,native_energy=energy,
        original_fixture_only=True,scope='Numeric conversion, native stored mass/COM/inertia, analytic slider ID and non-principal rotational kinetic energy. Illustrative mesh; no device/anatomy/contact/assistance/metabolic validation.')
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,tool_count=len(tools),id_delta_N=result['added_mass_id_force_N'],energy=energy)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    asyncio.run(main(a.report.resolve()))
