#!/usr/bin/env python3
"""Run a command and write an unsigned verification receipt.

Receipts defend against drift and carelessness (stale source trees and copied
summary numbers), not deliberate forgery.  They are unsigned by design, so a
reviewer should still spot-run suspicious evidence.  Their binding fingerprint
excludes ``jsonlog/`` because the tracked append-only operator event log records
the receipt after the source verification it describes.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import verify_scope
from failure_headers import iter_failure_headers


ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "jsonlog" / "receipts"
HOME_HISTORY_DIR_ENV = "HENGBOT_HOME_HISTORY_DIR"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "run"


@contextlib.contextmanager
def isolated_home_history():
    """Give a receipt run private durable history unless its caller supplied one."""
    supplied_history_dir = os.environ.get(HOME_HISTORY_DIR_ENV)
    if supplied_history_dir:
        yield supplied_history_dir
        return
    with tempfile.TemporaryDirectory(prefix="hengbot-receipt-history-") as name:
        os.environ[HOME_HISTORY_DIR_ENV] = name
        try:
            yield name
        finally:
            os.environ.pop(HOME_HISTORY_DIR_ENV, None)


def source_fingerprint(root: Path) -> str:
    """Hash tracked source state, excluding the append-only ``jsonlog/``."""
    digest = hashlib.sha256()
    for rel in sorted(verify_scope.git(root, "ls-files").splitlines()):
        normalized = rel.replace("\\", "/")
        if normalized == "jsonlog" or normalized.startswith("jsonlog/"):
            continue
        path = root / rel
        if path.is_file():
            digest.update(normalized.encode()); digest.update(b"\0")
            digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def summarize(stdout: str, stderr: str) -> dict[str, object]:
    combined = stdout + "\n" + stderr
    outcomes = [(header.kind, header.identity) for header in
                iter_failure_headers(combined, test_names_only=False)]
    ran = re.findall(r"^Ran (\d+) tests?", combined, re.MULTILINE)
    recorded = re.findall(r"recorded (\d+) tests", combined)
    total = re.findall(r"^Total: (\d+) tests", combined, re.MULTILINE)
    summary_lines = [line for line in combined.splitlines() if
                     re.search(r"(?:JSON_SUMMARY=|^PASS\b|^FAIL\b|^Total:|^Ran \d+ tests?)", line)]
    return {
        "test_count": int((ran or recorded or total)[-1]) if (ran or recorded or total) else None,
        "failures": list(dict.fromkeys(identity for kind, identity in outcomes if kind == "FAIL")),
        "errors": list(dict.fromkeys(identity for kind, identity in outcomes if kind == "ERROR")),
        "summary_lines": summary_lines[-10:],
    }


def inferred_exit_code(stdout: str, stderr: str) -> int | None:
    """Infer success/failure only where conventional runner output proves it."""
    combined = stdout + "\n" + stderr
    if re.search(r"^FAILED\b", combined, re.MULTILINE):
        return 1
    if re.search(r"^OK(?:\s|$)", combined, re.MULTILINE):
        return 0
    failures = re.findall(r"^Failures: (.+)$", combined, re.MULTILINE)
    errors = re.findall(r"^Errors: (.+)$", combined, re.MULTILINE)
    if failures and errors:
        return int(failures[-1].strip() != "none" or errors[-1].strip() != "none")
    return None


def write_receipt(tool: str, target: str, argv: list[str], started: datetime,
                  ended: datetime, exit_code: int, stdout_path: Path,
                  stderr_path: Path, head_sha: str, binding: str) -> Path:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S%z")
    receipt = RECEIPTS / f"{safe(tool)}-{safe(target)}-{stamp}.json"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    payload = {
        "schema_version": 2, "tool": tool, "target": target, "argv": argv,
        "head_sha": head_sha, "source_fingerprint": binding,
        "started_at": started.isoformat(), "ended_at": ended.isoformat(),
        "exit_code": exit_code, "result": summarize(stdout, stderr),
        "streams": {
            "stdout": {"path": str(stdout_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(stdout_path)},
            "stderr": {"path": str(stderr_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(stderr_path)},
        },
    }
    receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return receipt


class Tee(io.TextIOBase):
    def __init__(self, display: io.TextIOBase, saved: io.TextIOBase) -> None:
        self.display, self.saved = display, saved

    def fileno(self) -> int:
        for stream in (self.display, self.saved):
            try:
                return stream.fileno()
            except (AttributeError, io.UnsupportedOperation, ValueError):
                continue
        raise io.UnsupportedOperation("fileno")

    def write(self, value: str) -> int:
        try:
            self.saved.write(value); self.saved.flush()
        except ValueError:
            pass
        try:
            self.display.write(value)
        except UnicodeEncodeError:
            encoding = getattr(self.display, "encoding", None) or "utf-8"
            rendered = value.encode(encoding, errors="backslashreplace").decode(encoding)
            self.display.write(rendered)
        except ValueError:
            pass
        try:
            self.display.flush()
        except ValueError:
            pass
        return len(value)

    def flush(self) -> None:
        for stream in (self.display, self.saved):
            try:
                stream.flush()
            except ValueError:
                pass


def run_native(tool: str, target: str, argv: list[str], action: Callable[[], int]) -> int:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    started, head, tree = now(), verify_scope.git(ROOT, "rev-parse", "HEAD").strip(), source_fingerprint(ROOT)
    stem = f"{safe(tool)}-{safe(target)}-{started.strftime('%Y%m%dT%H%M%S%z')}"
    stdout_path, stderr_path = RECEIPTS / f"{stem}.stdout.log", RECEIPTS / f"{stem}.stderr.log"
    with isolated_home_history():
        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
            with contextlib.redirect_stdout(Tee(sys.stdout, out)), contextlib.redirect_stderr(Tee(sys.stderr, err)):
                exit_code = action()
    receipt = write_receipt(tool, target, argv, started, now(), exit_code,
                            stdout_path, stderr_path, head, tree)
    print(f"Receipt: {receipt}; sha256: {sha256(receipt)}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool")
    parser.add_argument("--target", default="run")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    tool = args.tool or Path(command[0]).stem
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    started, head, tree = now(), verify_scope.git(ROOT, "rev-parse", "HEAD").strip(), source_fingerprint(ROOT)
    stem = f"{safe(tool)}-{safe(args.target)}-{started.strftime('%Y%m%dT%H%M%S%z')}"
    stdout_path, stderr_path = RECEIPTS / f"{stem}.stdout.log", RECEIPTS / f"{stem}.stderr.log"
    with isolated_home_history() as history_dir:
        environment = os.environ.copy()
        environment[HOME_HISTORY_DIR_ENV] = history_dir
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            run = subprocess.run(command, cwd=ROOT, env=environment, stdout=out, stderr=err)
    receipt = write_receipt(tool, args.target, command, started, now(), run.returncode,
                            stdout_path, stderr_path, head, tree)
    sys.stdout.write(stdout_path.read_text(encoding="utf-8", errors="replace"))
    sys.stderr.write(stderr_path.read_text(encoding="utf-8", errors="replace"))
    print(f"Receipt: {receipt}; sha256: {sha256(receipt)}")
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
