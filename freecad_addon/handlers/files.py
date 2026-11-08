"""Explicit local file operations with no replacement of existing files."""

from __future__ import annotations

import os
import tempfile

import FreeCAD
from handlers.document import _resolve_doc


def _path(path, extensions):
    if not isinstance(path, str) or not path or len(path) > 4096 or not os.path.isabs(path):
        raise ValueError("An absolute local file path is required")
    if os.path.splitext(path)[1].lower() not in extensions:
        raise ValueError("Unsupported file extension")
    return os.path.abspath(path)


def _require_quiescent():
    try:
        booked = FreeCAD.getActiveTransaction()
    except (AttributeError, TypeError) as exc:
        raise RuntimeError("Cannot verify FreeCAD application transaction ownership") from exc
    if booked is not None or any(bool(d.HasPendingTransaction) for d in FreeCAD.listDocuments().values()):
        raise RuntimeError("FreeCAD has an active GUI transaction; finish or cancel it first")


def open_document(path: str) -> dict:
    """Open an existing FCStd file without replacing an already-open document."""
    path = _path(path, {".fcstd"})
    _require_quiescent()
    if not os.path.isfile(path) or os.path.getsize(path) > 100 * 1024 * 1024:
        raise ValueError("FCStd file must exist and be at most 100 MiB")
    target = os.path.normcase(os.path.realpath(path))
    if any(d.FileName and os.path.normcase(os.path.realpath(d.FileName)) == target
           for d in FreeCAD.listDocuments().values()):
        raise ValueError("That file is already open")
    doc = FreeCAD.openDocument(path)
    return {"name": doc.Name, "label": doc.Label, "file_path": doc.FileName}


def _publish_new(path, writer):
    """Write beside destination, then atomically link without replacing it."""
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        raise ValueError("Destination directory must exist")
    if os.path.lexists(path):
        raise FileExistsError("Destination already exists")
    with tempfile.TemporaryDirectory(prefix=".freecad-mcp-", dir=parent) as tmp:
        staged = os.path.join(tmp, "output" + os.path.splitext(path)[1])
        writer(staged)
        if not os.path.isfile(staged) or os.path.getsize(staged) == 0:
            raise RuntimeError("FreeCAD did not produce a non-empty output file")
        # A hard link creates the destination only if absent, including when a
        # competing process creates it after our preliminary check.
        os.link(staged, path)
    return {"path": path, "bytes": os.path.getsize(path)}


def save_document_copy(path: str, doc_name: str = "") -> dict:
    """Save an FCStd copy to a new path without changing the document's filename."""
    path = _path(path, {".fcstd"})
    _require_quiescent()
    doc = _resolve_doc(doc_name)
    return _publish_new(path, lambda staged: doc.saveCopy(staged))


def export_objects(path: str, names: list, doc_name: str = "") -> dict:
    """Export 1–16 named objects to a new STL or STEP file."""
    path = _path(path, {".stl", ".step", ".stp"})
    if (not isinstance(names, list) or not 1 <= len(names) <= 16
            or any(not isinstance(name, str) or not name or len(name) > 128 for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Provide 1–16 distinct object names")
    _require_quiescent()
    doc = _resolve_doc(doc_name)
    objects = []
    for name in names:
        obj = doc.getObject(name)
        shape = getattr(obj, "Shape", None) if obj is not None else None
        if shape is None or shape.isNull() or not shape.isValid() or not shape.Solids:
            raise ValueError(f"Object '{name}' must have a valid solid")
        objects.append(obj)
    if path.lower().endswith(".stl"):
        import Mesh
        writer = lambda staged: Mesh.export(objects, staged)
    else:
        import Part
        writer = lambda staged: Part.export(objects, staged)
    return _publish_new(path, writer)
