from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "freecad_addon"))

from freecad_mcp.bridge import BridgeError, FreeCADBridge
from freecad_mcp.config import read_token, token_path
from freecad_addon.rpc_server import MAX_FRAME_BYTES, RPCServer


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["FREECAD_MCP_TOKEN_FILE"] = str(Path(self.temp.name) / "token")

    def tearDown(self):
        os.environ.pop("FREECAD_MCP_TOKEN_FILE", None)
        self.temp.cleanup()

    def test_missing_token_fails_closed(self):
        with self.assertRaises(RuntimeError):
            read_token()

    def test_token_requires_minimum_strength(self):
        token_path().write_text("short\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            read_token()

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are not portable on Windows")
    def test_token_rejects_group_or_world_readable_permissions(self):
        path = token_path()
        path.write_text("x" * 48, encoding="utf-8")
        path.chmod(0o644)
        with self.assertRaises(RuntimeError):
            read_token()


class RPCSecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = RPCServer()
        self.server._token = "t" * 48

    def test_unauthorized_request_never_reaches_handler(self):
        called = []
        self.server.register_all({"touch": lambda: called.append(True)})
        response = self.server._handle(json.dumps({
            "jsonrpc": "2.0", "method": "touch", "params": {}, "id": 1,
            "token": "wrong",
        }).encode())
        self.assertEqual(response["error"]["code"], -32001)
        self.assertEqual(called, [])

    def test_handler_executes_only_after_authenticated_dispatch(self):
        self.server.register_all({"sum": lambda left, right: left + right})
        request = json.dumps({
            "jsonrpc": "2.0", "method": "sum", "params": {"left": 3, "right": 4},
            "id": 7, "token": self.server._token,
        }).encode()
        outcome = {}
        thread = threading.Thread(target=lambda: outcome.setdefault("response", self.server._handle(request)))
        thread.start()
        deadline = time.monotonic() + 2
        while self.server._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.server._drain_one()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome["response"]["result"], 7)
        self.assertEqual(outcome["response"]["id"], 7)

    def test_frame_limit_applies_before_newline(self):
        class FakeClient:
            def recv(self, size):
                return b"x" * size
        with self.assertRaises(ValueError):
            self.server._read_frame(FakeClient())

    def test_bad_request_shape_is_rejected(self):
        request = json.dumps({
            "jsonrpc": "2.0", "method": "ping", "params": [], "id": 2,
            "token": self.server._token,
        }).encode()
        response = self.server._handle(request)
        self.assertEqual(response["error"]["code"], -32600)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = "z" * 48
        os.environ["FREECAD_MCP_TOKEN_FILE"] = str(Path(self.temp.name) / "token")
        Path(os.environ["FREECAD_MCP_TOKEN_FILE"]).write_text(self.token, encoding="utf-8")
        Path(os.environ["FREECAD_MCP_TOKEN_FILE"]).chmod(0o600)
        os.environ["FREECAD_MCP_HOST"] = "127.0.0.1"
        os.environ["FREECAD_MCP_PORT"] = "9876"

    def tearDown(self):
        for key in ("FREECAD_MCP_TOKEN_FILE", "FREECAD_MCP_HOST", "FREECAD_MCP_PORT"):
            os.environ.pop(key, None)
        self.temp.cleanup()

    def test_rejects_non_loopback_targets(self):
        os.environ["FREECAD_MCP_HOST"] = "0.0.0.0"
        with self.assertRaises(ValueError):
            FreeCADBridge()

    def test_authenticates_and_checks_response_id(self):
        bridge = FreeCADBridge()
        class FakeSocket:
            def __init__(self):
                self.response = b""
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def settimeout(self, _):
                pass
            def sendall(self, raw):
                req = json.loads(raw.split(b"\n", 1)[0])
                self_id = req["id"]
                self.assert_token = req["token"]
                self.response = json.dumps({"jsonrpc": "2.0", "id": self_id,
                                            "result": {"ok": True}}).encode() + b"\n"
            def recv(self, size):
                data, self.response = self.response[:size], self.response[size:]
                return data
        fake = FakeSocket()
        with patch("freecad_mcp.bridge.socket.create_connection", return_value=fake):
            self.assertEqual(bridge.call("ping"), {"ok": True})
        self.assertEqual(fake.assert_token, self.token)


if __name__ == "__main__":
    unittest.main()

