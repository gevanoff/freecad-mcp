"""Authenticated, bounded loopback JSON-RPC client."""

from __future__ import annotations

import json
import os
import socket
import threading
from typing import Any

from freecad_mcp.config import read_token

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
MAX_FRAME_BYTES = 1024 * 1024
CONNECT_TIMEOUT = 3.0
CALL_TIMEOUT = 35.0


class BridgeError(RuntimeError):
    """Transport, authentication, or protocol failure."""


class FreeCADBridge:
    def __init__(self) -> None:
        self.host = os.environ.get("FREECAD_MCP_HOST", DEFAULT_HOST)
        self.port = int(os.environ.get("FREECAD_MCP_PORT", str(DEFAULT_PORT)))
        if self.host != "127.0.0.1":
            raise ValueError("FreeCAD MCP only permits loopback RPC targets")
        if not 1 <= self.port <= 65535:
            raise ValueError("FREECAD_MCP_PORT must be between 1 and 65535")
        self._token = read_token()
        self._lock = threading.Lock()
        self._next_id = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_request_id(),
            "token": self._token,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            raise BridgeError("RPC request exceeds the 1 MiB frame limit")

        try:
            with socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT) as sock:
                sock.settimeout(CALL_TIMEOUT)
                sock.sendall(raw)
                response = self._read_frame(sock)
        except OSError as exc:
            raise BridgeError(f"Cannot reach FreeCAD MCP at {self.host}:{self.port}: {exc}") from exc

        if response.get("id") != payload["id"]:
            raise BridgeError("Mismatched JSON-RPC response id")
        if "error" in response:
            err = response["error"]
            raise BridgeError(f"FreeCAD RPC error {err.get('code')}: {err.get('message')}")
        return response.get("result")

    def _next_request_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    @staticmethod
    def _read_frame(sock: socket.socket) -> dict[str, Any]:
        chunks = bytearray()
        while len(chunks) <= MAX_FRAME_BYTES:
            part = sock.recv(min(65536, MAX_FRAME_BYTES + 1 - len(chunks)))
            if not part:
                raise BridgeError("FreeCAD closed the RPC connection before replying")
            delimiter = part.find(b"\n")
            if delimiter >= 0:
                chunks.extend(part[:delimiter])
                try:
                    result = json.loads(chunks)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BridgeError(f"Invalid JSON-RPC response: {exc}") from exc
                if not isinstance(result, dict):
                    raise BridgeError("Invalid JSON-RPC response object")
                return result
            chunks.extend(part)
        raise BridgeError("FreeCAD RPC response exceeds the 1 MiB frame limit")

