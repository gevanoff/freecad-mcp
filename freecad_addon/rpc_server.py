"""Authenticated, bounded loopback RPC for the FreeCAD add-on."""

from __future__ import annotations

import hmac
import json
import logging
import os
import queue
import socket
import threading
import time
import traceback
from typing import Any, Callable

try:
    from .local_config import read_token
except ImportError:  # FreeCAD loads add-on modules from its Mod path as top-level modules.
    from local_config import read_token

logger = logging.getLogger("freecad_mcp.rpc")
HOST = "127.0.0.1"
PORT = int(os.environ.get("FREECAD_MCP_PORT", "9876"))
if not 1 <= PORT <= 65535:
    raise ValueError("FREECAD_MCP_PORT must be between 1 and 65535")
MAX_FRAME_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CLIENTS = 4
MAX_QUEUED_CALLS = 16
CLIENT_READ_TIMEOUT = 10.0
MAIN_THREAD_TIMEOUT = 35.0
POLL_INTERVAL_MS = 50


class RPCServer:
    def __init__(self, port: int = PORT):
        self.port = port
        self._handlers: dict[str, Callable] = {"ping": lambda: {"status": "ok"}}
        self._socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._running = False
        # Synchronize queue admission, GUI dispatch, shutdown, and restart.
        self._state_lock = threading.RLock()
        self._generation = 0
        self._active_jobs: list[dict[str, Any]] = []
        self._token: str | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUED_CALLS)
        self._clients = threading.BoundedSemaphore(MAX_CLIENTS)
        self._timer = None

    @property
    def is_running(self) -> bool:
        return self._running

    def register_all(self, handlers: dict[str, Callable]) -> None:
        self._handlers.update(handlers)

    def start(self) -> None:
        with self._state_lock:
            if self._running:
                return
        try:
            from PySide2 import QtCore
        except ImportError:
            from PySide6 import QtCore
        token = read_token()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        timer = None
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((HOST, self.port))
            listener.listen(MAX_CLIENTS)
            listener.settimeout(1.0)
            timer = QtCore.QTimer()
            timer.timeout.connect(self._drain_one)
            timer.start(POLL_INTERVAL_MS)
        except Exception:
            if timer is not None:
                timer.stop()
            listener.close()
            raise
        with self._state_lock:
            self._generation += 1
            generation = self._generation
            self._token = token
            self._socket = listener
            self._timer = timer
            self._running = True
            thread = threading.Thread(
                target=self._accept_loop, args=(listener, generation), daemon=True)
            self._accept_thread = thread
            thread.start()
        logger.info("FreeCAD MCP RPC listening on %s:%d", HOST, self.port)

    def stop(self) -> None:
        with self._state_lock:
            self._running = False
            # Retire the session before allowing a later Start, even when
            # the same token and RPCServer instance are reused.
            self._generation += 1
            while True:
                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    break
                with job["lock"]:
                    if job["state"] == "queued":
                        job["state"] = "cancelled"
                        job["cancel_reason"] = "shutdown"
                    job["event"].set()
            for job in self._active_jobs:
                with job["lock"]:
                    # Running FreeCAD GUI operations cannot be rolled back
                    # safely by a socket thread: tell callers the outcome
                    # is unknown, even if the handler finishes later.
                    job["shutdown_while_running"] = True
                    job["event"].set()
            timer, self._timer = self._timer, None
            listener, self._socket = self._socket, None
            accept_thread, self._accept_thread = self._accept_thread, None
            self._token = None
        if timer is not None:
            timer.stop()
        if listener is not None:
            listener.close()
        if accept_thread is not None:
            accept_thread.join(timeout=2)

    def _accept_loop(self, listener: socket.socket, generation: int) -> None:
        while True:
            with self._state_lock:
                if not self._running or generation != self._generation:
                    return
            try:
                client, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._state_lock:
                if not self._running or generation != self._generation:
                    client.close()
                    return
                allowed = self._clients.acquire(blocking=False)
            if not allowed:
                client.close()
                continue
            threading.Thread(
                target=self._client_loop,
                args=(client, address, generation), daemon=True).start()

    def _client_loop(self, client: socket.socket, address: tuple, generation: int) -> None:
        try:
            raw = self._read_frame(client)
            response = self._handle(raw, expected_generation=generation)
            encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
            if len(encoded) <= MAX_RESPONSE_BYTES:
                client.settimeout(2.0)
                client.sendall(encoded)
        except Exception as exc:
            logger.debug("RPC client %s failed: %s", address, exc)
        finally:
            client.close()
            self._clients.release()

    @staticmethod
    def _read_frame(client: socket.socket) -> bytes:
        data = bytearray()
        deadline = time.monotonic() + CLIENT_READ_TIMEOUT
        while True:
            frame_remaining = MAX_FRAME_BYTES - len(data)
            if frame_remaining <= 0:
                raise ValueError("RPC request exceeds the 1 MiB frame limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("RPC frame deadline exceeded")
            if hasattr(client, "settimeout"):
                client.settimeout(remaining)
            part = client.recv(min(4096, frame_remaining))
            if not part:
                raise ConnectionError("client disconnected before a complete frame")
            pos = part.find(b"\n")
            if pos >= 0:
                data.extend(part[:pos])
                return bytes(data)
            data.extend(part)

    def _handle(self, raw: bytes, expected_generation: int | None = None) -> dict[str, Any]:
        try:
            request = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(None, -32700, "Parse error")
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "Invalid request")
        req_id = request.get("id")
        supplied = request.get("token")
        method = request.get("method")
        params = request.get("params", {})
        with self._state_lock:
            if not self._running or (
                    expected_generation is not None and
                    expected_generation != self._generation):
                return self._error(req_id, -32006, "RPC server session stopped; request not executed")
            if not isinstance(supplied, str) or not hmac.compare_digest(supplied, self._token or ""):
                return self._error(req_id, -32001, "Unauthorized")
            if not isinstance(method, str) or not isinstance(params, dict) or req_id is None:
                return self._error(req_id, -32600, "Invalid request")
            handler = self._handlers.get(method)
            if handler is None:
                return self._error(req_id, -32601, "Method not found")
            job = {
                "handler": handler, "params": params, "event": threading.Event(),
                "lock": threading.Lock(), "state": "queued", "result": None,
                "generation": self._generation, "cancel_reason": None,
                "shutdown_while_running": False,
            }
            try:
                self._queue.put_nowait(job)
            except queue.Full:
                return self._error(req_id, -32002, "FreeCAD is busy; retry later")

        if not job["event"].wait(MAIN_THREAD_TIMEOUT):
            # Synchronize deadline cancellation with GUI dispatch. Once
            # running, no caller may safely assume a timed-out CAD action
            # was rolled back or did not execute.
            with job["lock"]:
                if job["state"] == "queued":
                    job["state"] = "cancelled"
                    job["cancel_reason"] = "deadline"
        with job["lock"]:
            if job["state"] == "cancelled":
                if job["cancel_reason"] == "shutdown":
                    return self._error(req_id, -32006,
                                       "RPC server stopped before execution; operation cancelled")
                return self._error(req_id, -32003,
                                   "Timed out before execution; operation cancelled")
            if job["shutdown_while_running"] or job["state"] == "running":
                return self._error(req_id, -32005,
                                   "FreeCAD operation is still running or was interrupted by shutdown; "
                                   "outcome is unknown. Inspect the document before retrying.")
            if "error" in job:
                return self._error(req_id, -32000, job["error"][:8192])
            result = job["result"]
        response = {"jsonrpc": "2.0", "result": result, "id": req_id}
        if len(json.dumps(response, separators=(",", ":")).encode("utf-8")) + 1 > MAX_RESPONSE_BYTES:
            return self._error(req_id, -32004,
                               "RPC response exceeds the 4 MiB limit after execution; "
                               "the operation may have completed. Inspect the document before retrying.")
        return response

    def _drain_one(self) -> None:
        with self._state_lock:
            if not self._running:
                return
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                return
            with job["lock"]:
                if job["state"] == "cancelled":
                    job["event"].set()
                    return
                if job["generation"] != self._generation:
                    job["state"] = "cancelled"
                    job["cancel_reason"] = "shutdown"
                    job["event"].set()
                    return
                job["state"] = "running"
                self._active_jobs.append(job)
        try:
            job["result"] = job["handler"](**job["params"])
        except Exception as exc:
            job["error"] = f"{type(exc).__name__}: {exc}\\n{traceback.format_exc(limit=8)}"
        finally:
            with self._state_lock:
                with job["lock"]:
                    job["state"] = "finished"
                    job["event"].set()
                self._active_jobs.remove(job)

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}

