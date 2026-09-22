"""Regression tests for the parallel runner's scheduling hazards."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

import test_parallel_runner as runner


class ParallelRunnerSelfTest(unittest.TestCase):
    def test_run_shard_exports_distinct_history_roots_under_run_temp(self) -> None:
        exported: list[Path] = []
        runtime: list[Path] = []

        def fake_run(command, **kwargs):
            history_dir = Path(kwargs["env"]["HENGBOT_HOME_HISTORY_DIR"])
            exported.append(history_dir)
            runtime.append(Path(kwargs["env"]["HENGBOT_RUNTIME_DIR"]))
            output = Path(command[command.index("--output") + 1])
            output.write_text(json.dumps({"tests": []}), encoding="utf-8")
            return mock.Mock(returncode=0)

        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory) / "run"
            streams = Path(directory) / "streams"
            temp_root.mkdir()
            streams.mkdir()
            with mock.patch.object(runner.subprocess, "run", side_effect=fake_run):
                rows = [runner.run_shard(index, ["tests.safe"], temp_root, streams) for index in range(2)]

            self.assertEqual(len(set(exported)), 2)
            self.assertTrue(all(path.parent.parent == temp_root for path in exported))
            self.assertTrue(all(path.name == "home-history" and path.is_dir() for path in exported))
            self.assertEqual([Path(row["home_history_dir"]) for row in rows], exported)
            self.assertEqual(len(set(runtime)), 2)
            self.assertTrue(all(path.parent.parent == temp_root for path in runtime))
            self.assertTrue(all(path.name == "runtime" and path.is_dir() for path in runtime))

    def test_unknown_module_uses_median_without_discarding_known_lpt_weights(self) -> None:
        modules = ["tests.heavy", "tests.medium", "tests.light", "tests.new"]
        weights = {"tests.heavy": 12.0, "tests.medium": 6.0, "tests.light": 2.0}

        self.assertEqual(
            runner.partition(modules, 2, weights),
            [["tests.heavy", "tests.light"], ["tests.medium", "tests.new"]],
        )

    def test_parallel_weights_cover_a_scheduled_module_with_no_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timings.json"
            path.write_text(json.dumps({
                "tests": [],
                "shards": [{"modules": ["tests.empty"]}],
            }), encoding="utf-8")
            self.assertEqual(runner.module_seconds(path), {"tests.empty": 0.0})

    def test_weight_selection_prefers_fresh_complete_and_reports_stale_fallback(self) -> None:
        modules = ["tests.one", "tests.two"]
        now = datetime.now(timezone.utc)

        def write(path: Path, generated_at: datetime, ids: list[str]) -> None:
            path.write_text(json.dumps({
                "generated_at": generated_at.isoformat(),
                "tests": [{"id": f"{module}.Case.test_x", "seconds": 1.0}
                          for module in ids],
            }), encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale, fresh = root / "stale.json", root / "fresh.json"
            write(stale, now - timedelta(days=10), ["tests.one"])
            write(fresh, now - timedelta(minutes=5), modules)
            selected = runner.select_weights([stale, fresh], modules)
            self.assertIsNotNone(selected)
            self.assertEqual(selected.path, fresh)
            self.assertIn("fallback=0/2; stale=no", runner.weights_summary(selected, 2, now))

            selected = runner.select_weights([stale], modules)
            self.assertIsNotNone(selected)
            summary = runner.weights_summary(selected, 2, now)
            self.assertIn("fallback=1/2", summary)
            self.assertIn("stale=yes", summary)

    def test_fixed_path_writers_are_the_exact_serial_tail(self) -> None:
        self.assertEqual(
            runner.SERIAL_MODULES,
            {
                "tests.test_absorbing_states",
                "tests.test_cli",
                "tests.test_latch_onset_capture",
                "tests.test_policy_structure",
            },
        )

    def test_standing_identity_contains_cli(self) -> None:
        self.assertIn("tests.test_cli", runner.standard_modules())

    def test_serial_modules_are_one_mutually_serial_concurrent_shard(self) -> None:
        writer = "tests.test_policy"
        modules = [writer, "tests.safe", *sorted(runner.SERIAL_MODULES)]
        calls: list[tuple[str, tuple[str, ...]]] = []
        calls_lock = threading.Lock()
        serial_calls = 0
        serial_started = threading.Event()

        def fake_run_shard(index: int, shard: list[str], temp_root: Path, streams: Path):
            nonlocal serial_calls
            is_serial = set(shard) == runner.SERIAL_MODULES
            with calls_lock:
                if is_serial:
                    serial_calls += 1
                    self.assertEqual(tuple(shard), tuple(sorted(runner.SERIAL_MODULES)))
                    calls.append(("serial", tuple(shard)))
                    serial_started.set()
                else:
                    self.assertTrue(runner.SERIAL_MODULES.isdisjoint(shard))
                    calls.append(("parallel", tuple(shard)))
            if not is_serial:
                self.assertTrue(serial_started.wait(2), "serial shard did not overlap the pool")
            return {
                "name": f"worker-{index + 1}", "modules": shard, "returncode": 0,
                "home_history_dir": str(temp_root / f"worker-{index + 1}" / "home-history"),
                "wall_seconds": 0.0, "payload": {"tests": []}, "failures": [],
                "errors": [], "stdout": str(streams / "stdout"),
                "stderr": str(streams / "stderr"),
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(runner, "standard_modules", return_value=modules),
                mock.patch.object(runner, "select_weights", return_value=None, create=True),
                mock.patch.object(runner, "run_shard", side_effect=fake_run_shard),
                mock.patch.object(runner.subprocess, "check_output", return_value="deadbeef\n"),
            ):
                result = runner.main([
                    "--workers", "2", "--output", str(root / "out.json"),
                    "--summary-output", str(root / "summary.json"),
                    "--streams-dir", str(root / "streams"),
                ])

            self.assertEqual(result, 0)
            self.assertEqual(serial_calls, 1)
            self.assertEqual(
                json.loads((root / "out.json").read_text(encoding="utf-8"))["serial_modules"],
                sorted(runner.SERIAL_MODULES),
            )
            pool_modules = {module for kind, shard in calls if kind == "parallel" for module in shard}
            self.assertEqual(pool_modules, {writer, "tests.safe"})


if __name__ == "__main__":
    unittest.main()
