"""Regression tests for the serial timing runner's filesystem isolation."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_timing_runner as runner


class TimingRunnerSelfTest(unittest.TestCase):
    def test_main_exports_single_history_root_under_run_temp(self) -> None:
        observed: list[Path] = []

        def load(names):
            observed.append(Path(os.environ["HENGBOT_HOME_HISTORY_DIR"]))
            return unittest.TestSuite()

        result = mock.Mock()
        result.timings = []
        result.wasSuccessful.return_value = True
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "serial-root"
            output = Path(directory) / "out.json"
            summary = Path(directory) / "summary.json"
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(runner.tempfile, "TemporaryDirectory", return_value=mock.MagicMock(
                    __enter__=mock.Mock(return_value=str(run_root)),
                    __exit__=mock.Mock(return_value=False),
                )),
                mock.patch.object(runner.unittest.defaultTestLoader, "loadTestsFromNames", side_effect=load),
                mock.patch.object(runner.unittest, "TextTestRunner") as text_runner,
                mock.patch.object(runner.subprocess, "check_output", return_value="deadbeef\n"),
            ):
                run_root.mkdir()
                text_runner.return_value.run.return_value = result
                status = runner.main([
                    "--modules", "tests.safe", "--output", str(output),
                    "--summary-output", str(summary), "--top", "0",
                ])
                self.assertNotIn("HENGBOT_HOME_HISTORY_DIR", os.environ)

            self.assertEqual(status, 0)
            self.assertEqual(observed, [run_root])


if __name__ == "__main__":
    unittest.main()
