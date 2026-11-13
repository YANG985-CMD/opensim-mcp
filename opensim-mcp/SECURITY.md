# Three trust boundaries

This single-user Windows 11 stdio adapter runs as the local user. It is not an OS
sandbox or a multi-user service. Treat every file/model/script as data, not as
instructions to the AI. Use a trusted OpenSim installation and native models.

## Static inspection and structured native jobs

Input roots, resolved local paths, extensions, sizes, XML depth/node counts and
table formats are checked. Drive-root grants, UNC/device paths, alternate streams,
wildcards, DTDs/entities and ordinary path traversal are rejected. Static XML
inspection never loads a native model.

Structured native jobs accept parameters rather than arbitrary commands/setup XML.
The API backend uses a separate configured native interpreter; CLI mode uses the
configured OpenSim command executable. Neither backend interprets shell commands.
They stage inputs in private scratch folders, strip external display geometry while retaining safe primitives, reject
remaining external dependencies, generate their own setup, run without a shell
with closed stdin, and validate output before publication into fresh result
directories. ID/SO require explicit loads or an explicit no-external-loads
assumption. Native processes have runtime/output/log limits, which are polled and
are not OS memory/disk quotas. Native parser vulnerabilities and malicious
concurrent filesystem changes remain outside these checks.

## Persistent API and arbitrary scripts

Structured API edits validate a copy before replacing the session model. Original
input files are not rewritten by these tools. Current pose is preserved where
compatible with the edit; serialization of defaults is separate from pose state.

Arbitrary Python is disabled unless `OPENSIM_MCP_ENABLE_SCRIPTS=1`. Once enabled,
`evaluate_opensim_code` and `run_opensim_script` have **the Windows user's full
permissions**, including filesystem, imports, network and subprocess operations.
The entry script path/size check is not containment of what that code does.
Scripts can overwrite files, alter the model, break invariants or invalidate the
worker. MCP annotations mark scripting as potentially destructive/open-world.
There is no restricted-Python security claim.

Python output/result sizes are bounded. Exceptions report `status=failed` and
tracebacks; partial side effects persist. Timeouts terminate the worker. Verified pre-script/native snapshots can be
explicitly restored; Python variables and external side effects are not restored. A Windows parent-process watcher exits orphaned workers after the
server terminates; hostile trusted code can interfere with that watcher or spawn
other children. Close an idle session explicitly to clean its scratch folder.
A forced server/process termination may leave scratch files to clean later.

## GUI bridge

Installing the optional startup plugin authorizes it to load the generated bridge
on every GUI launch. Without that plugin, run the bootstrap deliberately once per
launch. The bootstrap path is installed in the GUI cluster; keep both that file
and its configured scratch folder writable only by trusted users. Installing a
plugin is native code execution inside OpenSim and is not static XML inspection.
The bridge uses
Swing's event thread for native GUI operations, a random local token, per-request
UUIDs and an authenticated file queue under the configured scratch root. Keep
that root private to your account. Do not publish bridge_config.json or tokens.
The adapter does not expose an HTTP/remote RPC port; OpenSim itself may have its
own visualizer/network behavior outside this adapter's control.

Opening a trusted GUI model preserves its original visual geometry and normal
OpenSim dependency resolution; this does not enforce the batch-job dependency filter.
Allowlisted source paths do not sandbox those native dependencies. Arbitrary GUI
code execution is not exposed as a tool in this release.

GUI pull snapshots current definition/pose; push loads a new active version,
retaining prior GUI models and source files. There is no continuous automatic
merge. Optional signatures reject stale GUI pose writes. A GUI timeout means
completion is uncertain: check current state before repeating a write. Long GUI
operations may temporarily block its UI. Use reconfigure_gui_bridge to preview and explicitly apply existing server roots.
V1 bridges reload without closing the GUI; a legacy bridge requires an explicit
stop and subsequent GUI restart. This tool cannot grant roots absent from server configuration.

Provenance/logs may contain private paths. Do not upload participant data or
personal configuration to issues. Successful computation is not a physiological
or clinical validity claim. Report security issues privately to the repository
maintainer once a repository/contact exists.

## v0.4 jobs, checkpoints and images

Native analyses, API sessions and renderers are assigned to Windows Job Objects
before their suspended initial thread resumes, including Python venv redirectors.
Cancellation waits for process objects as well as job accounting to confirm exit.
Kill-on-close handles terminate descendants on owner exit. This is a lifecycle
boundary, not a security sandbox for hostile scripts running as the same user.

