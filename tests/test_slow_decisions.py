"""Deterministic slow-decision recorder pins; no wall-clock assertions."""
import tests  # noqa: F401
import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hengbot import cli
from hengbot.slow_decisions import (
    SlowDecisionRecorder, _Samples, _main_stack, MAX_DEPTH, MAX_FUNCTIONS, MAX_STACKS,
)
from tests.test_action_pacing import Clock, ScriptPolicy, board, ExchangeDone, RefuseOnce
from tests.run_follow_hygiene import run_follow

STACK = (("leaf", "worker.py", 10, 14), ("parent", "policy.py", 20, 25))


class ManualSamples(_Samples):
    """Production aggregation with deterministic ticks instead of a worker."""
    def __init__(self, thread_id, *, clock):
        super().__init__(thread_id, clock=clock, stack_reader=lambda _: STACK)

    def start(self):
        self.tick()
        self.tick()

    def finish(self):
        return True


class SlowDecisionTest(unittest.TestCase):
    def exchange(self, root, elapsed=2.0, limit=1.0, **kwargs):
        clock = Clock()
        policy = ScriptPolicy(clock, elapsed)
        policy._decision_sequence = 47
        recorder = SlowDecisionRecorder(
            limit, root / "decisions.jsonl", clock=clock.read,
            sampler_factory=ManualSamples, **kwargs,
        )
        key = recorder.choose_key(policy, object())
        path = root / "slow-decisions.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        return key, policy.last_reason, rows

    def test_over_limit_writes_one_aggregate(self):
        with TemporaryDirectory() as directory:
            key, reason, rows = self.exchange(Path(directory))
        self.assertEqual((key, reason), ("R1\r", "rest"))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["decision_sequence"], row["reason"], row["choose_key_ms"]),
                         (47, "rest", 2000.0))
        data = row["aggregate"]
        self.assertEqual(data["sample_count"], 2)
        self.assertEqual(data["interval_ms"], 10)
        self.assertEqual(data["max_depth"], MAX_DEPTH)
        self.assertEqual(data["sampling_work_ms"], 0)
        self.assertEqual(data["functions"], [
            dict(function="leaf", file="worker.py", line=10, self_samples=2, cumulative_samples=2),
            dict(function="parent", file="policy.py", line=20, self_samples=0, cumulative_samples=2),
        ])
        self.assertEqual(data["stacks"], [dict(samples=2, frames=[
            dict(function="leaf", file="worker.py", line=14),
            dict(function="parent", file="policy.py", line=25),
        ])])

    def test_under_and_equal_limit_discard(self):
        for elapsed in (0.25, 1.0):
            with self.subTest(elapsed=elapsed), TemporaryDirectory() as directory:
                self.assertEqual(self.exchange(Path(directory), elapsed=elapsed)[2], [])
                self.assertFalse((Path(directory) / "slow-decisions.jsonl").exists())

    def test_off_starts_no_thread(self):
        args = cli._build_argument_parser().parse_args(["--state-file", "unused"])
        self.assertEqual(args.slow_decision_sample, 0.0)
        with TemporaryDirectory() as directory, patch("hengbot.slow_decisions.threading.Thread") as thread:
            key, reason, rows = self.exchange(Path(directory), limit=0)
            thread.assert_not_called()
        self.assertEqual((key, reason, rows), ("R1\r", "rest", []))

    def test_absent_log_starts_no_thread(self):
        policy = SimpleNamespace(choose_key=Mock(return_value="5"))
        with patch("hengbot.slow_decisions.threading.Thread") as thread:
            self.assertEqual(SlowDecisionRecorder(1).choose_key(policy, None), "5")
            thread.assert_not_called()

    def test_follow_keys_and_reasons_identical_including_retry(self):
        def exchange(limit):
            clock = Clock()
            policy = ScriptPolicy(clock, 2)
            posts = []
            with TemporaryDirectory() as directory:
                root = Path(directory)
                state = root / "state.jsonl"
                state.write_text(board(1), encoding="utf-8")
                args = cli._build_argument_parser().parse_args([
                    "--state-file", str(state), "--decision-log", str(root / "decisions.jsonl"),
                    "--slow-decision-sample", str(limit),
                    "--game-save-path", str(root / "absent"), "--dump-interval-seconds", "0",
                ])
                args.wait_telemetry = Mock()

                appended = False

                def poll():
                    nonlocal appended
                    if posts:
                        raise ExchangeDone
                    if not appended:
                        with state.open("a", encoding="utf-8") as stream:
                            stream.write(board(2))
                        appended = True

                def send(key, **kwargs):
                    posts.append((key, kwargs["decision"]["reason"]))
                    return True

                with (patch("hengbot.cli.time", clock.module()),
                      patch("hengbot.slow_decisions.time", clock.module()),
                      patch("hengbot.slow_decisions._Samples", ManualSamples),
                      patch("hengbot.cli._arm_decision_watchdog", side_effect=poll)):
                    with self.assertRaises(ExchangeDone):
                        run_follow(args, policy, send, {}, posting_contract=RefuseOnce())
                rows = [json.loads(line) for line in args.decision_log.read_text(encoding="utf-8").splitlines()]
                sample_path = root / "slow-decisions.jsonl"
                samples = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines()] if sample_path.exists() else []
            return posts, [(r["key"], r["reason"]) for r in rows], samples, policy.calls
        plain = exchange(0)
        sampled = exchange(1)
        self.assertEqual(plain[:2], sampled[:2])
        self.assertEqual(sampled[0], [("R1\r", "rest")])
        self.assertEqual((plain[3], sampled[3]), (2, 2))
        self.assertEqual(len(plain[2]), 0)
        self.assertEqual(len(sampled[2]), 2)
        self.assertEqual([r["reason"] for r in sampled[2]], ["rest", "rest"])

    def test_once_also_samples_without_actuation(self):
        clock = Clock()
        policy = ScriptPolicy(clock, 2)
        with TemporaryDirectory() as directory, ExitStack() as patches:
            root = Path(directory)
            state = root / "state.jsonl"
            state.write_text(board(1), encoding="utf-8")
            patches.enter_context(patch("hengbot.cli.ConservativePolicy", return_value=policy))
            patches.enter_context(patch("hengbot.cli.find_monrace_definitions", return_value=root / "absent"))
            patches.enter_context(patch("hengbot.cli.load_monrace_knowledge", return_value={}))
            for name in ("find_terrain_definitions", "find_outpost_map", "find_town_map",
                         "find_wilderness_definition", "find_dungeon_definitions",
                         "find_quest_definitions", "find_quest_strategies"):
                patches.enter_context(patch("hengbot.cli." + name, return_value=None))
            patches.enter_context(patch("hengbot.cli._bot_play_macros_ready", return_value=False))
            patches.enter_context(patch("hengbot.slow_decisions.time", clock.module()))
            patches.enter_context(patch("hengbot.slow_decisions._Samples", ManualSamples))
            self.assertEqual(cli.main([
                "--once", "--state-file", str(state),
                "--decision-log", str(root / "decisions.jsonl"),
                "--slow-decision-sample", "1",
            ]), 0)
            row = json.loads((root / "slow-decisions.jsonl").read_text(encoding="utf-8"))
            self.assertEqual((row["reason"], row["choose_key_ms"]), ("rest", 2000.0))

    def test_recorded_follow_keeps_keys_and_reasons(self):
        from tests import test_action_pacing as pacing
        plain = pacing.ActionPacingTest().exchange(recorded=True)
        with patch("hengbot.cli.SlowDecisionRecorder", side_effect=lambda _, path:
                   SlowDecisionRecorder(0.001, path, sampler_factory=ManualSamples)) as factory:
            sampled = pacing.ActionPacingTest().exchange(recorded=True)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(plain[1], sampled[1])
        self.assertEqual([(r["key"], r["reason"]) for r in plain[2]],
                         [(r["key"], r["reason"]) for r in sampled[2]])

    def test_sampler_uses_main_thread_frames_and_depth_limit(self):
        import threading
        stack = _main_stack(threading.get_ident())
        self.assertEqual(stack[0][0], "_main_stack")
        self.assertTrue(any(f[0] == "test_sampler_uses_main_thread_frames_and_depth_limit" for f in stack))
        def recurse(n):
            return recurse(n - 1) if n else _main_stack(threading.get_ident())
        self.assertEqual(len(recurse(MAX_DEPTH + 5)), MAX_DEPTH)
        self.assertTrue(all(isinstance(f[3], int) for f in stack))

    def test_worker_waits_10ms_and_is_daemon(self):
        samples = _Samples(47, clock=lambda: 0, stack_reader=lambda _: STACK)
        self.assertTrue(samples.thread.daemon)
        samples.stop = Mock()
        samples.stop.wait.side_effect = [False, False, True]
        samples._run()
        self.assertEqual(samples.count, 2)
        self.assertEqual(samples.stop.wait.call_args_list, [((0.01,),)] * 3)
        samples.thread = Mock()
        samples.thread.is_alive.return_value = False
        self.assertTrue(samples.finish())
        samples.stop.set.assert_called_once()
        samples.thread.join.assert_called_once_with(timeout=0.05)

    def test_aggregate_and_memory_are_bounded(self):
        samples = _Samples(47, clock=lambda: 0)
        for index in range(MAX_FUNCTIONS + MAX_STACKS):
            samples.stack_reader = lambda _, i=index: ((str(i), "many.py", i, i),) * 2
            samples.tick()
        result = samples.aggregate()
        self.assertEqual(len(samples.functions), MAX_FUNCTIONS)
        self.assertEqual(len(samples.stacks), MAX_STACKS)
        self.assertEqual(len(result["functions"]), 40)
        self.assertEqual(len(result["stacks"]), 5)
        self.assertEqual(result["dropped_stacks"], MAX_FUNCTIONS)
        self.assertTrue(result["function_limit_reached"])
        self.assertTrue(all(f["self_samples"] == f["cumulative_samples"] == 1 for f in result["functions"]))

    def test_rotation_bounds_both_files_and_keeps_complete_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for _ in range(5):
                self.exchange(root, max_bytes=1000)
            path = root / "slow-decisions.jsonl"
            backup = root / "slow-decisions.jsonl.1"
            self.assertTrue(backup.exists())
            for file in (path, backup):
                self.assertLessEqual(file.stat().st_size, 1000)
                self.assertEqual(len(file.read_text(encoding="utf-8").splitlines()), 1)
                self.assertEqual(json.loads(file.read_text(encoding="utf-8"))["reason"], "rest")

    def test_diagnostic_failures_preserve_key_and_policy_exception(self):
        for target in ("start", "finish", "aggregate"):
            with self.subTest(target=target), TemporaryDirectory() as directory:
                with patch.object(ManualSamples, target, side_effect=RuntimeError("diagnostic")):
                    self.assertEqual(self.exchange(Path(directory))[:2], ("R1\r", "rest"))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(SlowDecisionRecorder, "_append", side_effect=OSError("full")):
                self.assertEqual(self.exchange(root)[:2], ("R1\r", "rest"))
            samples = Mock()
            policy = SimpleNamespace(choose_key=Mock(side_effect=ValueError("policy")))
            recorder = SlowDecisionRecorder(1, root / "decisions.jsonl", sampler_factory=Mock(return_value=samples))
            with self.assertRaisesRegex(ValueError, "policy"):
                recorder.choose_key(policy, None)
            samples.finish.assert_called_once()
        samples = _Samples(47, clock=lambda: 0, stack_reader=Mock(side_effect=RuntimeError("sample")))
        samples.stop.wait = Mock(return_value=False)
        samples._run()  # worker failure remains local


if __name__ == "__main__":
    unittest.main()
