"""Bounded solid modeling operations for the active FreeCAD document."""

from __future__ import annotations

import math

import FreeCAD
import Part

from handlers.document import _resolve_doc, _safe_valid, _shape_summary


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be a finite number between {low} and {high}")
    return float(value)


def _vector(values, name, limit):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"{name} must contain three numbers")
    return [_number(v, name, -limit, limit) for v in values]


def _active_document(doc_name):
    doc = _resolve_doc(doc_name)
    if doc is not FreeCAD.ActiveDocument:
        raise RuntimeError("Modeling requires the target document to be active")
    return doc


def _object_shape(doc, name):
    if not isinstance(name, str) or not name or len(name) > 128:
        raise ValueError("Object name must contain 1–128 characters")
    obj = doc.getObject(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or not shape.isValid():
        raise ValueError(f"Object '{name}' must have a valid, non-null shape")
    return shape


def _store_shape(doc, shape, label, action):
    """Create one undoable feature without taking ownership of a GUI transaction."""
    if not isinstance(label, str) or len(label) > 128:
        raise ValueError("Label must be at most 128 characters")
    if shape.isNull() or not shape.isValid() or not shape.Solids:
        raise ValueError("Modeling result must contain at least one valid solid")
    try:
        booked = FreeCAD.getActiveTransaction()
    except (AttributeError, TypeError) as exc:
        raise RuntimeError("Cannot verify FreeCAD application transaction ownership") from exc
    if booked is not None or any(bool(d.HasPendingTransaction) for d in FreeCAD.listDocuments().values()):
        raise RuntimeError("FreeCAD has an active GUI transaction; finish or cancel it first")
    if getattr(doc, "UndoMode", None) != 1:
        raise RuntimeError("FreeCAD document undo transactions are disabled")
    doc.openTransaction("MCP: " + action)
    owned = FreeCAD.getActiveTransaction()
    if owned is None:
        raise RuntimeError("FreeCAD did not book the modeling transaction")
    try:
        obj = doc.addObject("Part::Feature", "MCPModel")
        obj.Shape = shape
        if label:
            obj.Label = label
        doc.recompute([obj])
        states = [str(state) for state in getattr(obj, "State", [])]
        if "Error" in states or "Invalid" in states or not _safe_valid(obj) or not obj.Shape.isValid() or obj.Shape.isNull():
            raise ValueError("Modeling result failed recomputation")
        result = {"document": doc.Name, "name": obj.Name, "label": obj.Label,
                  "type_id": obj.TypeId, "shape": _shape_summary(obj.Shape)}
        try:
            doc.commitTransaction()
        except BaseException as exc:
            if owned is not None and FreeCAD.getActiveTransaction() == owned:
                raise
            if doc.getObject(obj.Name) is not obj:
                raise RuntimeError("Modeling commit outcome cannot be verified") from exc
            result["commit_observer_warning"] = "Model committed but a post-commit observer raised"
        return result
    except BaseException:
        if owned is not None and FreeCAD.getActiveTransaction() == owned:
            doc.abortTransaction()
        raise


def transformed_copy(name: str, translation: list, axis: list, angle_degrees: float = 0,
                     label: str = "", doc_name: str = "") -> dict:
    """Copy a solid, rotate it about the origin, and then translate it in millimetres."""
    t = _vector(translation, "translation", 10000)
    a = _vector(axis, "axis", 10000)
    angle = _number(angle_degrees, "angle_degrees", -3600, 3600)
    if math.hypot(*a) < 1e-9:
        raise ValueError("Rotation axis must be non-zero")
    doc = _active_document(doc_name)
    shape = _object_shape(doc, name).copy()
    shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(*a), angle)
    shape.translate(FreeCAD.Vector(*t))
    return _store_shape(doc, shape, label, "transformed copy")


def boolean_solids(operation: str, first: str, second: str, label: str = "", doc_name: str = "") -> dict:
    """Create a static cut, union, or intersection; preserve the inputs."""
    if operation not in ("cut", "fuse", "common"):
        raise ValueError("operation must be cut, fuse, or common")
    if first == second:
        raise ValueError("Boolean inputs must be different objects")
    doc = _active_document(doc_name)
    a, b = _object_shape(doc, first), _object_shape(doc, second)
    if not a.Solids or not b.Solids:
        raise ValueError("Boolean inputs must contain solids")
    shape = getattr(a, operation)(b).removeSplitter()
    return _store_shape(doc, shape, label, "boolean " + operation)


def create_helical_ridge(root_radius: float, outer_radius: float, pitch: float, height: float,
                         root_width: float, crest_width: float, label: str = "", doc_name: str = "") -> dict:
    """Sweep a trapezoid along a right-handed +Z helix; dimensions are mm."""
    root = _number(root_radius, "root_radius", 0.1, 1000)
    outer = _number(outer_radius, "outer_radius", 0.1, 1000)
    p = _number(pitch, "pitch", 0.1, 1000)
    h = _number(height, "height", 0.1, 1000)
    rw = _number(root_width, "root_width", 0.01, 1000)
    cw = _number(crest_width, "crest_width", 0.01, 1000)
    if outer <= root or cw > rw or rw >= p or h / p > 30:
        raise ValueError("Require outer_radius > root_radius, crest_width <= root_width < pitch, and at most 30 turns")
    doc = _active_document(doc_name)
    z = rw / 2
    path = Part.makeHelix(p, h, root)
    path.translate(FreeCAD.Vector(0, 0, z))
    pts = [FreeCAD.Vector(root, 0, z-rw/2), FreeCAD.Vector(outer, 0, z-cw/2),
           FreeCAD.Vector(outer, 0, z+cw/2), FreeCAD.Vector(root, 0, z+rw/2)]
    profile = Part.makePolygon(pts + [pts[0]])
    shape = Part.Wire(path.Edges).makePipeShell([Part.Wire(profile.Edges)], True, True)
    return _store_shape(doc, shape, label, "helical ridge")
