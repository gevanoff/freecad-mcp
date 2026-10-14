"""Unit tests for atomic FreeCAD primitive mutations, without a GUI dependency."""

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


HANDLER_PATH = pathlib.Path(__file__).resolve().parents[1] / "freecad_addon" / "handlers" / "document.py"


class FakeShape:
    ShapeType = "Solid"
    Vertexes = ()
    Edges = ()
    Wires = ()
    Faces = ()
    Solids = (object(),)
    Area = 1
    Volume = 1
    BoundBox = types.SimpleNamespace(XMin=0, YMin=0, ZMin=0, XMax=1, YMax=1, ZMax=1)

    def __init__(self, valid=True, null=False):
        self.valid, self.null = valid, null

    def isValid(self):
        return self.valid

    def isNull(self):
        return self.null


class FakeDocument:
    Name = "Test"

    HasPendingTransaction = False

    def __init__(self, shape=None, recompute_error=None):
        self.shape = shape if shape is not None else FakeShape()
        self.recompute_error = recompute_error
        self.objects = []
        self.events = []

    def openTransaction(self, label):
        self.events.append("open")

    def addObject(self, type_id, name):
        self.events.append("add")
        obj = types.SimpleNamespace(Name=name, Label=name, TypeId=type_id, Shape=self.shape,
                                    State=getattr(self, "object_state", []),
                                    isValid=lambda: not getattr(self, "object_invalid", False))
        self.objects.append(obj)
        return obj

    def recompute(self, objects=None):
        self.events.append("recompute")
        assert objects == self.objects, "Recompute must be scoped to new primitive"
        if self.recompute_error:
            raise self.recompute_error

    def commitTransaction(self):
        self.events.append("commit")
        if getattr(self, "commit_error", None):
            raise self.commit_error

    def abortTransaction(self):
        self.events.append("abort")
        self.objects.clear()


def load_handler(document):
    fake_freecad = types.SimpleNamespace(ActiveDocument=document, getDocument=lambda name: document)
    with patch.dict(sys.modules, {"FreeCAD": fake_freecad}):
        spec = importlib.util.spec_from_file_location("freecad_document_under_test", HANDLER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class PrimitiveTransactionTests(unittest.TestCase):
    def test_success_commits_once(self):
        doc = FakeDocument()
        result = load_handler(doc).create_primitive("box")
        self.assertEqual(result["type_id"], "Part::Box")
        self.assertEqual(len(doc.objects), 1)
        self.assertEqual(doc.events, ["open", "add", "recompute", "commit"])

    def test_recompute_failure_rolls_back(self):
        doc = FakeDocument(recompute_error=RuntimeError("solver failed"))
        with self.assertRaisesRegex(RuntimeError, "solver failed"):
            load_handler(doc).create_primitive("cylinder")
        self.assertEqual(doc.objects, [])
        self.assertEqual(doc.events, ["open", "add", "recompute", "abort"])

    def test_invalid_shape_rolls_back(self):
        for shape in (FakeShape(valid=False), FakeShape(null=True)):
            with self.subTest(null=shape.null, valid=shape.valid):
                doc = FakeDocument(shape=shape)
                with self.assertRaisesRegex(ValueError, "invalid or null"):
                    load_handler(doc).create_primitive("sphere")
                self.assertEqual(doc.objects, [])
                self.assertEqual(doc.events[-1], "abort")

    def test_commit_failure_attempts_rollback(self):
        doc = FakeDocument()
        doc.commit_error = RuntimeError("commit failed")
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            load_handler(doc).create_primitive("box")
        self.assertEqual(doc.objects, [])
        self.assertEqual(doc.events[-2:], ["commit", "abort"])

    def test_pending_gui_transaction_is_not_touched(self):
        doc = FakeDocument()
        doc.HasPendingTransaction = True
        with self.assertRaisesRegex(RuntimeError, "pending GUI transaction"):
            load_handler(doc).create_primitive("box")
        self.assertEqual(doc.events, [])

    def test_nonthrowing_recompute_error_rolls_back(self):
        doc = FakeDocument()
        doc.object_state = ["Error"]
        with self.assertRaisesRegex(ValueError, "failed recomputation"):
            load_handler(doc).create_primitive("box")
        self.assertEqual(doc.objects, [])
        self.assertEqual(doc.events[-1], "abort")

    def test_invalid_object_with_valid_brep_rolls_back(self):
        doc = FakeDocument()
        doc.object_invalid = True
        with self.assertRaisesRegex(ValueError, "failed recomputation"):
            load_handler(doc).create_primitive("box")
        self.assertEqual(doc.objects, [])

    def test_input_validation_never_opens_transaction(self):
        doc = FakeDocument()
        with self.assertRaises(ValueError):
            load_handler(doc).create_primitive("box", radius=float("nan"))
        self.assertEqual(doc.events, [])


if __name__ == "__main__":
    unittest.main()
