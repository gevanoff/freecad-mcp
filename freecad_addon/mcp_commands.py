"""Workbench controls and RPC handler registration."""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui

from rpc_server import PORT, RPCServer

_server: RPCServer | None = None


def _get_server() -> RPCServer:
    global _server
    if _server is None:
        _server = RPCServer()
        from handlers.document import (
            analyze_shape, create_document, create_primitive, get_document_graph,
            inspect_object, list_documents, tracked_recompute,
        )
        from handlers.sketcher import get_sketch_diagnostics
        from handlers.viewport import get_screenshot
        handlers = {
            "list_documents": list_documents,
            "create_document": create_document,
            "create_primitive": create_primitive,
            "get_document_graph": get_document_graph,
            "inspect_object": inspect_object,
            "analyze_shape": analyze_shape,
            "get_sketch_diagnostics": get_sketch_diagnostics,
            "tracked_recompute": tracked_recompute,
            "get_screenshot": get_screenshot,
        }
        if os.environ.get("FREECAD_MCP_ALLOW_SCRIPT") == "1":
            from handlers.execution import execute_script
            handlers["execute_script"] = execute_script
        _server.register_all(handlers)
    return _server


class StartRPCServer:
    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": f"Start authenticated loopback RPC on port {PORT}"}

    def Activated(self):
        server = _get_server()
        if not server.is_running:
            server.start()
            FreeCAD.Console.PrintMessage(f"FreeCAD MCP listening on 127.0.0.1:{PORT}\n")

    def IsActive(self):
        return True


class StopRPCServer:
    def GetResources(self):
        return {"MenuText": "Stop RPC Server", "ToolTip": "Stop the FreeCAD MCP RPC listener"}

    def Activated(self):
        if _server is not None and _server.is_running:
            _server.stop()
            FreeCAD.Console.PrintMessage("FreeCAD MCP RPC stopped\n")

    def IsActive(self):
        return True


FreeCADGui.addCommand("FreeCADMCPStart", StartRPCServer())
FreeCADGui.addCommand("FreeCADMCPStop", StopRPCServer())

