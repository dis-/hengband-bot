"""Repository-wide unittest invariants."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest

from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.save_archive import ARCHIVE_REPOSITORY_PATH


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _main_checkout(root: Path) -> Path:
    """A linked worktree's main checkout (where the live bot runs), else root."""
    try:
        marker = (root / ".git").read_text(encoding="utf-8").strip()
    except OSError:  # a directory in the main checkout itself
        return root
    if not marker.startswith("gitdir:"):
        return root
    gitdir = Path(marker.partition(":")[2].strip())
    # <main>/.git/worktrees/<name>
    return gitdir.resolve().parents[2] if gitdir.parent.name == "worktrees" else root


# Files the live bot owns.  A test session may read them but never write them:
# the bot runs from the main checkout while suites run, and checkpoints
# captured from it name its absolute paths even when tests run in a worktree.
_CHECKOUTS = tuple(dict.fromkeys((_REPOSITORY_ROOT, _main_checkout(_REPOSITORY_ROOT))))
_RUNTIME_DIRS = (
    *(checkout / "jsonlog" for checkout in _CHECKOUTS),
    *(checkout / "incident-captures" for checkout in _CHECKOUTS),
    ARCHIVE_REPOSITORY_PATH,
)
_RUNTIME_FILES = tuple(
    checkout / name
    for checkout in _CHECKOUTS
    for name in ("home-withdraw-history.jsonc", "home-disposal-decisions.jsonc")
)


def _resolved(raw: object) -> Path | None:
    try:
        path = Path(os.fsdecode(raw))
        return (path if path.is_absolute() else Path.cwd() / path).resolve()
    except (TypeError, ValueError, OSError):
        return None


def _repository_runtime_path(raw: object) -> Path | None:
    """Return the resolved path when it names a live runtime file or dir."""
    if isinstance(raw, int) or raw is None:
        return None
    path = _resolved(raw)
    if path is None:
        return None
    if path in _RUNTIME_FILES:
        return path
    for directory in _RUNTIME_DIRS:
        if path == directory or directory in path.parents:
            return path
    return None


def _isolated_default(variable: str, prefix: str, leaf: str = "") -> None:
    """Give the session a temporary override that never names live files."""
    if not os.environ.get(variable, "").strip():
        directory = Path(tempfile.mkdtemp(prefix=prefix)) / leaf
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(directory)
    configured = _resolved(os.environ[variable])
    if configured is None or configured in _CHECKOUTS or any(
        configured == directory or directory in configured.parents
        for directory in _RUNTIME_DIRS
    ):
        raise RuntimeError(
            f"{variable}={os.environ[variable]!r} resolves to the live bot's "
            f"runtime files under {_REPOSITORY_ROOT}; tests must use a "
            f"temporary directory"
        )


_isolated_default(HOME_HISTORY_DIR_ENV, "hengbot-test-history-")
# A "jsonlog" leaf keeps the flight recorder's sibling incident-captures/ inside
# the session's own temporary directory.
_isolated_default(RUNTIME_DIR_ENV, "hengbot-test-runtime-", "jsonlog")


_LEDGER_ROOT = _REPOSITORY_ROOT / "capture-ledger"


def _capture_fingerprint():
    if not _LEDGER_ROOT.exists():
        return False, ()
    return True, tuple(
        (path.relative_to(_LEDGER_ROOT).as_posix(), path.stat().st_size,
         path.stat().st_mtime_ns)
        for path in sorted(_LEDGER_ROOT.rglob("*")) if path.is_file()
    )


_CAPTURE_BEFORE = _capture_fingerprint()


class _CaptureLedgerInvariant(unittest.TestCase):
    pass


class _RuntimeFileInvariant(unittest.TestCase):
    pass


# Live-runtime write guard.  An audit hook sees every open/rename/remove made
# by this test process while a test run is in progress, blocks those that
# target the live bot's files and records them; the outermost run then fails.
# The live bot is a different process, so its own writes to the same files are
# invisible here and can never trip this guard.  Child processes started by
# tests inherit the two overrides above instead.
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_PATH_EVENTS = frozenset({"os.rename", "os.remove", "os.truncate", "os.mkdir",
                          "os.rmdir", "os.chmod", "os.utime", "shutil.rmtree"})
