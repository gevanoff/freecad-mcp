"""Run a request list over real MCP stdio and retain concise evidence."""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    source, output = (Path(arg).resolve() for arg in sys.argv[1:3])
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    parameters = StdioServerParameters(
        command=str(Path(sys.executable).with_name("freecad-mcp.exe")),
        cwd=str(root),
        env=dict(os.environ),
    )
    records = []
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = await session.list_tools()
            (output / "tools.json").write_text(tool_list.model_dump_json(indent=2), encoding="utf-8")
            for index, call in enumerate(json.loads(source.read_text(encoding="utf-8"))):
                arguments = dict(call.get("arguments", {}))
                if "script_file" in call:
                    arguments["script"] = f"EXPERIMENT_DIR = {str(source.parent)!r}\n" + (source.parent / call["script_file"]).read_text(encoding="utf-8")
                response = await session.call_tool(call["tool"], arguments)
                data = response.structuredContent
                if data is None:
                    data = [getattr(item, "text", "") for item in response.content]
                if isinstance(data, dict) and "base64_png" in data:
                    file = f"{index:02}-screenshot.png"
                    (output / file).write_bytes(base64.b64decode(data.pop("base64_png")))
                    data["image_file"] = file
                record = {"tool": call["tool"], "arguments": arguments,
                          "isError": response.isError, "result": data}
                records.append(record)
                (output / "responses.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
                print(json.dumps(record)[:3500], flush=True)
    (output / "revision.txt").write_text(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
