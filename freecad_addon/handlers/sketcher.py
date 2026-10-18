"""Read-only sketch constraint diagnostics."""

from __future__ import annotations

from handlers.document import _resolve_doc


def get_sketch_diagnostics(name: str, doc_name: str = "") -> dict:
    doc = _resolve_doc(doc_name)
    sketch = doc.getObject(name)
    if sketch is None:
        raise ValueError(f"Object not found: {name}")
    if not hasattr(sketch, "ConstraintCount"):
        raise ValueError(f"Object '{name}' is not a sketch")
    try:
        dof = sketch.solve()
    except Exception:
        dof = None
    try:
        redundant = list(sketch.getRedundantConstraints())
    except Exception:
        redundant = []
    try:
        conflicting = list(sketch.getConflictingConstraints())
    except Exception:
        conflicting = []
    constraints = []
    for i, c in enumerate(sketch.Constraints):
        item = {
            "index": i, "type": c.Type, "name": getattr(c, "Name", "") or None,
            "first": c.First, "first_pos": c.FirstPos,
            "second": c.Second, "second_pos": c.SecondPos,
            "is_driving": getattr(c, "Driving", None),
            "is_redundant": i in redundant, "is_conflicting": i in conflicting,
        }
        if hasattr(c, "Value"):
            item["value"] = float(c.Value)
        constraints.append(item)
    return {
        "name": sketch.Name, "label": sketch.Label,
        "constraint_count": sketch.ConstraintCount,
        "geometry_count": sketch.GeometryCount,
        "degrees_of_freedom": dof,
        "fully_constrained": getattr(sketch, "FullyConstrained", None),
        "redundant_indices": redundant, "conflicting_indices": conflicting,
        "constraints": constraints,
    }


def create_sketch(elements: list[dict], label: str = "", doc_name: str = "") -> dict:
    """Create a planar XY sketch atomically using a bounded geometry vocabulary.

    Each element is either a line (x1,y1,x2,y2, orientation=none/horizontal/
    vertical) or a circle (x,y,radius, constrain_radius=true/false).
    """
    import math
    import FreeCAD
    import Part
    import Sketcher

    if not isinstance(label, str) or len(label) > 128:
        raise ValueError("Sketch label must be at most 128 characters")
    if not isinstance(elements, list) or not 1 <= len(elements) <= 64:
        raise ValueError("elements must contain between 1 and 64 geometries")

    def number(item, key):
        value = item.get(key)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or abs(value) > 10000):
            raise ValueError(f"{key} must be a finite number within +/-10000 mm")
        return float(value)

    # Entire payload is validated before opening a FreeCAD transaction.
    prepared = []
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError("Each geometry must be an object")
        kind = element.get("type")
        if kind == "circle":
            if set(element) - {"type", "x", "y", "radius", "constrain_radius"}:
                raise ValueError("Unexpected circle field")
            x, y, radius = (number(element, k) for k in ("x", "y", "radius"))
            if not 0.001 <= radius <= 10000:
                raise ValueError("Circle radius must be 0.001-10000 mm")
            constrained = element.get("constrain_radius", False)
            if not isinstance(constrained, bool):
                raise ValueError("constrain_radius must be boolean")
            prepared.append(("circle", (x, y, radius), "radius" if constrained else None))
        elif kind == "line":
            if set(element) - {"type", "x1", "y1", "x2", "y2", "orientation"}:
                raise ValueError("Unexpected line field")
            x1, y1, x2, y2 = (number(element, k) for k in ("x1", "y1", "x2", "y2"))
            if math.hypot(x2 - x1, y2 - y1) < 0.001:
                raise ValueError("Line is too short")
            orientation = element.get("orientation", "none")
            if orientation not in ("none", "horizontal", "vertical"):
                raise ValueError("Unsupported line orientation")
            if orientation == "horizontal" and abs(y2 - y1) > 1e-8:
                raise ValueError("Horizontal line endpoints must share y")
            if orientation == "vertical" and abs(x2 - x1) > 1e-8:
                raise ValueError("Vertical line endpoints must share x")
            prepared.append(("line", (x1, y1, x2, y2), orientation))
        else:
            raise ValueError("Geometry type must be circle or line")

    doc = _resolve_doc(doc_name)
    try:
        booked = FreeCAD.getActiveTransaction()
    except (AttributeError, TypeError) as exc:
        raise RuntimeError("Cannot verify FreeCAD application transaction ownership") from exc
    if booked is not None or any(bool(d.HasPendingTransaction) for d in FreeCAD.listDocuments().values()):
        raise RuntimeError("FreeCAD has an active GUI transaction; finish or cancel it first")
    if getattr(doc, "UndoMode", None) != 1:
        raise RuntimeError("FreeCAD document undo transactions are disabled")

    doc.openTransaction("MCP: create sketch")
    owned = FreeCAD.getActiveTransaction()
    try:
        sketch = doc.addObject("Sketcher::SketchObject", "MCPSketch")
        if label:
            sketch.Label = label
        for kind, values, constraint in prepared:
            if kind == "circle":
                x, y, radius = values
                geom = Part.Circle(FreeCAD.Vector(x, y, 0), FreeCAD.Vector(0, 0, 1), radius)
            else:
                x1, y1, x2, y2 = values
                geom = Part.LineSegment(FreeCAD.Vector(x1, y1, 0), FreeCAD.Vector(x2, y2, 0))
            index = sketch.addGeometry(geom, False)
            if constraint == "radius":
                sketch.addConstraint(Sketcher.Constraint("Radius", index, values[2]))
            elif constraint in ("horizontal", "vertical"):
                sketch.addConstraint(Sketcher.Constraint(constraint.title(), index))
        doc.recompute([sketch])
        states = [str(state) for state in getattr(sketch, "State", [])]
        if "Error" in states or "Invalid" in states or not sketch.isValid():
            raise ValueError("Sketch recomputation failed")
        result = {"document": doc.Name, "name": sketch.Name, "label": sketch.Label,
                  "geometry_count": sketch.GeometryCount, "constraint_count": sketch.ConstraintCount}
        try:
            doc.commitTransaction()
        except BaseException as exc:
            # FreeCAD observers can raise after a successful commit; never
            # abort a transaction that is now owned by another command.
            if FreeCAD.getActiveTransaction() == owned and owned is not None:
                raise
            if doc.getObject(sketch.Name) is not sketch:
                raise RuntimeError("Sketch commit outcome cannot be verified") from exc
            result["commit_observer_warning"] = "Sketch committed but a post-commit observer raised"
        return result
    except BaseException:
        if owned is not None and FreeCAD.getActiveTransaction() == owned:
            doc.abortTransaction()
        raise
