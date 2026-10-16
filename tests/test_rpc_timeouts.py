"""Cancellation and outcome reporting at the GUI dispatch boundary."""
import json
import threading
import unittest
from unittest.mock import patch

from freecad_addon.rpc_server import RPCServer


class RPCTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.server = RPCServer()
        self.server._token = "t" * 48
        self.server._running = True  # In-process dispatcher stands in for Start.

    def request(self):
        return json.dumps({"jsonrpc": "2.0", "method": "mutate", "params": {},
                           "id": 1, "token": self.server._token}).encode()

    def test_queued_timeout_never_mutates_when_gui_resumes(self):
        mutations = []
        self.server.register_all({"mutate": lambda: mutations.append("committed")})
        with patch("freecad_addon.rpc_server.MAIN_THREAD_TIMEOUT", 0.01):
            reply = self.server._handle(self.request())
        self.server._drain_one()
        self.assertEqual(mutations, [])
        self.assertEqual(reply["error"]["code"], -32003)
        self.assertIn("before execution", reply["error"]["message"])

    def test_running_timeout_reports_unknown_outcome_and_does_not_retry(self):
        queued, started, release = (threading.Event() for _ in range(3))
        mutations, replies = [], []
        original_put = self.server._queue.put_nowait
        def put(job):
            original_put(job)
            queued.set()
        def mutate():
            started.set()
            if not release.wait(2):
                raise RuntimeError("Test did not release handler")
            mutations.append("committed")
        self.server.register_all({"mutate": mutate})
        with patch.object(self.server._queue, "put_nowait", put), patch(
                "freecad_addon.rpc_server.MAIN_THREAD_TIMEOUT", 0.2):
            caller = threading.Thread(target=lambda: replies.append(self.server._handle(self.request())))
            caller.start()
            self.assertTrue(queued.wait(2))
            gui = threading.Thread(target=self.server._drain_one)
            gui.start()
            try:
                self.assertTrue(started.wait(2))
                caller.join(2)
                self.assertFalse(caller.is_alive())
                self.assertEqual(replies[0]["error"]["code"], -32005)
                self.assertIn("outcome is unknown", replies[0]["error"]["message"])
            finally:
                release.set()
                gui.join(2)
                caller.join(2)
        self.server._drain_one()
        self.assertEqual(mutations, ["committed"])

    def test_stop_cancels_queue_and_fences_pre_restart_connections(self):
        queued = threading.Event()
        mutations, replies = [], []
        self.server.register_all({"mutate": lambda: mutations.append("committed")})
        original_put = self.server._queue.put_nowait

        def put(job):
            original_put(job)
            queued.set()

        with patch.object(self.server._queue, "put_nowait", put):
            caller = threading.Thread(
                target=lambda: replies.append(self.server._handle(
                    self.request(), expected_generation=0)))
            caller.start()
            self.assertTrue(queued.wait(2))
            self.server.stop()
            caller.join(2)

        self.assertFalse(caller.is_alive(), "shutdown must wake queued callers")
        self.assertEqual(replies[0]["error"]["code"], -32006)
        self.assertEqual(mutations, [])
        self.assertTrue(self.server._queue.empty())

        # A subsequent Start uses the same object/token but a new generation.
        self.server._generation += 1
        self.server._running = True
        self.server._token = "t" * 48
        self.server._drain_one()
        self.assertEqual(mutations, [])
        stale = self.server._handle(self.request(), expected_generation=0)
        self.assertEqual(stale["error"]["code"], -32006)
        self.assertTrue(self.server._queue.empty())

        fresh = []
        caller = threading.Thread(
            target=lambda: fresh.append(self.server._handle(
                self.request(), expected_generation=self.server._generation)))
        caller.start()
        for _ in range(200):
            if not self.server._queue.empty():
                break
            threading.Event().wait(0.005)
        self.assertFalse(self.server._queue.empty(), "fresh call never queued")
        self.server._drain_one()
        caller.join(2)
        self.assertFalse(caller.is_alive())
        self.assertEqual(fresh[0]["result"], None)
        self.assertEqual(mutations, ["committed"])

    def test_stop_reports_unknown_outcome_for_running_operation(self):
        started, release = threading.Event(), threading.Event()
        mutations, replies = [], []

        def mutate():
            started.set()
            if not release.wait(2):
                raise RuntimeError("test did not release GUI handler")
            mutations.append("committed")

        self.server.register_all({"mutate": mutate})
        caller = threading.Thread(
            target=lambda: replies.append(self.server._handle(self.request())))
        caller.start()
        for _ in range(200):
            if not self.server._queue.empty():
                break
            threading.Event().wait(0.005)
        gui = threading.Thread(target=self.server._drain_one)
        gui.start()
        try:
            self.assertTrue(started.wait(2))
            self.server.stop()
            caller.join(2)
            self.assertFalse(caller.is_alive())
            self.assertEqual(replies[0]["error"]["code"], -32005)
            self.assertIn("outcome is unknown", replies[0]["error"]["message"])
        finally:
            release.set()
            gui.join(2)
            caller.join(2)
        self.assertEqual(mutations, ["committed"])
