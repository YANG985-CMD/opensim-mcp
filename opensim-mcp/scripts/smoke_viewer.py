"""Native two-body mesh animation and comparison, without changing live API pose."""
import argparse,json,math
from pathlib import Path
from opensim_mcp.core import Settings
from opensim_mcp.session import ApiSession
from opensim_mcp.checkpoints import Checkpoints
from opensim_mcp.topology import apply_topology
from opensim_mcp.viewer import export_animation

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);a=p.parse_args();cfg=Settings.from_env()
    root=Path(__file__).resolve().parents[1]/'examples';api=ApiSession(cfg)
    try:
        loaded=api.load(str(root/'slider.osim'))
        edit=apply_topology(cfg,api,Checkpoints(cfg,api),[
            dict(op='add_body',name='link',mass=1.,mass_center=[0.,0.,0.],inertia=[.01,.01,.01,0.,0.,0.],geometry={'type':'brick','half_lengths':[.025,.15,.025],'color':[.25,.6,.75]}),
            dict(op='add_joint',name='hinge',joint_type='PinJoint',parent_frame='/bodyset/block',child_body='link',location_in_parent=[0.,.2,0.],coordinate={'name':'link_angle','range':[-1.4,1.4],'default_value':0.}),
            dict(op='add_marker',name='Tip',parent_frame='/bodyset/link',location=[0.,.15,0.])],loaded['revision'],False)
        folder=cfg.results_root/'viewer-inputs';folder.mkdir(parents=True,exist_ok=True)
        def motion(path,offset,amplitude):
            text='Native visual regression\nversion=1\nnRows=31\nnColumns=3\ninDegrees=no\nendheader\ntime\tslider_tx\tlink_angle\n'
            path.write_text(text+'\n'.join(f'{i/30:.12g}\t{.1*i/30+offset:.12g}\t{amplitude*math.sin(math.pi*i/30):.12g}' for i in range(31))+'\n',encoding='utf-8')
        first=folder/'motion.mot';other=folder/'comparison.mot';motion(first,0.,1.2);motion(other,.03,1.)
        api.call('pose',dict(coordinates={'slider_tx':.025,'link_angle':.1},time=.25));before=api.call('native_state')
        result=export_animation(cfg,api,str(first),geometry_model_path=str(root/'slider_mesh.osim'),comparison_motion_path=str(other),max_frames=31)
        after=api.call('native_state');assert before['states']==after['states'] and before['time']==after['time'] and before['revision']==after['revision']
        scene=json.loads(Path(result['scene_file']).read_text(encoding='utf-8'));assert result['mesh_count']==2 and len(scene['frames'])==31
        m=scene['frames'][15]['transforms']['/bodyset/block'];assert abs(m[12]-.05)<1e-10
        assert abs(scene['frames'][15]['coordinate_values']['link_angle']-1.2)<1e-10
        assert abs(scene['frames'][15]['marker_errors_m']['M1']-.03)<1e-8
        assert result['comparison_included'] and result['marker_errors_included']
        result.update(passed=True,api_full_state_unchanged=True,native_translation_and_rotation_verified=True,comparison_marker_distance_verified=True)
        a.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:api.close()

if __name__=='__main__':main()
