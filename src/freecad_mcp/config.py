"""Shared local configuration for the FreeCAD add-on and MCP process."""

from __future__ import annotations

import os
import secrets
import stat
import sys
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("FREECAD_MCP_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        return Path(root or Path.home() / "AppData" / "Local") / "FreeCADMCP"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FreeCADMCP"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "freecad-mcp"


def token_path() -> Path:
    return Path(os.environ.get("FREECAD_MCP_TOKEN_FILE", config_dir() / "token")).expanduser()


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
        raise RuntimeError(
            f"Cannot read MCP token at {path}; run `freecad-mcp-init` first"
        ) from exc
    if len(token) < 40 or "\n" in token:
        raise RuntimeError(f"Invalid or weak MCP token file: {path}")
    return token


def initialize_token_file() -> None:
    """Create a random token without overwriting an existing credential."""
    path = token_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SystemExit(f"Token already exists at {path}; refusing to replace it") from exc
    except OSError as exc:
        raise SystemExit(f"Cannot create token at {path}: {exc}") from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(48) + "\n")
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    print(f"Created MCP token at {path}")

