"""Placement normalization contracts without a FreeCAD runtime."""

import importlib.util
import math
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "freecad_addon" / "handlers" / "modeling.py"


class Placement:
    """A minimal 2D rigid transform for exercising rotated parent placements."""
    def __init__(self, x, y, angle=0):
        self.x, self.y, self.angle = x, y, angle

    def multiply(self, other):
        c, s = math.cos(self.angle), math.sin(self.angle)
        return Placement(self.x + c * other.x - s * other.y,
                         self.y + s * other.x + c * other.y,
                         self.angle + other.angle)

    def inverse(self):
        c, s = math.cos(self.angle), math.sin(self.angle)
        return Placement(-c*self.x-s*self.y, s*self.x-c*self.y, -self.angle)


class Shape:
    def __init__(self, placement):
        self.Placement = placement

    def isNull(self):
        return False

    def isValid(self):
        return True

    def copy(self):
        p = self.Placement
        return Shape(Placement(p.x, p.y, p.angle))


def load_modeling():
    document = types.ModuleType("handlers.document")
    for name in ("_resolve_doc", "_safe_valid", "_shape_summary"):
        setattr(document, name, lambda *args: None)
    with patch.dict(sys.modules, {"FreeCAD": types.ModuleType("FreeCAD"),
                                  "Part": types.ModuleType("Part"),
                                  "handlers": types.ModuleType("handlers"),
                                  "handlers.document": document}):
        spec = importlib.util.spec_from_file_location("modeling_coordinates_test", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class ShapePlacementTests(unittest.TestCase):
    def test_ancestor_rotation_is_applied_once_to_copied_shape(self):
        module = load_modeling()
        local = Placement(2, 0)
        shape = Shape(local)
        obj = types.SimpleNamespace(Shape=shape, Placement=local,
                                    getGlobalPlacement=lambda: Placement(100, 212, math.pi/2))
        doc = types.SimpleNamespace(getObject=lambda name: obj)
        result = module._object_shape(doc, "GroupedBox")
        self.assertIsNot(result, shape)
        self.assertAlmostEqual(result.Placement.x, 100)
        self.assertAlmostEqual(result.Placement.y, 212)
        self.assertAlmostEqual(result.Placement.angle, math.pi/2)
        self.assertEqual((shape.Placement.x, shape.Placement.y), (2, 0))

    def test_root_object_placement_is_not_applied_twice(self):
        module = load_modeling()
        local = Placement(12, 4, math.pi/2)
        obj = types.SimpleNamespace(Shape=Shape(local), Placement=local,
                                    getGlobalPlacement=lambda: local)
        result = module._object_shape(types.SimpleNamespace(getObject=lambda name: obj), "RootBox")
        self.assertAlmostEqual(result.Placement.x, 12)
        self.assertAlmostEqual(result.Placement.y, 4)
        self.assertAlmostEqual(result.Placement.angle, math.pi/2)

    def test_missing_placement_information_is_rejected(self):
        module = load_modeling()
        obj = types.SimpleNamespace(Shape=Shape(Placement(0, 0)))
        with self.assertRaisesRegex(ValueError, "Cannot determine document placement"):
            module._object_shape(types.SimpleNamespace(getObject=lambda name: obj), "Box")
