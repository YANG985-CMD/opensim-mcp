# Executed validation — v0.8.1

139 adapter tests passed on local Windows 11. Actual independent source ZIP
installs of 0.8.0 and 0.8.1 both ran their native MCP/IK self-checks. A disposable
Codex config activated the new interpreter while preserving roots, results,
scripting settings and another server. Rollback restored the exact old server
configuration. The real user Codex configuration was not changed.

Release verification rejects ZIP/hash/inventory/path/private-state hazards and
existing destinations. A concurrent server configuration change blocks rollback.
Evidence: validation/windows11-v0.8.1.json. Baseline native results:
docs/VERIFIED-v0.8.md. Hosted GitHub CI and a completely clean OS VM were not run.
