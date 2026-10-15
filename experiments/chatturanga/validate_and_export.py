"""Executed inside FreeCAD through the MCP execute_script tool."""
import hashlib
import json
from pathlib import Path

import Import
import Mesh
import MeshPart
import Part

folder = Path(EXPERIMENT_DIR) / "artifacts"
folder.mkdir(parents=True, exist_ok=True)
doc = App.getDocument("ChatturangaCurrent")
piece = doc.getObject("FootSoldier")
assert [obj.Name for obj in piece.Shapes] == ["MCPPrimitive", "Body", "Collar", "Head"]


def check_shape(shape):
    # Default BoundBox can use the viewport's coarse triangulation. Check the
    # actual curved BRep surfaces, independently of display tessellation.
    bounds = shape.optimalBoundingBox(False, False)
    result = {
        "valid": shape.isValid(),
        "closed": shape.isClosed(),
        "solids": len(shape.Solids),
        "bounds_mm": [bounds.XLength, bounds.YLength, bounds.ZLength],
        "z_min_mm": bounds.ZMin,
        "volume_mm3": shape.Volume,
    }
    assert result["valid"] and result["closed"] and result["solids"] == 1, result
    assert all(abs(a - b) < 1e-5 for a, b in zip(result["bounds_mm"], [22, 22, 31.5])), result
    assert abs(result["z_min_mm"]) < 1e-5 and result["volume_mm3"] > 0, result
    return result


native_checks = check_shape(piece.Shape)
for operand in piece.Shapes:
    operand.ViewObject.Visibility = False
piece.Label = "Chatturanga Foot Soldier"
piece.ViewObject.ShapeColor = (0.78, 0.60, 0.34)
piece.ViewObject.DisplayMode = "Flat Lines"
doc.recompute()
native = folder / "ChatturangaFootSoldier.FCStd"
step = folder / "ChatturangaFootSoldier.step"
stl = folder / "ChatturangaFootSoldier.stl"
doc.saveAs(str(native))
Part.export([piece], str(step))
mesh = MeshPart.meshFromShape(Shape=piece.Shape, LinearDeflection=0.05,
                              AngularDeflection=0.15, Relative=False)
assert mesh.isSolid()
mesh.write(str(stl))

step_doc = App.newDocument("StepRoundTrip")
Import.insert(str(step), step_doc.Name)
step_doc.recompute()
imported_shapes = [obj.Shape for obj in step_doc.Objects if hasattr(obj, "Shape") and not obj.Shape.isNull()]
assert len(imported_shapes) == 1, len(imported_shapes)
step_checks = check_shape(imported_shapes[0])
assert abs(step_checks["volume_mm3"] - native_checks["volume_mm3"]) < 1e-5
App.closeDocument(step_doc.Name)

imported_mesh = Mesh.Mesh(str(stl))
mesh_bounds = imported_mesh.BoundBox
stl_checks = {
    "solid": imported_mesh.isSolid(),
    "facets": imported_mesh.CountFacets,
    "bounds_mm": [mesh_bounds.XLength, mesh_bounds.YLength, mesh_bounds.ZLength],
    "volume_mm3": imported_mesh.Volume,
}
assert stl_checks["solid"] and stl_checks["facets"] > 0
assert all(abs(a - b) < 0.1 for a, b in zip(stl_checks["bounds_mm"], [22, 22, 31.5]))
assert abs(stl_checks["volume_mm3"] / native_checks["volume_mm3"] - 1) < 0.01

App.closeDocument(doc.Name)
reopened = App.openDocument(str(native))
reopened_checks = check_shape(reopened.FootSoldier.Shape)
assert len(reopened.Objects) == 5
assert [obj.Name for obj in reopened.FootSoldier.Shapes] == ["MCPPrimitive", "Body", "Collar", "Head"]
Gui.activeDocument().activeView().viewAxonometric()
Gui.activeDocument().activeView().fitAll()
from handlers import document as document_handler
report = {
    "freecad_version": App.Version(),
    "installed_document_handler_sha256": hashlib.sha256(Path(document_handler.__file__).read_bytes()).hexdigest(),
    "native": native_checks, "reopened_native": reopened_checks,
    "step_reimport": step_checks, "stl_reimport": stl_checks,
    "units": "mm (STL consumer must select mm)", "axes": "Z up, base on Z=0",
    "physical_validation": "Not printed or physically tested",
    "artifact_sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in (native, step, stl)},
}
(folder / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

