"""Constructed short exchanges through the real follow loop; all time is injected."""
import tests  # noqa: F401

import copy
import gzip
import io
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hengbot import cli
from hengbot.spectator import SpectatorWriter, printable_key
from tests.run_follow_hygiene import run_follow
from tests.test_action_pacing import Clock, ExchangeDone, ScriptPolicy, board, RefuseOnce
from tests import test_spectator as spectator_pins
from tests import test_input_executor as executor_pins
from hengbot.control_client import ControlClient
from hengbot.policy import HengbotPolicy
from hengbot.monrace_knowledge import load_monrace_knowledge


class FramesFollowTest(unittest.TestCase):
    def exchange(self, maximum=0, played="fresh", spectate=True, minimum=0,
                 refuse=False, recorded=False):
        clock = Clock()
        knowledge = (load_monrace_knowledge(
            Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")) if recorded else {})
        policy = (HengbotPolicy(monrace_knowledge=knowledge)
                  if recorded else ScriptPolicy(clock, 0.05))
        if recorded:
            fixture = Path(__file__).parent / "fixtures" / "esp-threat-rest-20260921.jsonl.gz"
            with gzip.open(fixture, "rt", encoding="utf-8") as stream:
                lines = [line for line in stream
                         if json.loads(line).get("type") == "player_turn"
                         and json.loads(line).get("floor", {}).get("level", 0) > 0][2:5]
        else:
            lines = [board(turn) for turn in range(4)]
        posts, watchdogs, frames_at_post, deadlines, cancellations = [], [], [], [], []
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.jsonl"
            state.write_text(lines[0], encoding="utf-8")
            argv = ["--state-file", str(state), "--decision-log", str(root / "decisions.jsonl"),
                    "--game-save-path", str(root / "absent"), "--dump-interval-seconds", "0",
                    "--spectate-max-backlog", str(maximum),
                    "--min-action-seconds", str(minimum)]
            if spectate:
                argv += ["--spectate-file", str(root / "spectate.json")]
            args = cli._build_argument_parser().parse_args(argv)
            args.wait_telemetry = Mock()
            writer = SpectatorWriter(root / "spectate.json", clock=clock.read)
            played_reads = []
            original_read = Path.read_text

            def read(path, *a, **kw):
                if path == writer.played_path:
                    played_reads.append(clock.now)
                return original_read(path, *a, **kw)

            def acknowledge(frame=0):
                if played == "missing":
                    return
                content = ("{" if played == "invalid" else json.dumps({
                    "frame": frame, "time": clock.now - (11 if played == "stale" else 0)}))
                writer.played_path.write_text(content, encoding="utf-8")

            acknowledge()
            appended = 0

            def poll():
                nonlocal appended
                watchdogs.append(clock.now)
                if len(posts) == len(lines) - 1:
                    raise ExchangeDone
                if appended <= len(posts):
                    with state.open("a", encoding="utf-8") as stream:
                        stream.write(lines[appended + 1])
                    appended += 1
                    if recorded:
                        clock.now += 0.05

            original_sleep = clock.sleep

            def sleep(seconds):
                if len(clock.sleeps) >= 12:
                    raise AssertionError("unexpected spectator wait did not terminate")
                original_sleep(seconds)
                # Server catches up after two short polls, or expires mid-wait.
                if played == "expire":
                    clock.now += 11
                elif len(clock.sleeps) % 2 == 0:
                    acknowledge(writer.last_frame)

            clock_module = clock.module()
            clock_module.sleep = sleep

            def send(key, **kwargs):
                frames_at_post.append(writer.last_frame)
                posts.append((key, kwargs["decision"]["reason"], clock.now))
                # No response budget is consumed by spectator waiting.
                return True

            original_init = SpectatorWriter.__init__

            def initialise(instance, path):
                nonlocal writer
                original_init(instance, path, clock=clock.read)
                writer = instance

            original_chain = cli._send_decision_key_with_prompt_chain

            def chain(*a, **kw):
                deadlines.append(kw["deadline"] - clock.now)
                return original_chain(*a, **kw)

            original_cancel = cli.faulthandler.cancel_dump_traceback_later

            def cancel():
                cancellations.append(clock.now)
                return original_cancel()

            with (patch("hengbot.cli.time", clock_module),
                  patch("hengbot.cli._arm_decision_watchdog", side_effect=poll),
                  patch.object(SpectatorWriter, "__init__", initialise),
                  patch.object(Path, "read_text", read),
                  patch("hengbot.cli._send_decision_key_with_prompt_chain", side_effect=chain),
                  patch("hengbot.cli.faulthandler.cancel_dump_traceback_later", side_effect=cancel)):
                with self.assertRaises(ExchangeDone):
                    run_follow(args, policy, send, knowledge,
                               posting_contract=RefuseOnce() if refuse else None)
            frames = ([json.loads(row) for row in writer.frames_path.read_text(
                encoding="utf-8").splitlines()] if writer.frames_path.exists() else [])
            rows = [json.loads(row) for row in args.decision_log.read_text(
                encoding="utf-8").splitlines()]
            snapshot = (json.loads(writer.path.read_text(encoding="utf-8"))
                        if writer.path.exists() else None)
        return SimpleNamespace(clock=clock, posts=posts, frames=frames, rows=rows,
                               snapshot=snapshot, reads=played_reads,
                               watchdogs=watchdogs, deadlines=deadlines, cancellations=cancellations,
                               frames_at_post=frames_at_post)

    def test_every_post_appends_in_order_without_snapshot_throttle(self):
        run = self.exchange()
        self.assertEqual([row["frame"] for row in run.frames], [1, 2, 3])
        self.assertEqual([row["decision_sequence"] for row in run.frames],
                         [row["decision_sequence"] for row in run.rows])
        self.assertEqual([row["key"] for row in run.frames],
                         [printable_key(key) for key, _, _ in run.posts])
        self.assertEqual([row["reason"] for row in run.frames], ["rest"] * 3)
        self.assertEqual(run.snapshot["time"], run.frames[0]["time"])
        self.assertLess(run.frames[-1]["time"] - run.frames[0]["time"], 0.25)

    def test_backlog_at_limit_waits_for_played_advance_outside_timing(self):
        run = self.exchange(1)
        self.assertEqual(run.clock.sleeps, [0.05] * 4)
        self.assertEqual(run.frames_at_post, [0, 1, 2])
        self.assertEqual(run.deadlines, [1.5] * 3)
        # The loop also cancels at ordinary boundaries; verify both wait entries.
        for start in (100.1, 100.25):
            self.assertTrue(any(abs(at - start) < 1e-8 for at in run.cancellations))
        self.assertAlmostEqual(run.posts[1][2] - run.posts[0][2], 0.15)
        self.assertEqual([row["timing"]["choose_key_ms"] for row in run.rows], [50.0] * 3)
        self.assertEqual([row["timing"]["send_ms"] for row in run.rows], [0.0] * 3)
        self.assertEqual([row["timing"]["total_ms"] for row in run.rows], [50.0] * 3)
        self.assertEqual(len(run.watchdogs), 6)  # regular arms plus the two re-arms

    def test_backlog_below_limit_does_not_wait(self):
        self.assertEqual(self.exchange(20).clock.sleeps, [])

    def test_stale_missing_and_invalid_ack_do_not_wait(self):
        for mode in ("stale", "missing", "invalid"):
            with self.subTest(mode=mode):
                run = self.exchange(1, mode)
                self.assertTrue(run.reads)
                self.assertEqual(run.clock.sleeps, [])
                self.assertEqual(len(run.posts), 3)

    def test_server_stopping_during_wait_releases_bot(self):
        run = self.exchange(1, "expire")
        self.assertEqual(run.clock.sleeps, [0.05])
        self.assertEqual(len(run.posts), 3)
        self.assertEqual([row["timing"]["total_ms"] for row in run.rows], [50.0] * 3)

    def test_default_zero_never_reads_played_file(self):
        args = cli._build_argument_parser().parse_args(["--state-file", "unused"])
        self.assertEqual(args.spectate_max_backlog, 0)
        run = self.exchange()
        self.assertEqual(run.reads, [])
        self.assertEqual(run.clock.sleeps, [])

    def test_keys_and_reasons_with_both_features_and_pacing(self):
        off = self.exchange(spectate=False)
        on = self.exchange(1)
        paced = self.exchange(1, minimum=0.25)
        self.assertEqual([(k, r) for k, r, _ in off.posts],
                         [(k, r) for k, r, _ in paced.posts])
        self.assertTrue(paced.clock.sleeps)
        self.assertEqual([(k, r) for k, r, _ in off.posts],
                         [(k, r) for k, r, _ in on.posts])
        self.assertEqual([(r["key"], r["reason"]) for r in off.rows],
                         [(r["key"], r["reason"]) for r in on.rows])
        self.assertTrue(on.clock.sleeps)
        self.assertEqual([row["timing"]["total_ms"] for row in on.rows], [50.0] * 3)
        self.assertEqual(off.frames, [])

    def test_recorded_policy_keys_reasons_and_compatibility_snapshot_with_waits(self):
        plain = self.exchange(spectate=False, recorded=True)
        frames = self.exchange(recorded=True)
        paced_frames = self.exchange(minimum=0.25, recorded=True)
        for spectate, maximum, minimum in ((False, 0, 0.25), (True, 1, 0),
                                           (True, 1, 0.25)):
            with self.subTest(spectate=spectate, maximum=maximum, minimum=minimum):
                run = self.exchange(spectate=spectate, maximum=maximum,
                                    minimum=minimum, recorded=True)
                self.assertEqual([(k, r) for k, r, _ in plain.posts],
                                 [(k, r) for k, r, _ in run.posts])
                self.assertEqual([(r["key"], r["reason"]) for r in plain.rows],
                                 [(r["key"], r["reason"]) for r in run.rows])
                self.assertTrue(run.clock.sleeps)
                if spectate:
                    self.assertEqual([(r["key"], r["reason"]) for r in run.frames],
                                     [(printable_key(k), r) for k, r, _ in run.posts])
        self.assertEqual([(k, r) for k, r, _ in frames.posts],
                         [(k, r) for k, r, _ in paced_frames.posts])
        self.assertEqual([(r["key"], r["reason"]) for r in frames.rows],
                         [(r["key"], r["reason"]) for r in paced_frames.rows])
        self.assertEqual((frames.snapshot["key"], frames.snapshot["reason"]),
                         (paced_frames.snapshot["key"], paced_frames.snapshot["reason"]))
        self.assertEqual(len(frames.frames), 2)
        self.assertTrue(paced_frames.clock.sleeps)

    def test_refused_post_has_no_frame_and_retry_is_backpressured(self):
        run = self.exchange(1, refuse=True)
        self.assertEqual(len(run.frames), len(run.posts))
        self.assertEqual([row["frame"] for row in run.frames], [1, 2, 3])
        self.assertEqual(run.clock.sleeps, [0.05] * 4)


class FramesColourFollowTest(executor_pins.ProductionHarness):
    def recorded_exchange(self, root, *, spectate, death=False):
        recorded = [json.loads(line) for line in spectator_pins._recorded_lines()]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(recorded[0])
        game.screen = executor_pins.command_screen(recorded[0]["turn"])
        game.states = copy.deepcopy(recorded[1:])
        if death:
            game.screens = [executor_pins.prompt_screen("You die.")]
        game.jsonl.append(copy.deepcopy(recorded[0]))
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = cli._ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        state = root / "state.jsonl"
        state.write_text("", encoding="utf-8")
        argv = ["--state-file", str(state), "--decision-log", str(root / "decisions.jsonl"),
                "--poll-interval", "0.001", "--stall-timeout", "0.5",
                "--spectate-max-backlog", "1"]
        if spectate:
            argv += ["--spectate-file", str(root / "spectate.json")]
        args = cli._build_argument_parser().parse_args(argv)
        args.wait_telemetry = Mock()
        policy = spectator_pins._fresh_policy(root)
        original_choose = policy.choose_key

        def choose(snapshot):
            if not game.states:
                policy._decision_sequence += 1
                policy.last_reason = spectator_pins.TERMINAL_REASON
                return ""
            return original_choose(snapshot)

        policy.choose_key = choose
        clock = Clock()
        writer = None
        original_init = SpectatorWriter.__init__

        def initialise(instance, path):
            nonlocal writer
            original_init(instance, path, clock=clock.read)
            writer = instance
            acknowledge()

        def acknowledge():
            if writer is not None:
                writer.played_path.write_text(json.dumps({
                    "frame": writer.last_frame, "time": clock.now}), encoding="utf-8")

        original_sleep = clock.sleep

        def sleep(seconds):
            original_sleep(seconds)
            acknowledge()

        clock_module = clock.module()
        clock_module.sleep = sleep
        with (patch("hengbot.cli.time", clock_module),
              patch("hengbot.input_executor.time", clock_module),
              patch("hengbot.control_client.time", clock_module),
              patch.object(SpectatorWriter, "__init__", initialise)):
            result = run_follow(args, policy, port, {})
        rows = [json.loads(line) for line in args.decision_log.read_text(encoding="utf-8").splitlines()]
        frames = ([json.loads(line) for line in writer.frames_path.read_text(
            encoding="utf-8").splitlines()] if writer is not None else [])
        return result, game.accepted, rows, frames

    def test_each_actual_post_requests_colours_through_executor(self):
        original = ControlClient.request
        calls = []

        def request(client, op, **fields):
            if op == "screen" and fields.get("attrs") is True:
                calls.append(fields)
            return original(client, op, **fields)

        with TemporaryDirectory() as off_dir, TemporaryDirectory() as on_dir:
            off = self.recorded_exchange(Path(off_dir), spectate=False)
            with patch.object(ControlClient, "request", request):
                on = self.recorded_exchange(Path(on_dir), spectate=True)
            _, keys, rows, frames = on
            self.assertEqual(off[:2], on[:2])
            self.assertEqual(spectator_pins.SpectatorFollowReplayTest._decided(off[2]),
                             spectator_pins.SpectatorFollowReplayTest._decided(rows))
            self.assertEqual(len(frames), len(keys))
            self.assertEqual(len(calls), len(keys))
            self.assertEqual([row["frame"] for row in frames], list(range(1, len(keys) + 1)))
            self.assertTrue(all("screen" in row for row in frames))

    def test_post_that_ends_in_death_still_has_frame(self):
        with TemporaryDirectory() as directory:
            result, keys, _, frames = self.recorded_exchange(
                Path(directory), spectate=True, death=True)
        self.assertEqual(result, 0)
        self.assertEqual(len(keys), 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["frame"], 1)
        self.assertEqual(frames[0]["key"], printable_key(keys[0]))


class FramesWriterTest(unittest.TestCase):
    def test_colours_every_frame_and_snapshot_stays_throttled(self):
        with TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json", clock=lambda: 100.0)
            client = Mock()
            snapshot = spectator_pins.SpectatorWriterTest._snapshot()
            for number in (1, 2, 3):
                client.request.return_value = {"lines": [str(number)], "attrs": ["0e"]}
                writer.observe(snapshot, str(number), "test", number, None,
                               screen_client=client, append_frame=True)
            rows = [json.loads(line) for line in writer.frames_path.read_text(
                encoding="utf-8").splitlines()]
            self.assertEqual(client.request.call_count, 3)
            self.assertEqual([row["screen"]["lines"] for row in rows], [["1"], ["2"], ["3"]])
            self.assertEqual(json.loads(writer.path.read_text(encoding="utf-8"))["key"], "1")

    def test_rotation_keeps_complete_newest_rows_and_restart_number(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path)
            snapshot = spectator_pins.SpectatorWriterTest._snapshot()
            with patch("hengbot.spectator.SPECTATE_FRAMES_MAX_BYTES", 2048):
                for number in range(30):
                    writer.observe(snapshot, "6", "test", number,
                                   {"lines": ["\u65e5\u672c\u8a9e" * 25]}, append_frame=True)
                self.assertLessEqual(writer.frames_path.stat().st_size, 2048)
                rows = [json.loads(line) for line in writer.frames_path.read_text(
                    encoding="utf-8").splitlines()]
                self.assertGreater(rows[0]["frame"], 1)
                self.assertEqual(rows[-1]["frame"], 30)
                restarted = SpectatorWriter(path)
                restarted.observe(snapshot, "6", "restart", 31, None, append_frame=True)
                self.assertEqual(restarted.last_frame, 31)
                self.assertEqual(json.loads(restarted.frames_path.read_text(
                    encoding="utf-8").splitlines()[-1])["frame"], 31)

    def test_torn_tail_is_repaired_before_next_append(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path)
            snapshot = spectator_pins.SpectatorWriterTest._snapshot()
            writer.observe(snapshot, "6", "first", 1, None, append_frame=True)
            with writer.frames_path.open("ab") as stream:
                stream.write(b'{"frame": 2')
            writer = SpectatorWriter(path)
            writer.observe(snapshot, "6", "second", 2, None, append_frame=True)
            rows = [json.loads(line) for line in writer.frames_path.read_text(
                encoding="utf-8").splitlines()]
            self.assertEqual([row["frame"] for row in rows], [1, 2])

    def test_failed_rotation_does_not_allow_file_to_grow(self):
        with TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json", stderr=io.StringIO())
            snapshot = spectator_pins.SpectatorWriterTest._snapshot()
            writer.observe(snapshot, "6", "first", 1, None, append_frame=True)
            before = writer.frames_path.read_bytes()
            with (patch("hengbot.spectator.SPECTATE_FRAMES_MAX_BYTES", len(before) + 10),
                  patch("hengbot.spectator.os.replace", side_effect=OSError("reader holds file"))):
                for _ in range(3):
                    writer.observe(snapshot, "6", "next", 2, None, append_frame=True)
                self.assertEqual(writer.frames_path.read_bytes(), before)
                self.assertEqual(writer.last_frame, 1)

    def test_bad_ack_values_fail_open(self):
        with TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json", clock=lambda: 100.0)
            writer.last_frame = 10
            for value in ({}, [], {"frame": True, "time": 100},
                          {"frame": -1, "time": 100}, {"frame": 11, "time": 100},
                          {"frame": 0, "time": float("nan")},
                          {"frame": 0, "time": 101}, {"frame": 0, "time": "100"}):
                writer.played_path.write_text(json.dumps(value), encoding="utf-8")
                self.assertFalse(writer.backlog_full(1), value)
            writer.played_path.write_text('{"frame": 0, "time": 90}', encoding="utf-8")
            self.assertTrue(writer.backlog_full(1))  # exactly ten seconds is still fresh

    def test_broken_output_never_raises_and_other_output_survives(self):
        snapshot = spectator_pins.SpectatorWriterTest._snapshot()
        with TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json", stderr=io.StringIO())
            writer.path.mkdir()  # cannot atomically replace a directory
            writer.observe(snapshot, "6", "test", 1, None, append_frame=True)
            self.assertEqual(writer.last_frame, 1)
            writer.path.rmdir()
            writer.frames_path.unlink()
            writer.frames_path.mkdir()
            writer.last_write = None
            self.assertTrue(writer.observe(snapshot, "6", "test", 2, None, append_frame=True))
            self.assertEqual(json.loads(writer.path.read_text(encoding="utf-8"))["decision_sequence"], 2)
            client = Mock()
            client.request.side_effect = OSError("offline")
            writer.observe(snapshot, "6", "test", 3, {"lines": ["fallback"]},
                           screen_client=client, append_frame=True)


if __name__ == "__main__":
    unittest.main()
