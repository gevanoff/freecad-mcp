"""Safety checks for explicit output publication, without a FreeCAD dependency."""
import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "freecad_addon" / "handlers" / "files.py"


def load_files():
    freecad = types.SimpleNamespace(getActiveTransaction=lambda: None, listDocuments=lambda: {})
    document = types.ModuleType("handlers.document")
    document._resolve_doc = lambda name: None
    with patch.dict(sys.modules, {"FreeCAD": freecad, "handlers": types.ModuleType("handlers"),
                                  "handlers.document": document}):
        spec = importlib.util.spec_from_file_location("modeling_files_test", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class PublicationTests(unittest.TestCase):
    def test_existing_output_is_untouched_and_writer_not_called(self):
        module = load_files()
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "object.stl"
            target.write_bytes(b"original")
            def writer(_):
                self.fail("writer ran despite existing output")
            with self.assertRaises(FileExistsError):
                module._publish_new(str(target), writer)
            self.assertEqual(target.read_bytes(), b"original")

    def test_competing_creator_is_never_overwritten(self):
        module = load_files()
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "object.stl"
            def writer(path):
                pathlib.Path(path).write_bytes(b"our output")
                target.write_bytes(b"other output")
            with self.assertRaises(FileExistsError):
                module._publish_new(str(target), writer)
            self.assertEqual(target.read_bytes(), b"other output")

    def test_failed_writer_leaves_no_destination(self):
        module = load_files()
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "object.stl"
            with self.assertRaisesRegex(RuntimeError, "did not produce"):
                module._publish_new(str(target), lambda path: None)
            self.assertFalse(target.exists())

    def test_bad_names_are_rejected_before_accessing_document(self):
        module = load_files()
        with self.assertRaisesRegex(ValueError, "distinct object names"):
            module.export_objects(str(pathlib.Path.cwd() / "out.stl"), [["unhashable"]])
