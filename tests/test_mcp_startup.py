"""Exercise the installed server entry point, without a running FreeCAD GUI."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def check_startup(tmp_path, allow_script):
    token = tmp_path / "token"
    token.write_text("startup-test-credential-" * 3, encoding="utf-8")
    token.chmod(0o600)
    environment = dict(os.environ)
    environment["FREECAD_MCP_TOKEN_FILE"] = str(token)
    environment.pop("FREECAD_MCP_ALLOW_SCRIPT", None)
    if allow_script:
        environment["FREECAD_MCP_ALLOW_SCRIPT"] = "1"

    async def handshake():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "freecad_mcp.server"],
            env=environment,
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()
                names = {tool.name for tool in response.tools}
                assert {"create_document", "create_primitive", "analyze_shape", "get_screenshot"} <= names
                assert ("execute_script" in names) == allow_script

    asyncio.run(asyncio.wait_for(handshake(), timeout=15))


class MCPStartupTests(unittest.TestCase):
    def test_default_tools_over_stdio(self):
        with tempfile.TemporaryDirectory() as folder:
            check_startup(Path(folder), False)

    def test_script_opt_in_over_stdio(self):
        with tempfile.TemporaryDirectory() as folder:
            check_startup(Path(folder), True)
