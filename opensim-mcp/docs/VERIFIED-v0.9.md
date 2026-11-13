# Executed validation — v0.9.0

152 adapter tests passed locally on Windows 11. 73 MCP tools discovered.
Native C3D conversion (mm→m, explicit Z-up rotation, force sign/COP/free moment),
IK analytic displacement and unfiltered ID=-5 N passed. A generated complete
eight-stage muscle pipeline finished through SO/JointReaction. Native RRA and
before/after ID comparison passed, with its actual boundary window reported.

MocoInverse two-mesh synthetic study passed; objective-only agreement is labeled
separately. Doubling explicit muscle strength changed objective 0.04→0.01.
Local official Gait2354 data completed COM-enabled RRA with 54 original muscles
restored, then explicit DGF conversion/reserves and a 0.4–0.5 s muscle inverse
problem at 0.015/0.0075 s mesh intervals. These are native short-window solves,
not full-cycle or physiological validation. No participant inputs are bundled.

Evidence: validation/windows11-v0.9.json; workflow details:
docs/V09_WORKFLOWS.zh-CN.md. Hosted GitHub CI and a clean OS VM were not run.
Prior release evidence remains in docs/VERIFIED-v0.8.md and VERIFIED-v0.8.1.md.
