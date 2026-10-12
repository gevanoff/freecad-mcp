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

