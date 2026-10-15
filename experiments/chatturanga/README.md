# Live FreeCAD / Chatturanga experiment

Target: gevanoff/freecad-mcp main at
`19f80b8546bb45a5194813a627c9a2137b3e06e2`.
Machine: Windows, Python 3.14.2, official portable FreeCAD 1.1.4.
Brief: a simple foot-soldier study, 22 mm base diameter, 31.5 mm high,
Z up, parametric native master plus STEP and STL; no physical-print claim.

The first discovery pass used neka-nat/freecad-mcp because no local FreeCAD
integration was configured. Its separate link-list fix and evidence are preserved
in https://github.com/gevanoff/freecad-mcp-neka-nat. This experiment uses the
user's distinct implementation and does not mix the two source histories.

## A: unchanged production baseline

Branch `experiment/chatturanga-baseline`. Fresh `pip install -e . pytest`
installed MCP SDK 2.3.0, as allowed by `mcp[cli]>=1.2.0`. Starting `freecad-mcp`
failed with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`.
The SDK explains that 2.x renamed FastMCP to MCPServer. Existing tests nevertheless
passed: 33 passed, 1 skipped, 4 subtests passed. New startup tests perform a real
stdio initialize and tools/list handshake, both with script disabled and enabled.

## B: supported dependency and live CAD checks

Branch `fix/windows-live-cad-pilot`. Production fixes are commits `2b0dc24`
(dependency) and `2cc3542` (addon loader and exact bounds). Keep the default token
authentication and loopback listener. Arbitrary scripting is disabled by default;
for this controlled modeling test only, the process-local opt-in is needed because
the current standard tools cannot position, fuse, save, or export primitives.
No global environment variable is changed.

| Check | Before | After |
| --- | --- | --- |
| Clean package install/start | MCP 2.3.0 imports removed FastMCP; fails | Constraint selects 1.30.0; real stdio initialize/tools-list pass |
| FreeCAD addon load | `__file__` absent in InitGui exec; workbench missing | Resolve compiled filename; real workbench and port 9876 start |
| Radius-11 cylinder bounds | X span 21.9844096524 mm | X/Y spans 22 mm before and after screenshot |
| Test suite | 33 passed, 1 skipped before new regressions | unittest: 38 tests, 1 skipped; same result in clean non-editable installation |
| Model delivery | No successful client startup | Five editable features, one valid closed solid; FCStd reopen and STEP/STL reimport pass |

The bound comparison uses the identical `pilot.json` requests. The intermediate
`results/addon-fixed` run has dependency and loader fixes but retains the original
measurement implementation; `results/fixed` includes exact bounds. Production
source provenance is anchored by commits above and the installed handler SHA256
in `artifacts/validation.json`.

## Validation and files

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q src freecad_addon
.venv\Scripts\python.exe experiments\chatturanga\check_results.py
```

`artifacts/ChatturangaFootSoldier.FCStd` retains four parametric operands and a
refined union. The STEP round trip preserves its 4616.11791168 mm3 volume and
22 x 22 x 31.5 mm bounds. The STL has 4238 facets, is solid on reimport, and has
about 0.24% volume deviation from the curved master. Its coordinates are in mm;
STL itself does not encode units. Reimport checks are in FreeCAD, not a third-party
CAD application or slicer. No physical specimen was printed.

The runner retains tool errors to preserve diagnostic evidence; its process exit
code alone is not an acceptance check. `check_results.py` rejects unexpected MCP
errors, script-level failures, wrong bounds, or changed artifact hashes. Only
`results/validation` and `artifacts` represent the final handoff. Earlier failed
runs remain diagnostic evidence.

## Installed Windows setup

- FreeCAD portable: `C:/Users/paper/Code/.tools/freecad-1.1.4/FreeCAD_1.1.4-Windows-x86_64-py311/FreeCAD.exe`.
- Start Menu shortcut: **FreeCAD MCP** launches FreeCAD and `start_rpc.FCMacro`.
- Addon: `FreeCAD.getUserAppDataDir()/Mod/freecad_addon`; on this packaged-app
  launch Windows redirects APPDATA into the Codex package's LocalCache.
- Codex MCP name: `freecad`, command points to this checkout's
  `.venv/Scripts/freecad-mcp.exe`, no script opt-in in the saved configuration.
- Token created by `freecad-mcp-init`, remains local and is never committed.
- Only the custom addon is active. The other implementation is preserved outside
  the Mod directory to avoid their top-level `rpc_server` module collision.

Restart the client session to load its newly registered MCP. Keep FreeCAD open
with its listener started. For the controlled modeling scripts, explicitly set
`FREECAD_MCP_ALLOW_SCRIPT=1` in the launching shell for both FreeCAD and the
runner; close that session and restart without it afterward. Standard tools
remain script-disabled by default. The completed model was left open after
restarting in that default mode.

This is baseline-versus-fix testing by one agent using the craft playbooks, not
a blinded comparison of agent performance with and without those playbooks.
