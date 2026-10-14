"""Basic FreeCAD document enumeration and feature-tree inspection."""

from __future__ import annotations

import FreeCAD


def _resolve_doc(doc_name: str = ""):
    doc = FreeCAD.getDocument(doc_name) if doc_name else FreeCAD.ActiveDocument
    if doc is None:
        raise ValueError("No matching or active FreeCAD document")
    return doc


def list_documents() -> list[dict]:
    result = []
    for name, doc in FreeCAD.listDocuments().items():
        result.append({
            "name": name,
            "label": doc.Label,
            "file_path": getattr(doc, "FileName", ""),
            "object_count": len(doc.Objects),
            "modified": bool(getattr(doc, "Modified", False)),
        })
    return result


def create_document(name: str) -> dict:
    if not name or len(name) > 64 or not name.isascii() or not name[0].isalpha() or not name.replace("_", "").isalnum():
        raise ValueError("Document name must be 1–64 letters, digits, or underscores and start with a letter")
    doc = FreeCAD.newDocument(name)
    return {"name": doc.Name, "label": doc.Label}


def get_document_graph(doc_name: str = "") -> dict:
    doc = _resolve_doc(doc_name)
    objects = []
    for obj in doc.Objects:
        objects.append({
            "name": obj.Name,
            "label": obj.Label,
            "type_id": obj.TypeId,
            "properties": {
                key: _safe_value(getattr(obj, key, None))
                for key in obj.PropertiesList
            },
            "dependencies": [item.Name for item in getattr(obj, "OutList", [])],
            "is_valid": _safe_valid(obj),
            "state": list(getattr(obj, "State", [])),
        })
    return {"name": doc.Name, "label": doc.Label, "objects": objects}


def inspect_object(name: str, doc_name: str = "") -> dict:
    doc = _resolve_doc(doc_name)
    obj = doc.getObject(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    shape = getattr(obj, "Shape", None)
    return {
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "properties": {
            key: _safe_value(getattr(obj, key, None))
            for key in obj.PropertiesList
        },
        "is_valid": _safe_valid(obj),
        "shape": _shape_summary(shape) if shape is not None else None,
    }


def analyze_shape(name: str, doc_name: str = "") -> dict:
    result = inspect_object(name, doc_name)
    if result["shape"] is None:
        raise ValueError(f"Object '{name}' has no shape")
    return result["shape"]


def tracked_recompute(doc_name: str = "") -> dict:
    doc = _resolve_doc(doc_name)
    before = {obj.Name: _safe_valid(obj) for obj in doc.Objects}
    doc.recompute()
    after = {obj.Name: _safe_valid(obj) for obj in doc.Objects}
    return {
        "document": doc.Name,
        "new_errors": sorted(n for n, valid in after.items() if not valid and before.get(n, True)),
        "resolved": sorted(n for n, valid in after.items() if valid and not before.get(n, True)),
        "persistent_errors": sorted(n for n, valid in after.items() if not valid and not before.get(n, True)),
        "valid_count": sum(after.values()),
        "total_objects": len(after),
    }


def create_primitive(
    kind: str,
    label: str = "",
    length: float = 10,
    width: float = 10,
    height: float = 10,
    radius: float = 5,
    doc_name: str = "",
) -> dict:
    """Create one basic Part primitive after strict type/dimension validation."""
    if kind not in {"box", "cylinder", "sphere"}:
        raise ValueError("kind must be box, cylinder, or sphere")
    if len(label) > 128:
        raise ValueError("label must be 128 characters or shorter")
    dims = {"length": length, "width": width, "height": height, "radius": radius}
    for key, value in dims.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not (0.001 <= value <= 10000):
            raise ValueError(f"{key} must be between 0.001 and 10000 mm")

    doc = _resolve_doc(doc_name)
    type_id = {"box": "Part::Box", "cylinder": "Part::Cylinder", "sphere": "Part::Sphere"}[kind]
    # A failed recompute or invalid shape must not leave a partially constructed
    # feature behind. FreeCAD transactions also preserve undo history on success.
    if bool(doc.HasPendingTransaction):
        raise RuntimeError("Document has a pending GUI transaction; finish or cancel it first")
    doc.openTransaction("MCP: create primitive")
    try:
        obj = doc.addObject(type_id, "MCPPrimitive")
        if kind == "box":
            obj.Length, obj.Width, obj.Height = float(length), float(width), float(height)
        elif kind == "cylinder":
            obj.Radius, obj.Height = float(radius), float(height)
        else:
            obj.Radius = float(radius)
        if label:
            obj.Label = label
        doc.recompute([obj])
        # FreeCAD often records execution failures in State instead of raising.
        state = [str(item) for item in getattr(obj, "State", [])]
        if "Invalid" in state or "Error" in state or not _safe_valid(obj):
            raise ValueError("Created primitive failed recomputation: " + ", ".join(state))
        summary = _shape_summary(obj.Shape)
        if summary["is_null"] or not summary["is_valid"]:
            raise ValueError("Created primitive has an invalid or null shape")
        result = {"document": doc.Name, "name": obj.Name, "label": obj.Label,
                  "type_id": obj.TypeId, "shape": summary}
        doc.commitTransaction()
    except BaseException:
        doc.abortTransaction()
        raise
    return result


def _safe_valid(obj) -> bool | None:
    try:
        return bool(obj.isValid())
    except Exception:
        return None


def _safe_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return [float(value.x), float(value.y), float(value.z)]
    if hasattr(value, "Base") and hasattr(value, "Rotation"):
        return {"base": _safe_value(value.Base), "rotation": _safe_value(value.Rotation.Q)}
    if hasattr(value, "Name"):
        return value.Name
    return str(value)


def _shape_summary(shape) -> dict:
    return {
        "shape_type": shape.ShapeType,
        "is_valid": bool(shape.isValid()),
        "is_null": bool(shape.isNull()),
        "topology": {
            "vertices": len(shape.Vertexes),
            "edges": len(shape.Edges),
            "wires": len(shape.Wires),
            "faces": len(shape.Faces),
            "solids": len(shape.Solids),
        },
        "bounds": {
            "min": [shape.BoundBox.XMin, shape.BoundBox.YMin, shape.BoundBox.ZMin],
            "max": [shape.BoundBox.XMax, shape.BoundBox.YMax, shape.BoundBox.ZMax],
        },
        "area": float(shape.Area),
        "volume": float(shape.Volume) if shape.Solids else None,
    }

