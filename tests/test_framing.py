"""Regression checks for asymmetric JSON-RPC frame limits.

These tests use local fake sockets and the in-process dispatch queue; FreeCAD
and a live GUI are not required.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from freecad_mcp.bridge import (
    BridgeError,
    FreeCADBridge,
    MAX_FRAME_BYTES as BRIDGE_MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES as BRIDGE_MAX_RESPONSE_BYTES,
)
from freecad_addon.rpc_server import (
    MAX_FRAME_BYTES as SERVER_MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES as SERVER_MAX_RESPONSE_BYTES,
    RPCServer,
)


class ChunkedSocket:
    def __init__(self, data: bytes, chunk_size: int = 65536):
        self.data = data
        self.chunk_size = chunk_size

    def recv(self, size: int) -> bytes:
        result = self.data[:min(size, self.chunk_size)]
        self.data = self.data[len(result):]
        return result

    def settimeout(self, timeout: float) -> None:
        pass


class FrameContractTests(unittest.TestCase):
    def test_request_and_response_limits_match_the_server(self):
        self.assertEqual(BRIDGE_MAX_REQUEST_BYTES, SERVER_MAX_REQUEST_BYTES)
        self.assertEqual(BRIDGE_MAX_RESPONSE_BYTES, SERVER_MAX_RESPONSE_BYTES)
        self.assertEqual(BRIDGE_MAX_REQUEST_BYTES, 1024 * 1024)
        self.assertEqual(BRIDGE_MAX_RESPONSE_BYTES, 4 * 1024 * 1024)

    def test_valid_response_larger_than_request_limit(self):
        result = {"base64_png": "A" * (BRIDGE_MAX_REQUEST_BYTES + 128)}
        frame = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result},
                           separators=(",", ":")).encode() + b"\n"
        self.assertGreater(len(frame), BRIDGE_MAX_REQUEST_BYTES)
        self.assertLess(len(frame), BRIDGE_MAX_RESPONSE_BYTES)
        self.assertEqual(FreeCADBridge._read_frame(ChunkedSocket(frame))["result"], result)

    def test_exact_maximum_response_frame_with_terminal_newline(self):
        template = {"jsonrpc": "2.0", "id": 1, "result": {"base64_png": ""}}
        empty_size = len(json.dumps(template, separators=(",", ":")).encode())
        data = "A" * (BRIDGE_MAX_RESPONSE_BYTES - empty_size - 1)
        template["result"]["base64_png"] = data
        frame = json.dumps(template, separators=(",", ":")).encode() + b"\n"
        self.assertEqual(len(frame), BRIDGE_MAX_RESPONSE_BYTES)
        self.assertEqual(FreeCADBridge._read_frame(ChunkedSocket(frame))["result"]["base64_png"], data)

    def test_response_with_delimiter_beyond_limit_is_rejected(self):
        with self.assertRaisesRegex(BridgeError, "4 MiB"):
            FreeCADBridge._read_frame(ChunkedSocket(b"x" * BRIDGE_MAX_RESPONSE_BYTES + b"\n"))

    def test_truncated_response_is_rejected(self):
        with self.assertRaisesRegex(BridgeError, "before replying"):
            FreeCADBridge._read_frame(ChunkedSocket(b'{"jsonrpc":'))

    def test_malformed_or_non_object_response_is_rejected(self):
        for frame in (b'{"jsonrpc":\n', b'["not a response"]\n'):
            with self.subTest(frame=frame), self.assertRaises(BridgeError):
                FreeCADBridge._read_frame(ChunkedSocket(frame))

    def test_request_boundary_includes_newline(self):
        self.assertEqual(RPCServer._read_frame(
            ChunkedSocket(b"x" * (SERVER_MAX_REQUEST_BYTES - 1) + b"\n", 4096)),
            b"x" * (SERVER_MAX_REQUEST_BYTES - 1))
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            RPCServer._read_frame(
                ChunkedSocket(b"x" * SERVER_MAX_REQUEST_BYTES + b"\n", 4096))

    def test_oversized_server_result_gets_bounded_protocol_error(self):
        server = RPCServer()
        server._token = "T" * 48
        server._running = True  # In-process dispatcher stands in for Start.
        server.register_all({"large": lambda: "A" * SERVER_MAX_RESPONSE_BYTES})
        outcome = {}
        request = json.dumps({
            "jsonrpc": "2.0", "id": 7, "token": server._token,
            "method": "large", "params": {},
        }).encode()

        thread = threading.Thread(
            target=lambda: outcome.setdefault("response", server._handle(request)))
        thread.start()
        deadline = time.monotonic() + 2
        while server._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(server._queue.empty(), "Request was not queued")
        server._drain_one()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome["response"]["error"]["code"], -32004)

    def test_server_accepts_compact_response_at_exact_byte_boundary(self):
        server = RPCServer()
        server._token = "T" * 48
        server._running = True  # In-process dispatcher stands in for Start.
        template = {"jsonrpc": "2.0", "result": "", "id": 9}
        content_length = SERVER_MAX_RESPONSE_BYTES - len(
            json.dumps(template, separators=(",", ":")).encode()) - 1
        data = "Z" * content_length
        server.register_all({"large": lambda: data})
        outcome = {}
        request = json.dumps({
            "jsonrpc": "2.0", "id": 9, "token": server._token,
            "method": "large", "params": {},
        }).encode()
        thread = threading.Thread(
            target=lambda: outcome.setdefault("response", server._handle(request)))
        thread.start()
        deadline = time.monotonic() + 2
        while server._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(server._queue.empty(), "Request was not queued")
        server._drain_one()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        response = outcome["response"]
        self.assertEqual(response["result"], data)
        frame = json.dumps(response, separators=(",", ":")).encode() + b"\n"
        self.assertEqual(len(frame), SERVER_MAX_RESPONSE_BYTES)
        self.assertEqual(FreeCADBridge._read_frame(ChunkedSocket(frame)), response)


if __name__ == "__main__":
    unittest.main()
