"""FreeCAD-side copy of the small shared-token configuration helper."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def token_path() -> Path:
    override = os.environ.get("FREECAD_MCP_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        return Path(root or Path.home() / "AppData" / "Local") / "FreeCADMCP" / "token"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FreeCADMCP" / "token"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "freecad-mcp" / "token"


def read_token() -> str:
    path = token_path()
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"MCP token must be a regular file: {path}")
        if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError(f"MCP token permissions are too broad; expected 0600: {path}")
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Cannot read MCP token at {path}; run `freecad-mcp-init` first") from exc
    if len(token) < 40 or "\n" in token:
        raise RuntimeError(f"Invalid or weak MCP token file: {path}")
    return token

