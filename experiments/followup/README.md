# FreeCAD follow-up tests

Baseline: `69e65abc866f788de971184276dcf059de6da5f8` on
`fix/windows-live-cad-pilot`. Fixes and evidence are on the follow-up test branch.
Tested with FreeCAD 1.1.4 (Windows, embedded Python 3.11), MCP 1.30.0,
Python 3.14.2 client, and Bambu Studio 02.08.02.61.

## Results

| Scenario | Baseline | Revised implementation |
| --- | --- | --- |
| Exception after real primitive recompute | Rolls back correctly | Still passes; preserves existing solid, undo count, and transaction state |
| Screenshot with spreadsheet active | Internal `AttributeError: saveImage` | Actionable instruction to activate a 3D view |
| Screenshot with 3D view active | Works | Real PNG captured and visually inspected |
| Queued request exceeds deadline | Cancelled, generic timeout wording | Explicit cancellation before execution; no delayed mutation |
| Already-running request exceeds deadline | Same error as queued cancellation | Distinct unknown-outcome error; caller is told to inspect before retrying |
| Connection loss after sending | Misleading reachability error | Unknown outcome; no automatic retry |

The dispatcher now serializes cancellation against the transition to running.
It does not interrupt an OpenCascade operation or claim that a timeout rolls
back running work. A real delayed primitive test returned `-32005` and then
committed exactly one object. A second real test blocked the GUI while a
primitive waited: that primitive returned `-32003` and never appeared after
the GUI resumed. No user document was used for fault injection.

The unit suite passed 46 tests with one Windows-specific skip (POSIX token
permissions). Five live MCP/FreeCAD checks passed. Logs are in
`baseline-timeouts.txt`, `baseline-viewport.txt`, `baseline/responses.json`,
`fixed-unit-tests.txt`, and `fixed/`. These were self-reviewed in an engineering
critic role, not independently reviewed.

## Slicer result

`slicer/Chatturanga-X1E-PLA.3mf` contains the imported mesh, explicit project
settings, thumbnails, and actual sliced G-code. Effective settings were checked
inside the resulting archive: Bambu X1E, confirmed 0.4 mm nozzle, Generic PLA,
0.20 mm layers, two walls, 15% infill, supports off. Textured PEI Plate is a
provisional test assumption, not a confirmed property of the user's printer.

The round-tripped mesh is closed and consistently oriented, with 4,238
triangles and dimensions 22 x 22 x 31.5 mm. Bambu generated 157 layers, estimated
17m 44s and 2.63 g, with no reported slicing warning. Its thumbnail was visually
inspected. Slicing is not a physical print test; the lower head and collar
surfaces still need inspection on a printed sample. Confirm the actual plate
and filament brand/profile before printing. Nothing was sent to a printer.

The slicer-reported object box is a conservative transformed bounding box;
the vertex bounds in the 3MF preserve the original 22 mm diameter. See
`slicer/report.json` for the actual vertex bounds and effective settings.
The machine/process/filament snapshots were expanded from the installed
[Bambu Studio system profiles](https://github.com/bambulab/BambuStudio/tree/master/resources/profiles/BBL),
using its documented [command-line interface](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage).

## Reproduce

1. Initialize the usual shared token with `freecad-mcp-init` if necessary.
2. Open `start_test.FCMacro` in a separate FreeCAD process. It loads this
   checkout and opens an authenticated, test-only listener on loopback 9877,
   including the script handler. It does not change the installed add-on.
3. Run `.venv\Scripts\python.exe experiments/followup/live_checks.py` from the
   repository. It creates scratch documents, injects faults, and asserts every
   result, including the nested script success flag.
4. Close that scratch FreeCAD process to remove the test listener. The user's
   normal 9876 listener and original piece remain untouched.
5. With Bambu Studio installed at the path in `slice_piece.py`, run
   `.venv\Scripts\python.exe experiments/followup/slice_piece.py`. It uses
   local system profiles, saves a project, and validates the output. It does
   not access the printer. The script is specific to this confirmed X1E setup.

The runtime timeout tests shorten the server deadline only in the isolated
process, restoring it afterward. Unit tests run with
`python -m unittest discover -s tests -v`. The normal installed FreeCAD add-on
was not replaced during this experiment; installing these server-side fixes
requires copying the revised add-on and restarting FreeCAD.
