import json
import socketserver
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.control_client import ControlClient, append_shadow_diff


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while line := self.rfile.readline():
            request = json.loads(line)
            self.server.requests.append(request)
            action = self.server.actions.pop(0) if self.server.actions else None
            if action == "disconnect":
                return
            if action == "timeout":
                time.sleep(0.1)
                continue
            result = action if isinstance(action, dict) else {"op": request["op"]}
            response_id = request["id"] + 1 if action == "wrong-id" else request["id"]
            self.wfile.write(
                (json.dumps({"id": response_id, "ok": True, "result": result}) + "\n").encode()
            )


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, actions=()):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.actions = list(actions)
        self.requests = []


class ControlClientTest(unittest.TestCase):
    def setUp(self):
        self.server = _Server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def client(self, **kwargs):
        client = ControlClient(
            self.server.server_address[1], request_budget=0.08, backoff=0, **kwargs
        )
        self.addCleanup(client.close)
        return client

    def test_newline_framing_persistent_connection_and_ids(self):
        client = self.client()
        self.assertEqual(client.request("state", map=False), {"op": "state"})
        self.assertEqual(client.request("messages"), {"op": "messages"})
        self.assertEqual([row["id"] for row in self.server.requests], [1, 2])
        self.assertFalse(self.server.requests[0]["map"])

    def test_id_mismatch_reconnects_and_retries(self):
        self.server.actions[:] = ["wrong-id", {"turn": 7}]
        self.assertEqual(self.client().request("state", map=False), {"turn": 7})
        self.assertEqual(len(self.server.requests), 2)

    def test_timeout_is_bounded_and_logged_once(self):
        self.server.actions[:] = ["timeout", "timeout"]
        messages = []
        client = self.client(log=messages.append)
        started = time.monotonic()
        self.assertIsNone(client.request("state", map=False))
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertIsNone(client.request("state", map=False))
        self.assertEqual(len(messages), 1)

    def test_two_request_shadow_shares_one_budget(self):
        self.server.actions[:] = [{"turn": 1}, "timeout"]
        client = self.client()
        started = time.monotonic()
        self.assertIsNone(append_shadow_diff(
            client, {"turn": 1, "messages": []}, decision_sequence=1,
            path=Path("unused.jsonl"),
        ))
        self.assertLess(time.monotonic() - started, 0.13)

    def test_shadow_write_failure_is_diagnostic_only(self):
        self.server.actions[:] = [{"turn": 1}, {"messages": []}]
        messages = []
        client = self.client(log=messages.append)
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            self.assertIsNone(append_shadow_diff(
                client, {"turn": 1, "messages": []}, decision_sequence=1,
                path=Path("unwritable.jsonl"),
            ))
        self.assertEqual(len(messages), 1)

    def test_keys_and_quit_are_refused_before_composition(self):
        client = self.client()
        with self.assertRaises(ValueError):
            client.request("keys", keys="j")
        with self.assertRaises(ValueError):
            client.request("quit")
        self.assertEqual(self.server.requests, [])

    def test_shadow_record_shape_and_normalization(self):
        self.server.actions[:] = [
            {"turn": 9, "player": {"hp": 3}, "cursor": {"x": 1}},
            {"messages": ["same"]},
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.jsonl"
            row = append_shadow_diff(
                self.client(),
                {
                    "turn": 9,
                    "player": {"hp": 3},
                    "messages": ["same"],
                    "timestamp": "volatile",
                    "nearby_grids": [1],
                },
                decision_sequence=12,
                path=path,
            )
            self.assertTrue(row["equal"])
            self.assertEqual(row["diff_keys"], [])
            self.assertEqual(set(row), {
                "decision_sequence", "turn_jsonl", "turn_tcp", "equal",
                "diff_keys", "latency_ms",
            })
            self.assertEqual(json.loads(path.read_text()), row)

    def test_policy_finishes_before_shadow_and_never_receives_tcp(self):
        events = []
        jsonl = {"turn": 1, "player": {"hp": 1}, "messages": []}
        self.server.actions[:] = [jsonl, {"messages": []}]

        def policy(snapshot):
            events.append(("policy", snapshot))
            return "5"

        key = policy(jsonl)
        with TemporaryDirectory() as directory:
            append_shadow_diff(
                self.client(), jsonl, decision_sequence=1,
                path=Path(directory) / "unused.jsonl",
            )
        events.append(("shadow", key))
        self.assertEqual(events, [("policy", jsonl), ("shadow", "5")])


class DisabledCliPinTest(unittest.TestCase):
    def test_disabled_parser_does_not_import_or_connect_or_write(self):
        from hengbot import cli

        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"HENGBOT_CONTROL_PORT": ""}, clear=False
        ):
            shadow = Path(directory) / "tcp-shadow-diff.jsonl"
            sys.modules.pop("hengbot.control_client", None)
            args = cli._build_argument_parser().parse_args(
                ["--state-file", str(Path(directory) / "state.jsonl")]
            )
            self.assertIsNone(args.control_port)
            args.shadow_client = None
            snapshot = {"turn": 1}
            chosen_key = (lambda authoritative: "5")(snapshot)
            cli._record_tcp_shadow(args, snapshot, 1)
            self.assertEqual(chosen_key, "5")
            self.assertNotIn("hengbot.control_client", sys.modules)
            self.assertFalse(shadow.exists())

    def test_invalid_environment_port_is_an_argparse_error(self):
        from hengbot import cli

        with patch.dict("os.environ", {"HENGBOT_CONTROL_PORT": "not-a-port"}):
            parser = cli._build_argument_parser()
            with self.assertRaises(SystemExit) as stopped:
                parser.parse_args(["--state-file", "state.jsonl"])
        self.assertEqual(stopped.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
