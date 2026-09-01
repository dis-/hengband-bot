"""Test-only isolation for the production read-batch capture ledger."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import cli


PRODUCTION_LEDGER = cli.READ_BATCH_LEDGER_PATH.resolve()


def _fingerprint():
    stat = PRODUCTION_LEDGER.stat()
    return stat.st_size, stat.st_mtime_ns


def run_follow_with_ledger(ledger_path: Path, *args, **kwargs):
    """Run follow with an injected ledger and fail if production was touched."""
    before = _fingerprint()
    with patch("hengbot.cli.READ_BATCH_LEDGER_PATH", ledger_path):
        result = cli._run_follow(*args, **kwargs)
    after = _fingerprint()
    if after != before:
        raise AssertionError(
            f"test wrote repository capture ledger {PRODUCTION_LEDGER}: "
            f"{before!r} -> {after!r}"
        )
    return result


def run_follow(*args, **kwargs):
    """Run follow with a disposable ledger and fail if production was touched."""
    with TemporaryDirectory() as tmp:
        return run_follow_with_ledger(Path(tmp) / "read-batches.jsonl", *args, **kwargs)
