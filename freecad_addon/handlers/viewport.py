"""Viewport screenshot handler."""

from __future__ import annotations

import base64
import os
import tempfile

import FreeCADGui


def get_screenshot(width: int = 1024, height: int = 768) -> dict:
    if not (64 <= width <= 2048 and 64 <= height <= 2048):
        raise ValueError("Screenshot dimensions must be between 64 and 2048 pixels")
    doc = FreeCADGui.ActiveDocument
    if doc is None or doc.ActiveView is None:
        raise RuntimeError("No active FreeCAD viewport")
    handle, path = tempfile.mkstemp(prefix="freecad-mcp-", suffix=".png")
    os.close(handle)
    try:
        doc.ActiveView.saveImage(path, width, height, "Current")
        with open(path, "rb") as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Screenshot exceeds the 2 MiB image limit")
        return {"format": "png", "width": width, "height": height,
                "base64_png": base64.b64encode(data).decode("ascii")}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

