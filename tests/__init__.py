"""Repository-wide unittest invariants."""

from __future__ import annotations

from pathlib import Path
import unittest


_LEDGER_ROOT = Path(__file__).resolve().parents[1] / "capture-ledger"


def _capture_fingerprint():
    if not _LEDGER_ROOT.exists():
        return False, ()
    return True, tuple(
        (path.relative_to(_LEDGER_ROOT).as_posix(), path.stat().st_size,
         path.stat().st_mtime_ns)
        for path in sorted(_LEDGER_ROOT.rglob("*")) if path.is_file()
    )


_CAPTURE_BEFORE = _capture_fingerprint()
_ORIGINAL_STOP_TEST_RUN = unittest.TextTestResult.stopTestRun


class _CaptureLedgerInvariant(unittest.TestCase):
    pass


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
    return _ORIGINAL_STOP_TEST_RUN(result)


unittest.TextTestResult.stopTestRun = _guarded_stop_test_run
