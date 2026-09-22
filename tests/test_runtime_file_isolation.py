"""Tests never write the live bot's runtime files (jsonlog/, Home history).

The live bot runs from this checkout while suites run.  Restored live
checkpoints carry the bot's own file locations, and the CLI defaults to
jsonlog/; both are routed through HENGBOT_RUNTIME_DIR / HENGBOT_HOME_HISTORY_DIR,
which tests/__init__.py always sets to temporary directories.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path, PurePath
import pickle
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

import tests as session
from hengbot.cli import _configure_policy_output_paths
from hengbot.exploration_ledger import EXPLORATION_LEDGER_PATH, ExplorationLedger
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV, HomeDisposalState
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.runtime_paths import (
    POLICY_RUNTIME_PATH_ATTRIBUTES,
    RUNTIME_DIR_ENV,
    isolate_restored_runtime_paths,
    runtime_dir,
    runtime_path,
)
from hengbot.save_archive import (
    ARCHIVE_REPOSITORY_PATH,
    SaveArchiveCoordinator,
    archive_repository_path,
)
from trajectory_harness import checkpoint_row
import test_policy_town


REPOSITORY = Path(__file__).resolve().parents[1]
LIVE_RUNTIME = REPOSITORY / "jsonlog"
FIXTURES = Path(__file__).parent / "fixtures"


def stored_paths(value, where="policy", seen=None, depth=0):
    """Every filesystem path reachable from a policy's state (bounded walk)."""
    seen = set() if seen is None else seen
    if id(value) in seen or depth > 6:
        return
    seen.add(id(value))
    if isinstance(value, PurePath):
        yield where, Path(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from stored_paths(item, f"{where}[{key!r}]", seen, depth + 1)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            yield from stored_paths(item, f"{where}[{index}]", seen, depth + 1)
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        for key, item in vars(value).items():
            yield from stored_paths(item, f"{where}.{key}", seen, depth + 1)


def under(path: Path, root: Path) -> bool:
    resolved = (path if path.is_absolute() else Path.cwd() / path).resolve()
    root = root.resolve()
    return resolved == root or root in resolved.parents


class SessionOverrideTest(unittest.TestCase):
    def test_session_overrides_never_name_the_repository(self):
        for variable in (RUNTIME_DIR_ENV, HOME_HISTORY_DIR_ENV):
            configured = Path(os.environ[variable])
            self.assertFalse(under(configured, REPOSITORY), (variable, configured))
            self.assertFalse(under(REPOSITORY, configured), (variable, configured))
        self.assertEqual(runtime_dir(), Path(os.environ[RUNTIME_DIR_ENV]))
        # A CLI follow loop in a test must not commit the live game's save.
        archive = SaveArchiveCoordinator(log=lambda message: None).repository.root
        self.assertTrue(under(archive, Path(os.environ[RUNTIME_DIR_ENV])), archive)


class BareModuleRunTest(unittest.TestCase):
    """`python -m unittest test_x` never imports tests/__init__.py by itself."""

    def test_every_test_module_imports_the_session_package(self):
        pattern = re.compile(r"^(from tests(\.| import)|import tests\b)", re.M)
        missing = [
            module.name
            for module in sorted(Path(__file__).parent.glob("test_*.py"))
            if not pattern.search(module.read_text(encoding="utf-8"))
        ]
        self.assertEqual(missing, [], "add `import tests` so bare runs are isolated")

    def test_bare_run_without_overrides_gets_temporary_ones(self):
        environment = {
            key: value for key, value in os.environ.items()
            if key not in {RUNTIME_DIR_ENV, HOME_HISTORY_DIR_ENV}
        }
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(REPOSITORY / "src"), str(REPOSITORY / "tests"))
        )
        run = subprocess.run(
            [sys.executable, "-m", "unittest", "-v",
             "test_runtime_file_isolation.SessionOverrideTest"],
            cwd=REPOSITORY, env=environment, capture_output=True, text=True,
            timeout=300,
        )
        # Judge the probe test itself: the child's capture-ledger invariant can
        # trip on the live bot's own ledger appends while it runs.
        self.assertIn(
            "test_session_overrides_never_name_the_repository "
            "(test_runtime_file_isolation.SessionOverrideTest"
            ".test_session_overrides_never_name_the_repository) ... ok",
            run.stderr,
            run.stdout + run.stderr,
        )


