import base64
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class ViewportTests(unittest.TestCase):
    def load(self, view):
        gui = types.SimpleNamespace(activeView=lambda: view,
                                    ActiveDocument=types.SimpleNamespace(ActiveView=view))
        spec = importlib.util.spec_from_file_location(
            "viewport_under_test", Path(__file__).resolve().parents[1] / "freecad_addon/handlers/viewport.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"FreeCADGui": gui}):
            spec.loader.exec_module(module)
        return module

    def test_non_3d_view_has_actionable_error_before_allocating_file(self):
        module = self.load(object())
        with patch.object(module.tempfile, "mkstemp") as temp:
            with self.assertRaisesRegex(RuntimeError, "Activate a 3D view"):
                module.get_screenshot()
            temp.assert_not_called()

    def test_no_view_has_actionable_error(self):
        with self.assertRaisesRegex(RuntimeError, "Activate a 3D view"):
            self.load(None).get_screenshot()

    def test_valid_capture_cleans_up_file(self):
        paths = []
        def save(path, width, height, background):
            paths.append(Path(path))
            Path(path).write_bytes(b"test image")
        module = self.load(types.SimpleNamespace(saveImage=save))
        result = module.get_screenshot(640, 480)
        self.assertEqual(base64.b64decode(result["base64_png"]), b"test image")
        self.assertFalse(paths[0].exists())

    def test_failed_capture_cleans_up_file(self):
        paths = []
        def save(path, *args):
            paths.append(Path(path))
            raise RuntimeError("Render failed")
        with self.assertRaisesRegex(RuntimeError, "Render failed"):
            self.load(types.SimpleNamespace(saveImage=save)).get_screenshot()
        self.assertFalse(paths[0].exists())
