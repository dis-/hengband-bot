import json
import socketserver
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.control_client import (
    ControlClient,
    append_shadow_diff,
    raw_keys_to_macro_notation,
)


def _snapshot_line(turn):
    return json.dumps({
        "turn": turn,
        "player": {"y": 5, "x": 5, "hp": 10, "max_hp": 10},
        "floor": {"dungeon_id": 0, "level": 1},
    }) + "\n"


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
            if isinstance(action, str) and action.startswith("error:"):
                self.wfile.write((json.dumps({
                    "id": request["id"], "ok": False, "error": action[6:],
                }) + "\n").encode())
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
        self.assertEqual(client.request("info"), {"op": "info"})
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

    def test_absent_server_backoff_is_capped_by_request_budget(self):
        client = ControlClient(
            1, request_budget=1, retries=0, backoff=1,
            socket_factory=unittest.mock.Mock(side_effect=ConnectionRefusedError()),
        )
        with patch("hengbot.control_client.time.monotonic", return_value=10):
            self.assertIsNone(client.request("state", map=False))
            self.assertEqual(client._retry_after, 11)
            client._retry_after = 0
            self.assertIsNone(client.request("state", map=False))
            self.assertEqual(client._retry_after, 11)

    def test_backoff_skip_does_not_count_as_a_network_failure(self):
        factory = unittest.mock.Mock(side_effect=ConnectionRefusedError())
        client = ControlClient(
            1, request_budget=1, retries=0, backoff=1, socket_factory=factory,
        )
        with patch("hengbot.control_client.time.monotonic", return_value=10):
            self.assertIsNone(client.request("state", map=False))
            self.assertEqual(client._consecutive_failures, 1)
            self.assertIsNone(client.request("state", map=False))
            self.assertEqual(client._consecutive_failures, 1)
        self.assertEqual(factory.call_count, 1)

    def test_network_recovery_is_attempted_after_the_capped_window(self):
        connection = unittest.mock.Mock()
        connection.recv.return_value = b'{"id":1,"ok":true,"result":{"turn":7}}\n'
        factory = unittest.mock.Mock(
            side_effect=[ConnectionRefusedError(), connection]
        )
        client = ControlClient(
            1, request_budget=1, retries=0, backoff=100, socket_factory=factory,
        )
        with patch("hengbot.control_client.time.monotonic", return_value=10):
            self.assertIsNone(client.request("state", map=False))
            self.assertEqual(client._retry_after, 11)
        with patch("hengbot.control_client.time.monotonic", return_value=11):
            self.assertEqual(client.request("state", map=False), {"turn": 7})
        self.assertEqual(client._consecutive_failures, 0)

    def test_shadow_uses_state_history_without_redundant_messages_request(self):
        self.server.actions[:] = [{"turn": 1, "messages": ["old", "same"]}]
        with TemporaryDirectory() as directory:
            row = append_shadow_diff(
                self.client(), {"turn": 1, "messages": ["same"]},
                decision_sequence=1, path=Path(directory) / "shadow.jsonl",
            )
        self.assertTrue(row["equal"])
        self.assertEqual([request["op"] for request in self.server.requests], ["state"])

    def test_shadow_write_failure_is_diagnostic_only(self):
        self.server.actions[:] = [{"turn": 1, "messages": []}]
        messages = []
        client = self.client(log=messages.append)
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            self.assertIsNone(append_shadow_diff(
                client, {"turn": 1, "messages": []}, decision_sequence=1,
                path=Path("unwritable.jsonl"),
            ))
        self.assertEqual(len(messages), 1)

    def test_non_allowlisted_operations_are_refused_before_composition(self):
        client = self.client()
        for operation in ("screen", "messages", "quit"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                client.request(operation, keys="j" if operation == "keys" else None)
        self.assertEqual(self.server.requests, [])

    def test_send_keys_returns_acknowledged_count(self):
        self.server.actions[:] = [{"pushed": 4}]
        client = self.client()
        self.assertEqual(client.send_keys(r"~9\e\e"), 4)
        self.assertEqual(self.server.requests[0]["op"], "keys")
        self.assertEqual(self.server.requests[0]["keys"], r"~9\e\e")

    def test_send_keys_surfaces_server_error_without_raising(self):
        self.server.actions[:] = ["error:the key sequence is too long"]
        messages = []
        client = self.client(log=messages.append)
        self.assertIsNone(client.send_keys("j"))
        self.assertEqual(client.last_error, "the key sequence is too long")
        self.assertFalse(client.backpressured)
        self.assertIn("the key sequence is too long", messages[0])

    def test_send_keys_identifies_recoverable_backpressure(self):
        self.server.actions[:] = [
            "error:the key queue does not have enough room", {"pushed": 1},
        ]
        client = self.client()
        self.assertIsNone(client.send_keys("j"))
        self.assertTrue(client.backpressured)
        self.assertEqual(client.send_keys("j"), 1)
        self.assertFalse(client.backpressured)

    def test_real_key_corpus_round_trips_text_to_ascii_grammar(self):
        corpus = ("\x1b", "~9\x1b\x1b", "5pj\x1b", "pe3\r\r\x1b", "R300\r",
                  "0123456789", "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
                  "\\^", "\x01\x08\x09\x0a\x1f\x7f\xff")

        def text_to_ascii(notation):
            result = bytearray()
            index = 0
            named = {"e": 27, "b": 8, "t": 9, "n": 10, "r": 13,
                     "s": 32, "\\": 92, "^": 94}
            while index < len(notation):
                char = notation[index]
                if char == "\\":
                    index += 1
                    code = notation[index]
                    if code == "x":
                        result.append(int(notation[index + 1:index + 3], 16))
                        index += 2
                    else:
                        result.append(named[code])
                elif char == "^":
                    index += 1
                    result.append(ord(notation[index]) & 0x1f)
                else:
                    result.append(ord(char))
                index += 1
            return bytes(result)

        for raw in corpus:
            with self.subTest(raw=repr(raw)):
                notation = raw_keys_to_macro_notation(raw)
                self.assertEqual(text_to_ascii(notation), raw.encode("latin-1"))

    def test_shadow_record_shape_and_normalization(self):
        self.server.actions[:] = [
            {"turn": 9, "type": "player_turn", "player": {"hp": 3},
             "messages": ["old", "same"]},
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.jsonl"
            row = append_shadow_diff(
                self.client(),
                {
                    "turn": 9,
                    "player": {"hp": 3},
                    "type": "store", "messages": ["same"],
                    "nearby_grids": [1],
                    "grid_map": {"runs": [[1, 1, 1, 0]]},
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
        self.server.actions[:] = [jsonl]

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
    def _run_once_with_routes(self, tcp_result, events, *, control=True):
        from hengbot import cli

        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.jsonl"
            definitions = root / "MonraceDefinitions.jsonc"
            state.write_text(_snapshot_line(1), encoding="utf-8")
            definitions.write_text("{}", encoding="utf-8")
            policy = unittest.mock.Mock()
            policy._decision_sequence = 1
            policy.last_reason = "test:routing"
            policy.prompt_owner_handoff = None
            policy.choose_key.return_value = "5"
            policy.validate_read_key.return_value = "5"

            with (
                patch("hengbot.cli.find_monrace_definitions", return_value=definitions),
                patch("hengbot.cli.load_monrace_knowledge", return_value={}),
                patch("hengbot.cli.find_terrain_definitions", return_value=None),
                patch("hengbot.cli.find_outpost_map", return_value=None),
                patch("hengbot.cli.find_town_map", return_value=None),
                patch("hengbot.cli.find_wilderness_definition", return_value=None),
                patch("hengbot.cli.find_dungeon_definitions", return_value=None),
                patch("hengbot.cli.find_quest_definitions", return_value=None),
                patch("hengbot.cli.find_quest_strategies", return_value=None),
                patch("hengbot.cli._bot_play_macros_ready", return_value=False),
                patch("hengbot.cli.ConservativePolicy", return_value=policy),
                patch("hengbot.cli._configure_policy_output_paths", return_value=None),
                patch("hengbot.cli._capture_decision_facts", return_value={}),
                patch("hengbot.cli._write_decision"),
                patch("hengbot.cli._record_tcp_shadow"),
                patch(
                    "hengbot.control_client.ControlClient.send_keys",
                    side_effect=lambda *_a, **_k: events.append("tcp") or tcp_result,
                ),
                patch(
                    "hengbot.input_windows.send_key_to_window",
                    side_effect=lambda *_a, **_k: events.append("wm"),
                ),
            ):
                argv = ["--state-file", str(state), "--once", "--send-to-window"]
                if control:
                    argv.extend(["--control-port", "1"])
                return cli.main(argv)

    def test_tcp_success_never_duplicates_key_to_wm_char(self):
        events = []
        self.assertEqual(self._run_once_with_routes(1, events), 0)
        self.assertEqual(events, ["tcp"])

    def test_tcp_transport_failure_falls_back_to_wm_char_in_order(self):
        events = []
        self.assertEqual(self._run_once_with_routes(None, events), 0)
        self.assertEqual(events, ["tcp", "wm"])

    def test_control_port_without_tcp_shadow_sends_without_recording_shadow(self):
        from hengbot import cli

        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.jsonl"
            definitions = root / "MonraceDefinitions.jsonc"
            state.write_text(_snapshot_line(1), encoding="utf-8")
            definitions.write_text("{}", encoding="utf-8")
            policy = unittest.mock.Mock()
            policy._decision_sequence = 1
            policy.last_reason = "test:once-shadow"
            policy.prompt_owner_handoff = None
            policy.choose_key.return_value = "5"
            policy.validate_read_key.return_value = "5"

            with (
                patch("hengbot.cli.find_monrace_definitions", return_value=definitions),
                patch("hengbot.cli.load_monrace_knowledge", return_value={}),
                patch("hengbot.cli.find_terrain_definitions", return_value=None),
                patch("hengbot.cli.find_outpost_map", return_value=None),
                patch("hengbot.cli.find_town_map", return_value=None),
                patch("hengbot.cli.find_wilderness_definition", return_value=None),
                patch("hengbot.cli.find_dungeon_definitions", return_value=None),
                patch("hengbot.cli.find_quest_definitions", return_value=None),
                patch("hengbot.cli.find_quest_strategies", return_value=None),
                patch("hengbot.cli._bot_play_macros_ready", return_value=False),
                patch("hengbot.cli.ConservativePolicy", return_value=policy),
                patch("hengbot.cli._configure_policy_output_paths", return_value=None),
                patch("hengbot.cli._capture_decision_facts", return_value={}),
                patch("hengbot.cli._write_decision"),
                patch("hengbot.cli._record_tcp_shadow") as shadow,
                patch(
                    "hengbot.control_client.ControlClient.send_keys", return_value=1
                ) as send_keys,
            ):
                result = cli.main([
                    "--state-file", str(state), "--once", "--control-port", "1",
                ])

            self.assertEqual(result, 0)
            send_keys.assert_called_once()
            shadow.assert_not_called()

    def test_tcp_shadow_opt_in_records_after_successful_send(self):
        from hengbot import cli

        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.jsonl"
            definitions = root / "MonraceDefinitions.jsonc"
            state.write_text(_snapshot_line(1), encoding="utf-8")
            definitions.write_text("{}", encoding="utf-8")
            policy = unittest.mock.Mock()
            policy._decision_sequence = 1
            policy.last_reason = "test:once-shadow"
            policy.prompt_owner_handoff = None
            policy.choose_key.return_value = "5"
            policy.validate_read_key.return_value = "5"

            with (
                patch("hengbot.cli.find_monrace_definitions", return_value=definitions),
                patch("hengbot.cli.load_monrace_knowledge", return_value={}),
                patch("hengbot.cli.find_terrain_definitions", return_value=None),
                patch("hengbot.cli.find_outpost_map", return_value=None),
                patch("hengbot.cli.find_town_map", return_value=None),
                patch("hengbot.cli.find_wilderness_definition", return_value=None),
                patch("hengbot.cli.find_dungeon_definitions", return_value=None),
                patch("hengbot.cli.find_quest_definitions", return_value=None),
                patch("hengbot.cli.find_quest_strategies", return_value=None),
                patch("hengbot.cli._bot_play_macros_ready", return_value=False),
                patch("hengbot.cli.ConservativePolicy", return_value=policy),
                patch("hengbot.cli._configure_policy_output_paths", return_value=None),
                patch("hengbot.cli._capture_decision_facts", return_value={}),
                patch("hengbot.cli._write_decision"),
                patch("hengbot.cli._record_tcp_shadow") as shadow,
                patch("hengbot.control_client.ControlClient.send_keys", return_value=1),
            ):
                result = cli.main([
                    "--state-file", str(state), "--once", "--control-port", "1",
                    "--tcp-shadow",
                ])

            self.assertEqual(result, 0)
            shadow.assert_called_once()
            self.assertEqual(shadow.call_args.args[1]["turn"], 1)
            self.assertEqual(shadow.call_args.args[2], 1)

    def test_without_control_port_uses_wm_path_without_control_client(self):
        from hengbot import cli

        events = []
        with patch.dict("os.environ", {"HENGBOT_CONTROL_PORT": ""}, clear=False), patch(
            "hengbot.control_client.ControlClient"
        ) as control_client, patch(
            "hengbot.input_windows.send_key_to_window",
            side_effect=lambda *_a, **_k: events.append("wm"),
        ):
            self.assertEqual(
                self._run_once_with_routes(None, events, control=False), 0
            )

        control_client.assert_not_called()
        self.assertEqual(events, ["wm"])

    def test_disabled_real_follow_cycle_has_no_shadow_side_effect_or_extra_decode(self):
        from hengbot import cli

        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"HENGBOT_CONTROL_PORT": ""}, clear=False
        ):
            root = Path(directory)
            state = root / "state.jsonl"
            decisions = root / "bot-decisions.jsonl"
            shadow = root / "tcp-shadow-diff.jsonl"
            state.write_text(_snapshot_line(1), encoding="utf-8")
            parsed = cli._build_argument_parser().parse_args(["--state-file", str(state)])
            self.assertIsNone(parsed.control_port)
            parsed.decision_log = decisions
            parsed.poll_interval = 0.001
            parsed.wait_telemetry = unittest.mock.Mock()
            from hengbot.policy import HengbotPolicy
            policy = HengbotPolicy()
            def choose(snapshot):
                policy._decision_sequence += 1
                if snapshot.turn == 2:
                    policy.last_reason = "test:disabled-shadow-post-send"
                    return "5"
                policy.last_reason = "equipment-transaction:restore-blocked-terminal"
                return ""
            policy.choose_key = unittest.mock.Mock(side_effect=choose)
            original_loads = cli.json.loads
            decodes = []
            following = threading.Event()
            def append_snapshot():
                following.wait()
                with state.open("a", encoding="utf-8") as stream:
                    stream.write(_snapshot_line(2))
                    stream.flush()
                    time.sleep(0.05)
                    stream.write(_snapshot_line(3))

            writer = threading.Thread(target=append_snapshot)
            with patch.dict(sys.modules):
                sys.modules.pop("hengbot.control_client", None)
                writer.start()
                with (
                    patch(
                        "hengbot.cli._arm_decision_watchdog",
                        side_effect=following.set,
                    ),
                    patch("hengbot.cli.json.loads", side_effect=lambda value, *a, **k: (
                        decodes.append(value) or original_loads(value, *a, **k)
                    )),
                    patch(
                        "socket.create_connection",
                        side_effect=AssertionError("connected"),
                    ),
                ):
                    self.assertEqual(
                        cli._run_follow(
                            parsed, policy, lambda *_a, **_k: True, {}
                        ),
                        0,
                    )
                writer.join()
                self.assertNotIn("hengbot.control_client", sys.modules)

            self.assertEqual(decodes.count(_snapshot_line(2)), 1)
            self.assertFalse(shadow.exists())

    def test_shadow_dispatch_is_after_real_send_and_tcp_never_reaches_policy(self):
        from hengbot import cli

        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.jsonl"
            state.write_text(_snapshot_line(1), encoding="utf-8")
            events = []
            fake_client = unittest.mock.Mock()
            args = cli._build_argument_parser().parse_args([
                "--state-file", str(state),
                "--decision-log", str(root / "decisions.jsonl"),
                "--poll-interval", "0.001",
                "--tcp-shadow",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            args.shadow_client = fake_client
            from hengbot.policy import HengbotPolicy
            policy = HengbotPolicy()
            def choose(snapshot):
                policy._decision_sequence += 1
                policy.last_reason = (
                    "equipment-transaction:restore-blocked-terminal"
                    if snapshot.turn == 3 else "test:send"
                )
                return "" if snapshot.turn == 3 else "5"
            policy.choose_key = unittest.mock.Mock(side_effect=choose)

            def shadow(_client, jsonl_state, **_kwargs):
                events.append(("shadow", jsonl_state["turn"]))

            def append_snapshots():
                following.wait()
                with state.open("a", encoding="utf-8") as stream:
                    stream.write(_snapshot_line(2))
                    stream.flush()
                    time.sleep(0.05)
                    stream.write(_snapshot_line(3))

            following = threading.Event()
            writer = threading.Thread(target=append_snapshots)
            writer.start()
            try:
                with (
                    patch(
                        "hengbot.cli._arm_decision_watchdog",
                        side_effect=following.set,
                    ),
                    patch(
                        "hengbot.control_client.append_shadow_diff",
                        side_effect=shadow,
                    ),
                ):
                    self.assertEqual(cli._run_follow(
                        args, policy,
                        lambda *_a, **_k: events.append(("send", 1)) or True, {},
                    ), 0)
            finally:
                writer.join()
            self.assertEqual(events, [("send", 1), ("shadow", 2)])
            self.assertEqual(
                [call.args[0].turn for call in policy.choose_key.call_args_list],
                [2, 3],
            )
            rows = [
                json.loads(line)
                for line in args.decision_log.read_text().splitlines()
            ]
            sent_row = next(row for row in rows if row.get("reason") == "test:send")
            self.assertIn("shadow_ms", sent_row["timing"])

    def test_invalid_environment_port_is_an_argparse_error(self):
        from hengbot import cli

        with patch.dict("os.environ", {"HENGBOT_CONTROL_PORT": "not-a-port"}):
            parser = cli._build_argument_parser()
            with self.assertRaises(SystemExit) as stopped:
                parser.parse_args(["--state-file", "state.jsonl"])
        self.assertEqual(stopped.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
