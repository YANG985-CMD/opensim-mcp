# Executed Windows validation — v0.7.0

112 adapter tests passed. Actual API 4.6 MocoTrack and MocoInverse native solves
succeeded. Static slider tracking RMS 7.74e-9 m; inverse actuator objective zero;
muscle inverse objective 0.04, with explicit 5 N external load 0.0225.
90-degree rotational reference converted correctly to rad; RMS 4.50e-8 rad,
zero sampled state/control bound violation. These are synthetic analytic checks.
No human Moco study or mesh convergence study was executed.
Evidence: validation/windows11-v0.7.json. Prior evidence: docs/VERIFIED-v0.6.md.
GUI bridge remains 0.4; hosted CI not executed.
