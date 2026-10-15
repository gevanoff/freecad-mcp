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

Fix branch and evidence recorded after reproduction. Keep the default token
authentication and loopback listener. Arbitrary scripting is disabled by default;
for this controlled modeling test only, the process-local opt-in is needed because
the current standard tools cannot position, fuse, save, or export primitives.
No global environment variable is changed.

This is baseline-versus-fix testing by one agent using the craft playbooks, not
a blinded comparison of agent performance with and without those playbooks.
