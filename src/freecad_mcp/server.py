"""Client-neutral stdio MCP server for FreeCAD."""

from __future__ import annotations

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from freecad_mcp.bridge import FreeCADBridge
from freecad_mcp.config import read_token

mcp = FastMCP("freecad")
_bridge: FreeCADBridge | None = None


def _call(method: str, params: dict | None = None):
    global _bridge
    if _bridge is None:
        _bridge = FreeCADBridge()
    return _bridge.call(method, params)


@mcp.tool()
def list_documents() -> list[dict]:
    """List open FreeCAD documents and basic status."""
    return _call("list_documents")


@mcp.tool()
def get_document_graph(doc_name: str = "") -> dict:
    """Inspect a document's feature tree, dependencies, and object validity."""
    return _call("get_document_graph", {"doc_name": doc_name})


@mcp.tool()
def inspect_object(name: str, doc_name: str = "") -> dict:
    """Inspect a FreeCAD object's properties and basic geometric state."""
    return _call("inspect_object", {"name": name, "doc_name": doc_name})


@mcp.tool()
def analyze_shape(name: str, doc_name: str = "") -> dict:
    """Inspect a shape's topology, validity, bounds, area, and volume."""
    return _call("analyze_shape", {"name": name, "doc_name": doc_name})


@mcp.tool()
def get_sketch_diagnostics(name: str, doc_name: str = "") -> dict:
    """Report sketch constraints, conflicts, redundancies, and degrees of freedom."""
    return _call("get_sketch_diagnostics", {"name": name, "doc_name": doc_name})


@mcp.tool()
def create_sketch(elements: list[dict], label: str = "", doc_name: str = "") -> dict:
    """Create an XY sketch containing up to 64 lines/circles with optional dimensional constraints.

    The target document must be active in FreeCAD.
    Circle: {type:"circle",x:0,y:0,radius:5,constrain_radius:true}
    Line: {type:"line",x1:0,y1:0,x2:10,y2:0,orientation:"horizontal"}
    """
    return _call("create_sketch", {"elements": elements, "label": label, "doc_name": doc_name})


@mcp.tool()
def tracked_recompute(doc_name: str = "") -> dict:
    """Recompute a document and report object validity changes."""
    return _call("tracked_recompute", {"doc_name": doc_name})


@mcp.tool()
def create_primitive(
    kind: Literal["box", "cylinder", "sphere"],
    label: str = "",
    length: float = 10,
    width: float = 10,
    height: float = 10,
    radius: float = 5,
    doc_name: str = "",
) -> dict:
    """Create a box, cylinder, or sphere in the active FreeCAD document using bounded dimensions."""
    if len(label) > 128:
        raise ValueError("Label must be 128 characters or shorter")
    for value in (length, width, height, radius):
        if not (0.001 <= value <= 10000):
            raise ValueError("Dimensions must be between 0.001 and 10000 mm")
    return _call("create_primitive", {
        "kind": kind, "label": label, "length": length, "width": width,
        "height": height, "radius": radius, "doc_name": doc_name,
    })


@mcp.tool()
def create_document(name: str) -> dict:
    """Create and activate a new document with a restricted identifier."""
    if not name or len(name) > 64 or not name.isascii() or not name[0].isalpha() or not name.replace("_", "").isalnum():
        raise ValueError("Document name must be 1–64 letters, digits, or underscores and start with a letter")
    return _call("create_document", {"name": name})


@mcp.tool()
def get_screenshot(width: int = 1024, height: int = 768) -> dict:
    """Capture the active FreeCAD viewport as a PNG data URL payload."""
    if not (64 <= width <= 2048 and 64 <= height <= 2048):
        raise ValueError("Screenshot dimensions must be between 64 and 2048 pixels")
    return _call("get_screenshot", {"width": width, "height": height})


if os.environ.get("FREECAD_MCP_ALLOW_SCRIPT") == "1":
    @mcp.tool()
    def execute_script(script: str) -> dict:
        """Run arbitrary Python in FreeCAD. This grants full code execution as your user."""
        if len(script.encode("utf-8")) > 128 * 1024:
            raise ValueError("Script exceeds the 128 KiB limit")
        return _call("execute_script", {"script": script})


def main() -> None:
    # Fail before starting the protocol if the local credential is unavailable.
    read_token()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

