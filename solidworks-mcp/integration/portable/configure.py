"""Generate local client entries and the portable launcher's settings."""
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    typelib, output, runtime = (Path(value).resolve() for value in sys.argv[1:])
    output.mkdir(parents=True, exist_ok=True)
    command = Path(sys.executable).resolve().as_posix()
    args = ["-B", "-u", (root / "launch.py").as_posix()]
    cwd = root.as_posix()
    settings = {
        "SWLOCAL_TYPELIB": typelib.as_posix(),
        "SWLOCAL_OUTPUT": output.as_posix(),
        "SWLOCAL_TEMP": runtime.as_posix(),
        "SWLOCAL_YEAR": "2025",
        "SWLOCAL_TIMEOUT": "120",
        "PYTHONIOENCODING": "utf-8",
    }
    (root / "bridge-settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "[mcp_servers.solidworks-mcp]",
        f"command = {json.dumps(command, ensure_ascii=False)}",
        f"args = {json.dumps(args, ensure_ascii=False)}",
        f"cwd = {json.dumps(cwd, ensure_ascii=False)}",
        "enabled = true",
        "startup_timeout_sec = 120",
        "tool_timeout_sec = 150",
        "",
    ]
    (root / "mcp-codex.toml").write_text("\n".join(lines), encoding="utf-8")
    harness = {"solidworks-mcp": {
        "transport": "stdio", "command": command, "args": args, "cwd": cwd,
        "toolCallTimeoutMs": 150000,
    }}
    (root / "mcp-harness.json").write_text(
        json.dumps(harness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
