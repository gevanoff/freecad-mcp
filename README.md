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
  Responses above the limit receive a JSON-RPC error rather than being sent.
- Arbitrary Python execution is disabled by default. Enabling it grants the MCP
  client the ability to execute code with the FreeCAD process's full privileges.
- This is a local-user boundary, not a sandbox against malicious code running
  as the same OS user.

The design was informed by a review of [theosib/FreeCAD-MCP-Server](https://github.com/theosib/FreeCAD-MCP-Server).
This is a fresh implementation, not a fork; the upstream project is credited as
a design reference.

## Development status

Initial implementation in progress. The stdio server and authenticated bridge
are being built first; the add-on's FreeCAD handlers follow. Live FreeCAD
integration has not yet been tested.

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

| Variable | Default | Purpose |
| --- | --- | --- |
| `FREECAD_MCP_TOKEN_FILE` | OS user config path | Shared secret file created by `freecad-mcp-init` |
| `FREECAD_MCP_HOST` | `127.0.0.1` | Client target; server refuses non-loopback binds |
| `FREECAD_MCP_PORT` | `9876` | Local RPC port |
| `FREECAD_MCP_ALLOW_SCRIPT` | unset | Expose the arbitrary Python tool when set to `1` |

