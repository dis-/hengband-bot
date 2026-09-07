"""Regression tests for the parallel runner's scheduling hazards."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import test_parallel_runner as runner


class ParallelRunnerSelfTest(unittest.TestCase):
    def test_run_shard_exports_distinct_history_roots_under_run_temp(self) -> None:
        exported: list[Path] = []

        def fake_run(command, **kwargs):
            history_dir = Path(kwargs["env"]["HENGBOT_HOME_HISTORY_DIR"])
            exported.append(history_dir)
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

    def test_unknown_module_uses_median_without_discarding_known_lpt_weights(self) -> None:
        modules = ["tests.heavy", "tests.medium", "tests.light", "tests.new"]
        weights = {"tests.heavy": 12.0, "tests.medium": 6.0, "tests.light": 2.0}

        self.assertEqual(
            runner.partition(modules, 2, weights),
            [["tests.heavy", "tests.light"], ["tests.medium", "tests.new"]],
        )

    def test_fixed_path_writers_are_the_exact_serial_tail(self) -> None:
        self.assertEqual(
            runner.SERIAL_MODULES,
            {
                "tests.test_absorbing_states",
                "tests.test_latch_onset_capture",
                "tests.test_policy_structure",
            },
        )

    def test_serial_modules_are_excluded_from_pool_and_run_after_it(self) -> None:
        writer = "tests.test_policy"
        modules = [writer, "tests.safe", *sorted(runner.SERIAL_MODULES)]
        calls: list[tuple[str, tuple[str, ...]]] = []
        calls_lock = threading.Lock()
        parallel_active = 0

        def fake_run_shard(index: int, shard: list[str], temp_root: Path, streams: Path):
            nonlocal parallel_active
            is_serial = set(shard) == runner.SERIAL_MODULES
            with calls_lock:
                if is_serial:
                    self.assertEqual(parallel_active, 0)
                    calls.append(("serial", tuple(shard)))
                else:
                    self.assertTrue(runner.SERIAL_MODULES.isdisjoint(shard))
                    parallel_active += 1
                    calls.append(("parallel", tuple(shard)))
            if not is_serial:
                with calls_lock:
                    parallel_active -= 1
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
                mock.patch.object(runner, "module_seconds", return_value={name: 1.0 for name in modules}),
                mock.patch.object(runner, "run_shard", side_effect=fake_run_shard),
                mock.patch.object(runner.subprocess, "check_output", return_value="deadbeef\n"),
            ):
                result = runner.main([
                    "--workers", "2", "--output", str(root / "out.json"),
                    "--summary-output", str(root / "summary.json"),
                    "--streams-dir", str(root / "streams"),
                ])

            self.assertEqual(result, 0)
            self.assertEqual(calls[-1], ("serial", tuple(sorted(runner.SERIAL_MODULES))))
            self.assertEqual(
                json.loads((root / "out.json").read_text(encoding="utf-8"))["serial_modules"],
                sorted(runner.SERIAL_MODULES),
            )
            pool_modules = {module for kind, shard in calls if kind == "parallel" for module in shard}
            self.assertEqual(pool_modules, {writer, "tests.safe"})


if __name__ == "__main__":
    unittest.main()
