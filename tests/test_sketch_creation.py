"""Regression coverage for bounded sketch creation without a FreeCAD GUI."""

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "freecad_addon" / "handlers" / "sketcher.py"


class FakeSketch:
    Name = "MCPSketch"
    Label = "MCPSketch"
    State = ()

    def __init__(self):
        self.geometry = []
        self.constraints = []

    @property
    def GeometryCount(self):
        return len(self.geometry)

    @property
    def ConstraintCount(self):
        return len(self.constraints)

    def addGeometry(self, geom, construction):
        assert construction is False
        self.geometry.append(geom)
        return len(self.geometry) - 1

    def addConstraint(self, constraint):
        self.constraints.append(constraint)

    def isValid(self):
        return True


class FakeDoc:
    Name = "Doc"
    UndoMode = 1
    HasPendingTransaction = False

    def __init__(self):
        self.booking = None
        self.events = []
        self.sketch = None

    def openTransaction(self, title):
        self.booking = ("MCP", 1)
        self.events.append("open")

    def addObject(self, type_id, name):
        assert type_id == "Sketcher::SketchObject"
        self.events.append("add")
        self.sketch = FakeSketch()
        return self.sketch

    def recompute(self, objects):
        self.events.append("recompute")
        if getattr(self, "recompute_failure", False):
            raise RuntimeError("recompute failed")

    def commitTransaction(self):
        self.events.append("commit")
        self.booking = None

    def abortTransaction(self):
        self.events.append("abort")
        self.booking = None
        self.sketch = None

    def getObject(self, name):
        return self.sketch


def load(doc, other=None):
    freecad = types.SimpleNamespace(
        ActiveDocument=doc,
        getActiveTransaction=lambda: doc.booking,
        listDocuments=lambda: {"Doc": doc, **({"Other": other} if other else {})},
        Vector=lambda x, y, z: (x, y, z),
    )
    part = types.SimpleNamespace(
        Circle=lambda *a: ("circle", a),
        LineSegment=lambda *a: ("line", a),
    )
    sketcher = types.SimpleNamespace(Constraint=lambda *a: a)
    document = types.ModuleType("handlers.document")
    document._resolve_doc = lambda name="": doc
    with patch.dict(sys.modules, {
        "FreeCAD": freecad, "Part": part, "Sketcher": sketcher,
        "handlers": types.ModuleType("handlers"), "handlers.document": document,
    }):
        spec = importlib.util.spec_from_file_location("sketcher_under_test", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    original = mod.create_sketch
    def invoke(*args, **kwargs):
        with patch.dict(sys.modules, {"FreeCAD": freecad, "Part": part, "Sketcher": sketcher}):
            return original(*args, **kwargs)
    mod.create_sketch = invoke
    return mod


class SketchCreationTests(unittest.TestCase):
    def test_success_with_two_constraint_types(self):
        doc = FakeDoc()
        result = load(doc).create_sketch([
            {"type": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0, "orientation": "horizontal"},
            {"type": "circle", "x": 1, "y": 2, "radius": 5, "constrain_radius": True},
        ], label="Profile")
        self.assertEqual((result["geometry_count"], result["constraint_count"]), (2, 2))
        self.assertEqual(doc.sketch.constraints, [("Horizontal", 0), ("Radius", 1, 5.0)])
        self.assertEqual(doc.events, ["open", "add", "recompute", "commit"])

    def test_prevalidate_before_mutation(self):
        samples = [
            [],
            [{"type": "circle", "x": 0, "y": 0, "radius": -1}],
            [{"type": "circle", "x": 0, "y": 0, "radius": float("nan")}],
            [{"type": "line", "x1": 0, "y1": 0, "x2": 0, "y2": 0}],
            [{"type": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 1, "orientation": "horizontal"}],
            [{"type": "circle", "x": 0, "y": 0, "radius": 5, "surprise": True}],
        ]
        for elements in samples:
            with self.subTest(elements=elements):
                doc = FakeDoc()
                with self.assertRaises(ValueError):
                    load(doc).create_sketch(elements)
                self.assertEqual(doc.events, [])

    def test_recompute_failure_aborts(self):
        doc = FakeDoc()
        doc.recompute_failure = True
        with self.assertRaisesRegex(RuntimeError, "recompute failed"):
            load(doc).create_sketch([{"type": "circle", "x": 0, "y": 0, "radius": 2}])
        self.assertEqual(doc.events[-1], "abort")
        self.assertIsNone(doc.sketch)

    def test_busy_other_document_blocks_mutation(self):
        doc = FakeDoc()
        other = FakeDoc()
        other.HasPendingTransaction = True
        with self.assertRaisesRegex(RuntimeError, "active GUI transaction"):
            load(doc, other).create_sketch([{"type": "circle", "x": 0, "y": 0, "radius": 2}])
        self.assertEqual(doc.events, [])

    def test_booked_application_transaction_blocks_mutation(self):
        doc = FakeDoc()
        doc.booking = ("GUI", 10)
        with self.assertRaisesRegex(RuntimeError, "active GUI transaction"):
            load(doc).create_sketch([{"type": "circle", "x": 0, "y": 0, "radius": 2}])
        self.assertEqual(doc.events, [])


if __name__ == "__main__":
    unittest.main()
