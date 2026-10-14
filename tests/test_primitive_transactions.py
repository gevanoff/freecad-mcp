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
        self.HasPendingTransaction = False
        self.UndoMode = 1
        self.UndoNames = []

    def openTransaction(self, label):
        self.events.append("open")

    def addObject(self, type_id, name):
        self.events.append("add")
        self.HasPendingTransaction = True
        obj = types.SimpleNamespace(Name=name, Label=name, TypeId=type_id, Shape=self.shape,
                                    State=getattr(self, "object_state", []),
                                    isValid=lambda: not getattr(self, "object_invalid", False))
        self.objects.append(obj)
        return obj

    def getObject(self, name):
        return next((obj for obj in self.objects if obj.Name == name), None)

    def recompute(self, objects=None):
        self.events.append("recompute")
        assert objects == self.objects, "Recompute must be scoped to new primitive"
        if self.recompute_error:
            raise self.recompute_error

    def commitTransaction(self):
        self.events.append("commit")
        if getattr(self, "commit_error", None):
            raise self.commit_error
        self.HasPendingTransaction = False
        self.UndoNames.insert(0, "MCP: create primitive")
        if getattr(self, "post_commit_error", None):
            raise self.post_commit_error

    def abortTransaction(self):
        self.events.append("abort")
        if self.HasPendingTransaction:
            self.objects.clear()
            self.HasPendingTransaction = False


def load_handler(document, active_transaction=None, transaction_api_available=True):
    fake_freecad = types.SimpleNamespace(ActiveDocument=document, getDocument=lambda name: document,
                                         listDocuments=lambda: {"Test": document, **getattr(document, "other_documents", {})})
    if transaction_api_available:
        fake_freecad.getActiveTransaction = lambda: active_transaction
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

    def test_disabled_undo_refuses_mutation(self):
        doc = FakeDocument()
        doc.UndoMode = 0
        with self.assertRaisesRegex(RuntimeError, "undo transactions are disabled"):
            load_handler(doc).create_primitive("box")
        self.assertEqual(doc.events, [])
        self.assertEqual(doc.objects, [])

    def test_postcommit_observer_error_returns_committed_result(self):
        doc = FakeDocument()
        doc.post_commit_error = RuntimeError("observer raised after commit")
        result = load_handler(doc).create_primitive("sphere")
        self.assertEqual(len(doc.objects), 1)
        self.assertIn("commit_observer_warning", result)
        self.assertEqual(doc.events, ["open", "add", "recompute", "commit"])
        self.assertEqual(doc.UndoNames, ["MCP: create primitive"])

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

    def test_transaction_on_other_document_blocks_mutation(self):
        doc = FakeDocument()
        other = FakeDocument()
        other.HasPendingTransaction = True
        doc.other_documents = {"Other": other}
        with self.assertRaisesRegex(RuntimeError, "pending GUI transaction"):
            load_handler(doc).create_primitive("box")
        self.assertEqual(doc.events, [])
        self.assertEqual(other.events, [])

    def test_booked_gui_transaction_before_first_edit_is_preserved(self):
        doc = FakeDocument()
        other = FakeDocument()
        doc.other_documents = {"Other": other}
        # No document has pending edits yet, but FreeCAD has booked a GUI command.
        self.assertFalse(doc.HasPendingTransaction)
        self.assertFalse(other.HasPendingTransaction)
        booked = ("GUI: edit sketch", 128)
        with self.assertRaisesRegex(RuntimeError, "already booked"):
            load_handler(doc, active_transaction=booked).create_primitive("box")
        self.assertEqual(doc.events, [])
        self.assertEqual(other.events, [])
        self.assertEqual(doc.objects, [])

    def test_unavailable_transaction_api_fails_closed(self):
        doc = FakeDocument()
        with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
            load_handler(doc, transaction_api_available=False).create_primitive("box")
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
