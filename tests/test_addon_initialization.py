"""FreeCAD executes InitGui.py without supplying a __file__ global."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class AddonInitializationTests(unittest.TestCase):
    def test_freecad_exec_loader_without_file_global(self):
        source = Path(__file__).resolve().parents[1] / "freecad_addon/InitGui.py"
        registered = []
        gui = types.SimpleNamespace(Workbench=type("Workbench", (), {}),
                                    addWorkbench=registered.append)
        original_path = sys.path[:]
        try:
            with patch.dict(sys.modules, {"FreeCADGui": gui}):
                exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"),
                     {"__name__": "__FreeCADInitGui__"})
            self.assertEqual(len(registered), 1)
            self.assertEqual(registered[0].MenuText, "FreeCAD MCP")
            self.assertIn(str(source.parent), sys.path)
        finally:
            sys.path[:] = original_path
