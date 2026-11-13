"""Isolated native tools for PyPI installations that do not ship opensim-cmd.

Launched with the configured API interpreter, never in the MCP transport
process or the persistent interactive worker. Compatible with CPython 3.8+.
"""
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from worker import bootstrap


def main():
    osim = bootstrap()
    if sys.argv[1:]==['--solver-probe']:
        import json
        model=osim.Model();model.setGravity(osim.Vec3(0));body=osim.Body('probe_body',1.,osim.Vec3(0),osim.Inertia(1.))
        joint=osim.SliderJoint('probe_joint',model.getGround(),osim.Vec3(0),osim.Vec3(0),body,osim.Vec3(0),osim.Vec3(0));joint.updCoordinate().setName('q')
        model.addBody(body);model.addJoint(joint);actuator=osim.CoordinateActuator('q');actuator.setName('probe_drive');actuator.setOptimalForce(1.);model.addForce(actuator);model.initSystem()
        study=osim.MocoStudy();study.set_write_solution(False);problem=study.updProblem();problem.setModelAsCopy(model);problem.setTimeBounds(0.,.1)
        for suffix in ('value','speed'):problem.setStateInfo('/jointset/probe_joint/q/'+suffix,osim.MocoBounds(-1,1),osim.MocoInitialBounds(0),osim.MocoFinalBounds(0))
        problem.setControlInfo('/forceset/probe_drive',osim.MocoBounds(-1,1));problem.addGoal(osim.MocoControlGoal('effort'))
        solver=study.initCasADiSolver();solver.set_parallel(0);solver.set_num_mesh_intervals(2);solver.set_optim_max_iterations(50);solution=study.solve()
        if not solution.success():raise RuntimeError('Native Moco solver probe failed: '+solution.getStatus())
        print(json.dumps(dict(solver_success=True,status=solution.getStatus(),objective=solution.getObjective(),opensim_version=osim.GetVersionAndDate(),scope='Actual tiny native CasADi/IPOPT solve, not symbol detection.')))
        return
    if sys.argv[1:]==['--capabilities']:
        import json,platform
        import numpy
        print(json.dumps(dict(opensim_version=osim.GetVersionAndDate(),python=platform.python_version(),numpy=numpy.__version__,
              moco_track=hasattr(osim,'MocoTrack'),moco_inverse=hasattr(osim,'MocoInverse'),moco_casadi=hasattr(osim,'MocoCasADiSolver'),
              marker_placer=hasattr(osim,'MarkerPlacer'))))
        return
    if sys.argv[1:] == ["--version"]:
        print(osim.GetVersionAndDate())
        return
    if sys.argv[1:]==['extended','request.json']:
        import json
        from extended_runner import run
        request=json.loads(Path('request.json').read_text(encoding='utf-8'))
        result=run(osim,request)
        Path('native-result.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
        return
    if sys.argv[1:] != ["run-tool", "setup.xml"]:
        raise ValueError("Only a generated setup.xml in the staged working directory is supported.")
    root = ET.parse(str(Path.cwd() / "setup.xml")).getroot()
    if root.tag != "OpenSimDocument" or len(root) != 1:
        raise ValueError("Invalid generated tool setup.")
    classes = {
        "InverseKinematicsTool": osim.InverseKinematicsTool,
        "InverseDynamicsTool": osim.InverseDynamicsTool,
        "AnalyzeTool": osim.AnalyzeTool,
    }
    kind = root[0].tag
    if kind not in classes:
        raise ValueError("Unsupported native tool: " + kind)
    tool = classes[kind]("setup.xml")
    if not tool.run():
        raise RuntimeError(kind + " returned false")


if __name__ == "__main__":
    main()
