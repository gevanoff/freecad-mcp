"""Assertions over real MCP stdio -> RPC -> FreeCAD, in the isolated test session."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent

async def main():
    output = HERE / "fixed"
    output.mkdir(exist_ok=True)
    records = []
    params = StdioServerParameters(command=str(Path(sys.executable).with_name("freecad-mcp.exe")),
                                  env={**os.environ, "FREECAD_MCP_PORT": "9877", "FREECAD_MCP_ALLOW_SCRIPT": "1"})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        async def call(tool, arguments, expected_error=None):
            response = await session.call_tool(tool, arguments)
            data = response.structuredContent
            if data is None:
                texts = [getattr(item, "text", "") for item in response.content]
                try:
                    data = json.loads(texts[0]) if len(texts) == 1 else texts
                except ValueError:
                    data = texts
            if isinstance(data, dict) and "base64_png" in data:
                png = base64.b64decode(data.pop("base64_png"))
                assert png.startswith(b"\x89PNG\r\n\x1a\n")
                (output / "3d-view.png").write_bytes(png)
                data["image_sha256"] = hashlib.sha256(png).hexdigest()
            records.append({"tool": tool, "arguments": arguments, "isError": response.isError, "result": data})
            (output / "responses.json").write_text(json.dumps(records, indent=2))
            if expected_error:
                assert response.isError and expected_error in str(data), data
            else:
                assert not response.isError, data
                if tool == "execute_script":
                    assert data["success"], data
            return data
        async def script(code, expected_error=None):
            return await call("execute_script", {"script": code}, expected_error)
        await script((HERE / "setup.py").read_text())
        await call("get_screenshot", {}, "Activate a 3D view")
        await script('doc = App.newDocument("Screenshot3D")\ndoc.UndoMode = 1')
        await call("create_primitive", {"kind": "box", "doc_name": "Screenshot3D"})
        await script('Gui.activeDocument().activeView().viewAxonometric()\nGui.activeDocument().activeView().fitAll()\nGui.updateGui()')
        await call("get_screenshot", {"width": 640, "height": 480})
        await script('''import time
from freecad_addon import rpc_server
from freecad_addon.handlers import document
rpc_server.MAIN_THREAD_TIMEOUT = 0.2
document._original_summary = document._shape_summary
def slow_summary(shape):
    time.sleep(0.8)
    return document._original_summary(shape)
document._shape_summary = slow_summary
''')
        await call("create_primitive", {"kind": "sphere", "doc_name": "Screenshot3D"}, "-32005")
        await asyncio.sleep(1)
        await script('''from freecad_addon.handlers import document
document._shape_summary = document._original_summary
del document._original_summary
doc = App.getDocument("Screenshot3D")
assert len(doc.Objects) == 2
assert all(obj.Shape.isValid() for obj in doc.Objects)
assert not doc.HasPendingTransaction
print("Running timeout: exactly one primitive eventually committed")
''')
        await script("import time\ntime.sleep(1.2)", "-32005")
        await call("create_primitive", {"kind": "cylinder", "doc_name": "Screenshot3D"}, "-32003")
        await asyncio.sleep(1.3)
        await script('''from freecad_addon import rpc_server
rpc_server.MAIN_THREAD_TIMEOUT = 35.0
doc = App.getDocument("Screenshot3D")
assert len(doc.Objects) == 2
assert doc.UndoCount == 2
assert not doc.HasPendingTransaction
print("Queued timeout: no late mutation after GUI resumed")
''')
    (output / "summary.json").write_text(json.dumps({"checks": ["real geometry exception rollback", "spreadsheet rejection", "3D PNG capture", "in-flight timeout truthfulness", "queued timeout cancellation"], "status": "passed"}, indent=2))
    print("All five live MCP/FreeCAD checks passed")

if __name__ == "__main__":
    asyncio.run(main())
