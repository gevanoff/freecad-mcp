# FreeCAD MCP

A cross-client Model Context Protocol server for a live FreeCAD GUI session.
The MCP process uses stdio; a small FreeCAD add-on exposes a bounded RPC service
on loopback for document inspection and controlled model operations.

## Security model

- The add-on binds only to `127.0.0.1`.
- Every RPC request requires a per-user bearer token stored in the local config
  directory with owner-only permissions on POSIX systems.
- Request frames (1 MiB), response frames (4 MiB including the newline),
  concurrent clients, queued operations, and execution time are bounded.
  Responses above the limit receive a JSON-RPC error rather than being sent;
  the operation may already have completed, so inspect before retrying.
- Arbitrary Python execution is disabled by default. Enabling it grants the MCP
  client the ability to execute code with the FreeCAD process's full privileges.
- This is a local-user boundary, not a sandbox against malicious code running
  as the same OS user.

The design was informed by a review of [theosib/FreeCAD-MCP-Server](https://github.com/theosib/FreeCAD-MCP-Server).
This is a fresh implementation, not a fork; the upstream project is credited as
a design reference.

## Development status

The authenticated bridge and initial modeling/inspection tools have been tested
with FreeCAD 1.1.4 on Windows. A Chatturanga foot-soldier pilot was created through
MCP and saved/reopened as FCStd, STEP and STL. See the
[reproducible experiment and limits](https://github.com/gevanoff/freecad-mcp/blob/codex_test-rollback-viewport-slicer/experiments/chatturanga/README.md).
Follow-up [rollback, timeout, viewport, and X1E slicer tests](https://github.com/gevanoff/freecad-mcp/blob/codex_test-rollback-viewport-slicer/experiments/followup/README.md)
include live FreeCAD evidence and a sliced PLA project. The generated
experiment outputs remain on the experimental branch rather than on `main`.
The standard tools currently create basic primitives and inspect documents;
positioning, Boolean composition, saving and export require the optional script
tool. This is not yet a full constrained modeling toolset.

## Install the MCP process

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
freecad-mcp-init
```

On Windows, activate `.venv\Scripts\activate` instead. Install or symlink the
`freecad_addon` directory into FreeCAD's `Mod` directory, then restart FreeCAD.
The add-on starts with its RPC listener stopped; activate the **FreeCAD MCP**
workbench and choose **Start RPC Server**.

For FreeCAD 1.1 on Windows, the user addon directory is normally
`%APPDATA%\FreeCAD\v1-1\Mod\freecad_addon` (containing `InitGui.py` directly).
Confirm the running instance's location with `FreeCAD.getUserAppDataDir()` if
using a portable or packaged launcher; Windows app virtualization can redirect
this directory. The Python server currently supports MCP SDK 1.x and declares
`mcp[cli]>=1.2.0,<2`; install from this checkout to obtain that constraint.

Configure any MCP client that supports stdio servers to run `freecad-mcp` from
the project environment. For example, the generic command shape is:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "/absolute/path/to/.venv/bin/freecad-mcp"
    }
  }
}
```

On Windows, use the absolute path to `.venv\\Scripts\\freecad-mcp.exe`.

## Optional arbitrary script tool

The `execute_script` tool is intentionally absent by default. To expose it, set
`FREECAD_MCP_ALLOW_SCRIPT=1` in both the FreeCAD process environment and the MCP
server environment, then restart both. This is equivalent to granting arbitrary
code execution in FreeCAD as your user. Do not enable it for untrusted clients.

## Configuration

RPC calls queued for more than 35 seconds are cancelled before execution
(`-32003`). Stop cancels any pending operations and fences requests from
an earlier server session (`-32006`). If execution has already started,
`-32005` reports an unknown
outcome: the operation may still commit. Inspect the document before retrying;
a transport failure or invalid RPC response after transmission also cannot
establish cancellation.
The client allows 40 seconds for the server's explicit deadline response.
Primitive and sketch creation require the target document to be active in
FreeCAD, even when `doc_name` is supplied. Screenshots require an active 3D view;
spreadsheet and other non-3D tabs are rejected with an instruction to activate
a 3D view.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FREECAD_MCP_TOKEN_FILE` | OS user config path | Shared secret file created by `freecad-mcp-init` |
| `FREECAD_MCP_CONFIG_DIR` | OS user config directory | Directory containing `token`; overridden by `FREECAD_MCP_TOKEN_FILE` |
| `FREECAD_MCP_HOST` | `127.0.0.1` | Client target; server refuses non-loopback binds |
| `FREECAD_MCP_PORT` | `9876` | Local RPC port |
| `FREECAD_MCP_ALLOW_SCRIPT` | unset | Expose the arbitrary Python tool when set to `1` |

Set token path overrides in both the FreeCAD process and the MCP process so
they read the same credential.

