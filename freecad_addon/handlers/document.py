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
    # FreeCAD transaction ownership is application-wide. Opening a transaction
    # on B can commit an existing GUI transaction on A, so inspect every document.
    # Document.HasPendingTransaction is false for a GUI transaction booked
    # before its first edit. The application-level transaction must be checked
    # first or doc.openTransaction() can replace the GUI's undo/Cancel scope.
    try:
        booked_transaction = FreeCAD.getActiveTransaction()
    except (AttributeError, TypeError) as exc:
        raise RuntimeError("Cannot verify FreeCAD application transaction ownership") from exc
    if booked_transaction is not None:
        raise RuntimeError("A FreeCAD GUI transaction is already booked; finish or cancel it first")
    if any(bool(open_doc.HasPendingTransaction)
           for open_doc in FreeCAD.listDocuments().values()):
        raise RuntimeError("A FreeCAD document has a pending GUI transaction; finish or cancel it first")
    # With UndoMode=0, FreeCAD's document transactions do not record edits:
    # abortTransaction() then cannot undo a partially created feature.
    if getattr(doc, "UndoMode", None) != 1:
        raise RuntimeError("FreeCAD document undo transactions are disabled")
    undo_before = tuple(doc.UndoNames)
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
        try:
            doc.commitTransaction()
        except BaseException as exc:
            # Commit observers can throw *after* FreeCAD finalizes the undo
            # transaction. In that case abortTransaction would be a no-op and
            # reporting failure would hide a successfully created object.
            if bool(doc.HasPendingTransaction):
                raise
            undo_after = tuple(doc.UndoNames)
            committed = (undo_after != undo_before
                         and "MCP: create primitive" in undo_after
                         and doc.getObject(obj.Name) is obj)
            if not committed:
                raise RuntimeError("Primitive commit outcome cannot be verified") from exc
            result["commit_observer_warning"] = (
                "Primitive committed, but a FreeCAD post-commit observer raised"
            )
    except BaseException:
        # Do not abort a transaction that already completed: it may have no
        # active pointer, or another GUI command may now own the global state.
        # A booked application transaction may have no document undo record
        # yet (e.g. addObject failed before its first edit). Still abort our
        # booking, but never interfere with a different transaction owner.
        if bool(doc.HasPendingTransaction) or FreeCAD.getActiveTransaction() is not None:
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

