import json
import math
from freecad_addon.handlers import document
doc = App.newDocument("FollowupScratch")
doc.UndoMode = 1
seed = document.create_primitive("box", label="Preserve me", doc_name=doc.Name)
before = [obj.Name for obj in doc.Objects]
before_undo = doc.UndoCount
original = document._shape_summary
def fail_after_recompute(shape):
    assert shape.isValid() and shape.Volume > 0
    raise RuntimeError("Injected failure after real geometry recompute")
document._shape_summary = fail_after_recompute
try:
    try:
        document.create_primitive("sphere", doc_name=doc.Name)
        raise AssertionError("Expected injected failure")
    except RuntimeError as exc:
        assert "Injected failure" in str(exc), str(exc)
finally:
    document._shape_summary = original
assert [obj.Name for obj in doc.Objects] == before
assert doc.UndoCount == before_undo
assert not doc.HasPendingTransaction
assert App.getActiveTransaction() is None
assert math.isclose(doc.getObject(seed["name"]).Shape.Volume, 1000, rel_tol=1e-10)
print(json.dumps({"rollback": "passed", "objects": before, "undo_count": before_undo}))
sheet = doc.addObject("Spreadsheet::Sheet", "TestSheet")
sheet.set("A1", "Non-3D viewport regression")
doc.recompute()
Gui.activeDocument().setEdit(sheet.Name)
Gui.updateGui()
print(json.dumps({"actual_view": str(type(Gui.activeView())),
                  "doc_view": str(type(Gui.activeDocument().activeView())),
                  "actual_has_saveImage": hasattr(Gui.activeView(), "saveImage")}))