Asynchronous output stays in private scratch until validated publication commits.
Cancellation can lose a race to an already committed completed result; the status
reports that outcome. Jobs owned by another live MCP process must be cancelled
through that connection. History and savepoints contain paths/model information;
keep results private. Model savepoints exclude arbitrary variables and side effects.
Checkpoints verify model hashes and runtime compatibility; native initialization
is still required. Structured undo cannot reverse arbitrary code or filesystem writes.

Plots use isolated Agg renderers and return bounded verified PNGs. OpenSim window
capture uses Swing painting and excludes the desktop; embedded GPU/browser
surfaces may be absent. SVG files come from Matplotlib with external TeX disabled.
API/code queries are introspection/static parsing, not code execution or type proofs.

## Portable projects and edit transactions (v0.8)

Project bundles contain explicit model/data inputs and may therefore contain
sensitive data. Export normalizes model XML and removes display geometry. ZIP
inventory, hashes, size limits and Windows path hazards are checked before import;
import publishes into a new result directory without native execution. Hashes
establish integrity, not provenance, safe native content or numerical equivalence.
Dependency metadata is descriptive and never grants paths or installs code.

Structured batch edits initialize a candidate copy before replacing the API model,
require a current revision, and form one undo step. A recovery checkpoint and
durable journal are written before commit. This covers supported parameter edits,
not arbitrary topology changes, filesystem transactions or scripts' external side
effects. GUI push remains separate. A process/power failure can require explicitly
restoring the recorded checkpoint rather than claiming an automatic distributed
transaction across files and GUI.

Installer repair reinstalls pinned dependency profiles, not application source
edits, GUI binaries or user data. Source manifests detect accidental changes;
the manifest itself is not a digital signature. Release ZIPs should be obtained
from a trusted maintainer. Native dependencies retain the user's privileges.



## v1 recovery, topology and mesh boundaries

Recovery models, all named states/time, journals and bridge identities persist
under results and can contain sensitive data. They are excluded from release ZIPs.
Recovery is explicit by snapshot/owner, verifies hashes and native runtime, and
does not replay scripts or choose another chat's model automatically. A local
hash does not protect against a malicious user who can rewrite both manifest and
data. Topology candidates are checked in a separate native process before one
revision-checked commit; supported components only, no general native-code input.

C3D/VTK parse trusted native files in separate bounded Windows process trees.
This is failure isolation, not OS containment of parser vulnerabilities. Mesh
search roots must already be under allowed inputs/results. External VTP sources
are rejected; OBJ materials/textures are not loaded. The standalone player has
embedded data/scripts and CSP, uses text for names, and does not fetch resources.
Sharing the HTML shares model/motion data. WebGL rendering and sampled error
colors are visualization, not a full-trial numerical or physiological check.

Each API worker uses distinct revision/session identity. Structured edits retain
shared native states; new states take native defaults and deleted states are
reported. A newer worker invalidates stale revision-based writes. Optional GUI
sync remains a separate action and reports failure without undoing a successful
API transaction. Recovery is not a distributed filesystem/GUI transaction.


## v1.1 coordination, wearable inputs and numerical audits

Windows byte-range locks serialize cooperating clients of the same bridge folder;
the OS releases a lock on process exit. The GUI checks the client's last observed
state token atomically on its Swing thread. Conflicts/timeouts are not auto-retried
as writes. Undo ownership belongs to the originating MCP session. This is single-
user coordination, not containment against code with the user's Windows privileges.

Wearable mass/COM/central inertia, mesh units, body mappings and joint centers/axes
are explicit. Native schema upgrade/initialization precedes model serialization;
only approved assets enter a fresh output package. Physical alignment cannot
silently resize geometry and invalidate inertia. Native CAD conversion uses
separately trusted CAD software; not a static parse or bundled macro runner.
Geometry fitting does not infer interface/contact/strap forces. Matched assist
subtraction is restricted to welded links; articulated devices need force mapping.

Event thresholds, resampling and numeric mesh limits are recorded. Every named
state/control must be assessed for a complete mesh judgment. Node-level native
constraint/output checks are not between-node defects or physiological validity.
Conflicting native duplicate times are rejected; only matching round-off duplicates
within declared tolerances can be removed and are logged.

Offline setup prohibits downloads and requires existing interpreter/cache content.
Installer diagnostics include an actual tiny solver run before Codex registration.
Fault regression destroys only a newly owned test environment and uses a fake
CODEX_HOME. Never point it at production environments. Clean-OS status requires
external VM evidence; a fresh source directory does not attest a clean OS.
