"""Test-only isolation for every production capture ledger."""

from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import cli


PRODUCTION_LEDGER_ROOT = cli.CAPTURE_LEDGER_ROOT.resolve()


def fingerprint_capture_ledgers(root: Path = PRODUCTION_LEDGER_ROOT):
    """Fingerprint the complete ledger directory, including absent files."""
    if not root.exists():
        return False, ()
    return True, tuple(
        (path.relative_to(root).as_posix(), path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*")) if path.is_file()
    )


def run_follow_with_ledger(ledger_path: Path, *args, **kwargs):
    """Run follow with an injected ledger and fail if production was touched."""
    before = fingerprint_capture_ledgers()
    knowledge_path = ledger_path.with_name("knowledge-responses.jsonl")
    result = cli._run_follow(
        *args,
        read_batch_ledger_path=ledger_path,
        knowledge_ledger_path=knowledge_path,
        **kwargs,
    )
    after = fingerprint_capture_ledgers()
    if after != before:
        raise AssertionError(
            f"test wrote repository capture ledger directory {PRODUCTION_LEDGER_ROOT}: "
            f"{before!r} -> {after!r}"
        )
    return result


def run_follow(*args, **kwargs):
    """Run follow with a disposable ledger and fail if production was touched."""
    with TemporaryDirectory() as tmp:
        return run_follow_with_ledger(Path(tmp) / "read-batches.jsonl", *args, **kwargs)
