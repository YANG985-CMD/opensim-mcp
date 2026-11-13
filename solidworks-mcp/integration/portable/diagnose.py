"""Check a Codex stdio entry and its live MCP tools without editing CAD."""
import argparse
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tomllib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def probe(entry, attach):
    if not entry.get("enabled", True):
        raise ValueError("solidworks-mcp is disabled in this Codex configuration")
    command = entry.get("command", "")
    if not Path(command).is_file():
        raise ValueError(f"MCP interpreter not found: {command}. Use the entry generated on this PC.")
    if entry.get("cwd") and not Path(entry["cwd"]).is_dir():
        raise ValueError("MCP working directory no longer exists. Regenerate the Codex entry.")
    for arg in entry.get("args", ()):
        if arg.lower().endswith("launch.py") and not Path(arg).is_file():
            raise ValueError(f"MCP launcher not found: {arg}. Regenerate the Codex entry.")

    server = StdioServerParameters(
        command=command, args=entry.get("args", []), cwd=entry.get("cwd"), env=entry.get("env")
    )
    timeout = timedelta(seconds=30)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timeout) as session:
            info = await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            visible = names.intersection(entry.get("enabled_tools", names))
            visible.difference_update(entry.get("disabled_tools", []))
            required = {"sw_health", "sw_connect", "sw_documents", "sw_find_tools"}
            if not required.issubset(visible):
                raise ValueError("Missing from Codex tool list: " + ", ".join(sorted(required - visible)))
            health = await session.call_tool("sw_health")
            if health.isError:
                raise ValueError(health.content[0].text)
            data = health.structuredContent or json.loads(health.content[0].text)
            result = {"server": info.serverInfo.name, "tools": len(names),
                      "codex_visible_tools": len(visible), "health": data}
            if not data.get("type_library_exists", True):
                result["status"] = "TYPELIB_MISSING"
            elif attach:
                attached = await session.call_tool("sw_connect", {"start_if_needed": False})
                result["status"] = "ATTACH_FAILED" if attached.isError else "ATTACHED"
                result["attach"] = attached.structuredContent or attached.content[0].text
            else:
                result["status"] = "MCP_READY"
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("mcp-codex.toml"))
    parser.add_argument("--connect", action="store_true", help="Try attaching to an already running SOLIDWORKS")
    args = parser.parse_args()
    try:
        config = tomllib.loads(args.config.read_text(encoding="utf-8-sig"))
        entry = config.get("mcp_servers", {}).get("solidworks-mcp")
        if not entry:
            raise ValueError("No solidworks-mcp entry in this configuration")
        result = asyncio.run(probe(entry, args.connect))
    except Exception as error:
        result = {"status": "MCP_CHECK_FAILED", "error": repr(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("MCP_READY", "ATTACHED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