_guard = {"suspended": 0, "test": "<no test>"}
# Results of the test runs in progress (outermost first).  Runner self-tests
# nest runs; only the outermost run reports, so a nested result cannot absorb
# a violation.
_active_runs: list[tuple[int, int]] = []  # (id(result), first violation index)
_runtime_write_violations: list[tuple[str, str, str]] = []


def _write_targets(event: str, args: tuple) -> tuple[object, ...]:
    if event == "open":
        path, mode, flags = args
        if isinstance(mode, str):
            writing = any(character in mode for character in "wax+")
        else:
            writing = bool((flags or 0) & _WRITE_FLAGS)
        return (path,) if writing else ()
    if event in _PATH_EVENTS:
        return tuple(value for value in args[:2]
                     if isinstance(value, (str, bytes, os.PathLike)))
    return ()


def _runtime_write_audit(event: str, args: tuple) -> None:
    if not _active_runs or _guard["suspended"]:
        return
    if event != "open" and event not in _PATH_EVENTS:
        return
    for target in _write_targets(event, args):
        path = _repository_runtime_path(target)
        if path is None:
            continue
        if event == "os.mkdir" and path.is_dir():
            continue  # mkdir(exist_ok=True) of an existing directory writes nothing
        _runtime_write_violations.append(
            (_guard["test"], event, str(path))
        )
        raise PermissionError(
            f"test run may not write the live bot's runtime file {path} "
            f"({event}); route it through {RUNTIME_DIR_ENV}/{HOME_HISTORY_DIR_ENV}"
        )


sys.addaudithook(_runtime_write_audit)


@contextmanager
def expected_runtime_write_violations():
    """Collect guard violations raised inside the block without failing the run."""
    start = len(_runtime_write_violations)
    collected: list[tuple[str, str, str]] = []
    try:
        yield collected
    finally:
        collected.extend(_runtime_write_violations[start:])
        del _runtime_write_violations[start:]


@contextmanager
def suspended_runtime_write_guard():
    """Only for guard self-tests cleaning up after a failed block."""
    _guard["suspended"] += 1
    try:
        yield
    finally:
        _guard["suspended"] -= 1


_ORIGINAL_START_TEST_RUN = unittest.TestResult.startTestRun
_ORIGINAL_BASE_STOP_TEST_RUN = unittest.TestResult.stopTestRun
_ORIGINAL_START_TEST = unittest.TestResult.startTest


def _guarded_start_test_run(result):
    _active_runs.append((id(result), len(_runtime_write_violations)))
    return _ORIGINAL_START_TEST_RUN(result)


def _guarded_base_stop_test_run(result):
    positions = [index for index, (run, _) in enumerate(_active_runs) if run == id(result)]
    if not positions:
        return _ORIGINAL_BASE_STOP_TEST_RUN(result)
    first = _active_runs[positions[0]][1]
    del _active_runs[positions[0]:]
    # Report only this run's own violations, so a run that is outermost only
    # by construction (the guard self-test) cannot absorb the session's.
    if not _active_runs and _runtime_write_violations[first:]:
        violations = list(dict.fromkeys(_runtime_write_violations[first:]))
        del _runtime_write_violations[first:]
        error = AssertionError(
            "test run wrote the live bot's runtime files: "
            + "; ".join(f"{test}: {event} {path}" for test, event, path in violations)
        )
        result.addFailure(
            _RuntimeFileInvariant("runTest"),
            (AssertionError, error, error.__traceback__),
        )
    return _ORIGINAL_BASE_STOP_TEST_RUN(result)


def _tracking_start_test(result, test):
    _guard["test"] = test.id()
    return _ORIGINAL_START_TEST(result, test)


unittest.TestResult.startTestRun = _guarded_start_test_run
unittest.TestResult.stopTestRun = _guarded_base_stop_test_run
unittest.TestResult.startTest = _tracking_start_test


def _guarded_stop_test_run(result):
    after = _capture_fingerprint()
    if after != _CAPTURE_BEFORE:
        error = AssertionError(
            f"test run wrote repository capture ledger: "
            f"{_CAPTURE_BEFORE!r} -> {after!r}"
        )
        result.addFailure(
            _CaptureLedgerInvariant("runTest"),
            (AssertionError, error, error.__traceback__),
        )
    # Chain to the guarded base so the runtime-file check runs for text runs too.
    return unittest.TestResult.stopTestRun(result)


unittest.TextTestResult.stopTestRun = _guarded_stop_test_run
