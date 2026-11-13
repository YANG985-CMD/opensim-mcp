"""Internal protocol only; never exposes arbitrary code or macros as MCP tools."""
import json
import sys
import traceback
import pythoncom
from .cad import CAD, Failure
from .native_batch import NativeBatch

OPERATIONS={'health','connect','list_documents','snapshot','new_document','open_document','box','cylinder','polygon','through_hole','fillet','features','set_dimension','save','export','close','add_component','component_geometry','mate_cylinders','api_lookup','set_component_fixed','add_mate','assembly_status','move_component','check_interference','mass_properties','materials','set_material'}
MUTATIONS={'new_document','box','cylinder','polygon','through_hole','fillet','set_dimension','save','export','close','add_component','mate_cylinders','set_component_fixed','add_mate','move_component','set_material'}
OPERATIONS.add('set_mate_position')
MUTATIONS.add('set_mate_position')
OPERATIONS.update({'add_components','connect_rigid_group','create_joint'})
MUTATIONS.update({'add_components','connect_rigid_group','create_joint'})
OPERATIONS.update({'set_mate_positions','set_dimensions'})
MUTATIONS.update({'set_mate_positions','set_dimensions'})
OPERATIONS.add('scan_motion');MUTATIONS.add('scan_motion')
OPERATIONS.add('set_mate_suppressed');MUTATIONS.add('set_mate_suppressed')
OPERATIONS.update({'organize_assembly','package_assembly'});MUTATIONS.update({'organize_assembly','package_assembly'})
OPERATIONS.add('set_mate_flips');MUTATIONS.add('set_mate_flips')
OPERATIONS.add('set_assembly_pose');MUTATIONS.add('set_assembly_pose')
OPERATIONS.add('close_reference_views');MUTATIONS.add('close_reference_views')
OPERATIONS.add('audit_assembly')
MUTATIONS.add('open_document')
OPERATIONS.add('import_step');MUTATIONS.add('import_step')
OPERATIONS.update({'compare_assemblies','capture_joint_recipe','apply_joint_recipe','verify_package_references'})
MUTATIONS.add('apply_joint_recipe')

def main():
    wire=sys.stdout
    sys.stdout=sys.stderr
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        cad=CAD()
        for line in sys.stdin:
            request={}
            try:
                request=json.loads(line)
                op=request['operation']
                if op not in OPERATIONS: raise Failure('OPERATION','Unsupported operation')
                cad._thread()
                with NativeBatch(None if op in ('connect','health') else cad.sw,cad.scratch):
                    data=getattr(cad,op)(**request['arguments'])
                response={'id':request['id'],'ok':True,'data':data}
            except Failure as e:
                response={'id':request.get('id'),'ok':False,**e.payload}
                response.setdefault('edit_may_be_partial',request.get('operation') in MUTATIONS)
                response.setdefault('retry_automatically',False)
            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                response={'id':request.get('id'),'ok':False,'code':'NATIVE_ERROR','message':str(e),'error_type':type(e).__name__,'edit_may_be_partial':request.get('operation') in MUTATIONS,'retry_automatically':False}
            wire.write(json.dumps(response,ensure_ascii=False,allow_nan=False)+'\n');wire.flush()
            pythoncom.PumpWaitingMessages()
    finally: pythoncom.CoUninitialize()

if __name__=='__main__': main()
