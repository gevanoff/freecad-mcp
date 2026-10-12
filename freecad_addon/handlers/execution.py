"""Explicit opt-in arbitrary script execution. Not a sandbox."""

from __future__ import annotations

import contextlib
import io
import traceback

import FreeCAD
import FreeCADGui


def execute_script(script: str) -> dict:
    if len(script.encode("utf-8")) > 128 * 1024:
        raise ValueError("Script exceeds the 128 KiB limit")
    stdout, stderr = io.StringIO(), io.StringIO()
    namespace = {
        "FreeCAD": FreeCAD, "App": FreeCAD,
        "FreeCADGui": FreeCADGui, "Gui": FreeCADGui,
        "doc": FreeCAD.ActiveDocument,
    }
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(script, namespace)
        return {"success": True, "stdout": stdout.getvalue()[:32768],
                "stderr": stderr.getvalue()[:32768], "error": None}
    except Exception as exc:
        return {"success": False, "stdout": stdout.getvalue()[:32768],
                "stderr": stderr.getvalue()[:32768],
                "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=8)}"[:8192]}