class ProductionDefaultTest(unittest.TestCase):
    """I3: without overrides the bot still targets jsonlog/ exactly as before."""

    def test_defaults_without_overrides_are_jsonlog(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(RUNTIME_DIR_ENV, None)
            self.assertEqual(runtime_dir(), Path("jsonlog"))
            self.assertEqual(
                runtime_path(EXPLORATION_LEDGER_PATH.name), EXPLORATION_LEDGER_PATH
            )
            self.assertEqual(EXPLORATION_LEDGER_PATH, Path("jsonlog") / "exploration-ledger.json")
            self.assertEqual(
                runtime_path("tcp-shadow-diff.jsonl"),
                Path("jsonlog") / "tcp-shadow-diff.jsonl",
            )
            self.assertEqual(archive_repository_path(), ARCHIVE_REPOSITORY_PATH)
            self.assertEqual(ARCHIVE_REPOSITORY_PATH, Path(r"C:\hengband-save-archive"))

    def test_cli_output_paths_still_follow_the_decision_log(self):
        policy = type("Policy", (), {})()
        args = mock.Mock(
            decision_log=Path("jsonlog") / "bot-decisions.jsonl",
            capture_home_entry=False,
            capture_latch_onset=False,
            recorder_log_generations=8,
        )
        _configure_policy_output_paths(policy, args)
        self.assertEqual(policy._loadout_report_path, Path("jsonlog") / "loadout-report.jsonl")
        self.assertEqual(policy._confirmed_loadout_path, Path("jsonlog") / "confirmed-loadout.json")
        self.assertEqual(
            policy._character_calibration_path,
            Path("jsonlog") / "character-calibration.json",
        )

    def test_restore_without_overrides_keeps_captured_paths(self):
        policy, _ = test_policy_town.NoSafeRecallDestinationTest()._fixture()
        self._point_at_live_files(policy)
        with mock.patch.dict(os.environ):
            os.environ.pop(RUNTIME_DIR_ENV, None)
            os.environ.pop(HOME_HISTORY_DIR_ENV, None)
            restored = restore_checkpoint(type(policy), checkpoint(policy))
        self.assertEqual(restored._confirmed_loadout_path, LIVE_RUNTIME / "confirmed-loadout.json")
        self.assertEqual(restored._exploration_ledger.path, LIVE_RUNTIME / "exploration-ledger.json")
        self.assertEqual(restored._home_disposal.events_path, LIVE_RUNTIME / "sol-events.jsonl")

    @staticmethod
    def _point_at_live_files(policy):
        for name in POLICY_RUNTIME_PATH_ATTRIBUTES:
            setattr(policy, name, LIVE_RUNTIME / f"{name.strip('_')}.probe")
        policy._confirmed_loadout_path = LIVE_RUNTIME / "confirmed-loadout.json"
        policy._exploration_ledger = ExplorationLedger(LIVE_RUNTIME / "exploration-ledger.json")
        home = policy._home_disposal
        home.history_path, home.decisions_path, home.queue_path, home.events_path = (
            HomeDisposalState._repo_paths(REPOSITORY)
        )


class RestoredCheckpointIsolationTest(unittest.TestCase):
    """I1 mechanism: restored live checkpoints write only to the overrides."""

    def assert_isolated(self, policy):
        runtime = Path(os.environ[RUNTIME_DIR_ENV])
        history = Path(os.environ[HOME_HISTORY_DIR_ENV])
        paths = list(stored_paths(vars(policy)))
        self.assertTrue(paths)
        for where, path in paths:
            self.assertTrue(
                under(path, runtime) or under(path, history),
                f"{where} still names {path}",
            )

    def test_constructed_policy_pointing_at_live_files_is_redirected(self):
        policy, _ = test_policy_town.NoSafeRecallDestinationTest()._fixture()
        ProductionDefaultTest._point_at_live_files(policy)

        restored = restore_checkpoint(type(policy), checkpoint(policy))

        self.assert_isolated(restored)
        runtime = Path(os.environ[RUNTIME_DIR_ENV])
        self.assertEqual(restored._confirmed_loadout_path, runtime / "confirmed-loadout.json")
        self.assertEqual(restored._exploration_ledger.path, runtime / "exploration-ledger.json")
        history = Path(os.environ[HOME_HISTORY_DIR_ENV])
        self.assertEqual(restored._home_disposal.history_path, history / "home-withdraw-history.jsonc")
        self.assertEqual(
            restored._home_disposal.events_path, history / "jsonlog" / "sol-events.jsonl"
        )

    def test_live_captured_checkpoint_is_redirected_on_restore(self):
        _, policy_blob, _ = checkpoint_row(
            FIXTURES / "golden-trajectory-decision-110.jsonl.gz", 110
        )
        # The capture really carries the live bot's locations ...
        raw = pickle.loads(base64.b64decode(policy_blob))
        captured = {where: path for where, path in stored_paths(raw)}
        self.assertIn("policy['_loadout_report_path']", captured)
        self.assertIn("policy['_exploration_ledger'].path", captured)
        self.assertIn("policy['_home_disposal'].events_path", captured)
        self.assertTrue(all(path.parent.name in {"jsonlog", "bot-client"}
                            for path in captured.values()), captured)

        # ... and none of them survives restoration in a test session.
        from hengbot.policy import HengbotPolicy

        self.assert_isolated(restore_checkpoint(HengbotPolicy, policy_blob))

    def test_isolation_is_a_no_op_for_unset_paths(self):
        holder = type("Policy", (), {})()
        holder._loadout_report_path = None
        isolate_restored_runtime_paths(holder)
        self.assertIsNone(holder._loadout_report_path)


class RuntimeWriteGuardTest(unittest.TestCase):
    """I2: a test run that writes the live runtime files fails."""

    def setUp(self):
        self.target = LIVE_RUNTIME / f".isolation-guard-probe-{uuid.uuid4().hex}"
        self.addCleanup(self._remove_probe)

    def _remove_probe(self):
        with session.suspended_runtime_write_guard():
            if self.target.exists():
                self.target.unlink()

    def test_write_is_blocked_and_recorded(self):
        with session.expected_runtime_write_violations() as violations:
            with self.assertRaises(PermissionError):
                with open(self.target, "a", encoding="utf-8"):
                    pass
            with self.assertRaises(PermissionError):
                os.open(self.target, os.O_WRONLY | os.O_CREAT)
            with tempfile.NamedTemporaryFile(delete=False) as stream:
                source = Path(stream.name)
            self.addCleanup(source.unlink, missing_ok=True)
            with self.assertRaises(PermissionError):
                os.replace(source, self.target)
            with self.assertRaises(PermissionError):
                open(REPOSITORY / "home-withdraw-history.jsonc", "a").close()
        self.assertFalse(self.target.exists())
        self.assertEqual(
            [event for _, event, _ in violations], ["open", "open", "os.rename", "open"]
        )
        self.assertTrue(all(test == self.id() for test, _, _ in violations))

    def test_reads_are_allowed(self):
        if not LIVE_RUNTIME.is_dir():
            self.skipTest("no jsonlog/ in this checkout")
        with session.expected_runtime_write_violations() as violations:
            live = next(LIVE_RUNTIME.glob("*.json"), None)
            if live is not None:
                with open(live, "rb") as stream:
                    stream.read(1)
            LIVE_RUNTIME.mkdir(exist_ok=True)
        self.assertEqual(violations, [])

    def test_writing_test_fails_the_outermost_run(self):
        target = self.target

        class WritingProbe(unittest.TestCase):
            """Deliberately writes a live runtime file (local, so never collected)."""

            def test_write(self):
                with open(target, "x", encoding="utf-8") as stream:
                    stream.write("probe\n")

        suite = unittest.TestSuite([WritingProbe("test_write")])
        # Pretend the probe run is the outermost one, as in a real session.
        saved = list(session._active_runs)
        session._active_runs.clear()
        try:
            with open(os.devnull, "w", encoding="utf-8") as sink:
                result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
        finally:
            session._active_runs[:] = saved
        self.assertFalse(self.target.exists())
        invariant = [
            test for test, _ in result.failures
            if isinstance(test, session._RuntimeFileInvariant)
        ]
        self.assertEqual(len(invariant), 1, result.failures)
        message = dict(result.failures)[invariant[0]]
        self.assertIn(str(self.target), message)
        self.assertIn("WritingProbe.test_write", message)
        self.assertNotIn(str(self.target), repr(session._runtime_write_violations))

    def test_self_test_run_does_not_absorb_earlier_session_violations(self):
        earlier = ("earlier.test", "open", str(LIVE_RUNTIME / "earlier"))
        session._runtime_write_violations.append(earlier)
        try:
            saved = list(session._active_runs)
            session._active_runs.clear()
            try:
                with open(os.devnull, "w", encoding="utf-8") as sink:
                    result = unittest.TextTestRunner(stream=sink, verbosity=0).run(
                        unittest.TestSuite()
                    )
            finally:
                session._active_runs[:] = saved
            self.assertFalse(any(
                isinstance(test, session._RuntimeFileInvariant) for test, _ in result.failures
            ))
            self.assertIn(earlier, session._runtime_write_violations)
        finally:
            session._runtime_write_violations.remove(earlier)


if __name__ == "__main__":
    unittest.main()
