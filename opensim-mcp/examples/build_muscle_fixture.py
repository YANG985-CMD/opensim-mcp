"""Run with run_opensim_script after enabling trusted scripting.

Creates an original analytic one-muscle model and a static 11-frame motion in
output_dir (a variable you set in the API session). No human data are used.
"""
from pathlib import Path

target = Path(output_dir)
target.mkdir(parents=True, exist_ok=True)
model = osim.Model()
model.setName("mcp_muscle_slider")
model.setGravity(osim.Vec3(-10, 0, 0))
body = osim.Body("block", 2.0, osim.Vec3(0), osim.Inertia(1))
joint = osim.SliderJoint("slider", model.getGround(), osim.Vec3(0), osim.Vec3(0),
                         body, osim.Vec3(0), osim.Vec3(0))
joint.updCoordinate().setName("slider_tx")
joint.updCoordinate().setRangeMin(-0.1)
joint.updCoordinate().setRangeMax(0.1)
model.addBody(body)
model.addJoint(joint)
muscle = osim.Millard2012EquilibriumMuscle("puller", 100, 0.6, 0.4, 0)
muscle.set_ignore_tendon_compliance(True)
muscle.set_ignore_activation_dynamics(True)
muscle.addNewPathPoint("origin", model.getGround(), osim.Vec3(1, 0, 0))
muscle.addNewPathPoint("insertion", body, osim.Vec3(0, 0, 0))
model.addForce(muscle)
model.finalizeConnections()
state = model.initSystem()
model.printToXML(str(target / "muscle_slider.osim"))
lines = ["SyntheticStaticMotion", "nRows=11", "nColumns=2", "inDegrees=no", "endheader", "time\tslider_tx"]
lines += ["%.1f\t0" % (i / 10.0) for i in range(11)]
(target / "muscle_slider_static.mot").write_text("\n".join(lines) + "\n", encoding="utf-8")
load_lines = ["SyntheticAssistForce", "nRows=11", "nColumns=10", "endheader",
              "time\tassist_vx\tassist_vy\tassist_vz\tassist_px\tassist_py\tassist_pz\tassist_tx\tassist_ty\tassist_tz"]
load_lines += ["%.1f\t5\t0\t0\t0\t0\t0\t0\t0\t0" % (i / 10.0) for i in range(11)]
(target / "muscle_slider_loads.sto").write_text("\n".join(load_lines) + "\n", encoding="utf-8")
result = {"model": str(target / "muscle_slider.osim"), "mass_kg": 2,
          "gravity_x_m_per_s2": -10, "expected_id_force_N": 20,
          "expected_muscle_force_N": 20, "expected_muscle_path_length_m": 1,
          "expected_translational_moment_arm": 1}
