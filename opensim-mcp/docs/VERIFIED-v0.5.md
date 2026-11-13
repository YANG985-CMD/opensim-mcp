# Executed validation — v0.5.0

Windows 11 x64, OpenSim API 4.6-2026-06-22-85aaf64, 2026-10-28.
92 adapter tests passed. A real stdio connection discovered 52 tools and passed
the original native v0.4 workflows, images, checkpoint/undo, async cancellation
and history restart regression. GUI bridge is unchanged at 0.4; no GUI update in this version.

The seven-stage project executed scale, IK, independent marker fit, ID,
JointReaction, static optimization and muscle geometry. Repeat reused all seven;
changed threshold reused all; a tampered output triggered recomputation;
native failure retained a valid prefix; cancellation stopped native Moco and
retained only the completed scaling stage, which a later run reused.

Official installed Gait2354 measured force-plate pipeline: marker RMS
0.0219965228 m; residual force RMS 52.9397181 N, 0.07435742 body-weight fraction.
The illustrative 0.05 BW limit produces needs_review. These thresholds are
software examples, not clinical acceptance criteria. Participant inputs are not redistributed.
Self-contained HTML, Markdown, JSON and PNG/SVG produced; synthetic curve visually inspected.

Machine-readable evidence: validation/windows11-v0.5.json.
Prior GUI/cross-version evidence: docs/VERIFIED-v0.4.md.
Hosted CI, arbitrary human studies, future GUI distributions and clinical validity remain unverified.
