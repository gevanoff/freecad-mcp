"""Build the four-primitive study through the opt-in execute_script MCP tool."""
import Part

doc = App.getDocument("ChatturangaCurrent")
assert len(doc.Objects) == 1 and doc.Objects[0].Name == "MCPPrimitive"
base = doc.MCPPrimitive
base.Label = "Base (22 mm diameter)"
body = doc.addObject("Part::Cone", "Body")
body.Radius1, body.Radius2, body.Height = 8.5, 4.5, 18
body.Placement.Base.z = 3
collar = doc.addObject("Part::Cylinder", "Collar")
collar.Radius, collar.Height = 6, 2.5
collar.Placement.Base.z = 20
head = doc.addObject("Part::Sphere", "Head")
head.Radius = 5.5
head.Placement.Base.z = 26
piece = doc.addObject("Part::MultiFuse", "FootSoldier")
piece.Shapes = [base, body, collar, head]
piece.Refine = True
doc.recompute()
assert piece.Shape.isValid() and len(piece.Shape.Solids) == 1
for operand in piece.Shapes:
    operand.ViewObject.Visibility = False
piece.Label = "Chatturanga Foot Soldier"
piece.ViewObject.ShapeColor = (0.78, 0.60, 0.34)
piece.ViewObject.Deviation = 0.1
Gui.activeDocument().activeView().viewAxonometric()
Gui.activeDocument().activeView().fitAll()
Gui.updateGui()
print("Created one valid solid with four editable operands")
