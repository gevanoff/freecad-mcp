"""Register the FreeCAD MCP workbench; the listener never auto-starts."""

from __future__ import annotations

import os
import sys

try:
    _source_file = __file__
except NameError:
    # FreeCAD's InitGui loader executes compiled source without __file__.
    # The code object's filename still identifies this addon, independently
    # of the user's current directory and installation location.
    import inspect
    _source_file = inspect.getfile(inspect.currentframe())
_addon_dir = os.path.dirname(os.path.realpath(_source_file))
if _addon_dir not in sys.path:
    sys.path.insert(0, _addon_dir)

import FreeCADGui as Gui


class FreeCADMCPWorkbench(Gui.Workbench):
    MenuText = "FreeCAD MCP"
    ToolTip = "Connect an MCP client to this FreeCAD session"

    def Initialize(self):
        import mcp_commands  # noqa: F401
        self.appendToolbar("FreeCAD MCP", ["FreeCADMCPStart", "FreeCADMCPStop"])
        self.appendMenu("FreeCAD MCP", ["FreeCADMCPStart", "FreeCADMCPStop"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(FreeCADMCPWorkbench())

