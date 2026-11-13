"""Real stdio MCP client. With --run-ik, solve and verify the synthetic slider via MCP."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from opensim_mcp.core import read_motion


async def main(examples: Path, run: bool) -> None:
    params = StdioServerParameters(command=sys.executable,
                                  args=["-B", "-m", "opensim_mcp.server"], env=dict(os.environ))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"get_environment", "inspect_model", "read_motion_result", "run_inverse_kinematics"} <= names, names
            output = {"protocol_version": initialized.protocolVersion, "tools": sorted(names)}
            async def call(name, args):
                result = await session.call_tool(name, args)
                if result.isError:
                    raise RuntimeError(result.model_dump_json())
                assert isinstance(result.structuredContent, dict), result
                return result.structuredContent
            output["environment"] = await call("get_environment", {})
            output["inspection"] = await call("inspect_model", {"model_path": str(examples / "slider.osim")})
            assert output["inspection"]["counts"]["coordinates"] == 1
            denied = await session.call_tool("inspect_model", {"model_path": str(examples.parent / "outside.osim")})
            assert denied.isError, "MCP must propagate input-policy failure as a tool error"
            output["rejection_checked"] = True
            if run:
                result = await call("run_inverse_kinematics", {"model_path": str(examples / "slider.osim"),
                                                             "marker_path": str(examples / "slider.trc")})
                table = read_motion(Path(result["motion_file"]))
                index = table["columns"].index("slider_tx")
                error = max(abs(row[index] - .1*row[0]) for row in table["rows"])
                assert len(table["rows"]) == 11 and error <= 1e-6, error
                result["analytic_max_error_m"] = error
                output["result_readback"] = await call("read_motion_result", {"result_path": result["motion_file"], "preview_rows": 2})
                assert output["result_readback"]["row_count"] == 11
                output["ik"] = result
            print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--run-ik", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.examples.resolve(), args.run_ik))
