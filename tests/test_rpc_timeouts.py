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
