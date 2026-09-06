#!/usr/bin/env python3
"""Run a verification command and write a tamper-evident execution receipt."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import verify_scope


ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "jsonlog" / "receipts"
FAILURE_RE = re.compile(
    r"^(FAIL|ERROR): \S+ \(([^)\r\n]+)\)"
    r"(?: \[[^\r\n]*\])?(?: \([^\r\n]*\))?$",
    re.MULTILINE,
)


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


def summarize(stdout: str, stderr: str) -> dict[str, object]:
    combined = stdout + "\n" + stderr
    outcomes = [(kind, identity) for kind, identity in FAILURE_RE.findall(combined)]
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


def write_receipt(tool: str, target: str, argv: list[str], started: datetime,
                  ended: datetime, exit_code: int, stdout_path: Path,
                  stderr_path: Path, head_sha: str, tree: str) -> Path:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S%z")
    receipt = RECEIPTS / f"{safe(tool)}-{safe(target)}-{stamp}.json"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    payload = {
        "schema_version": 1, "tool": tool, "target": target, "argv": argv,
        "head_sha": head_sha, "tree_fingerprint": tree,
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

    def write(self, value: str) -> int:
        self.display.write(value); self.display.flush()
        self.saved.write(value); self.saved.flush()
        return len(value)

    def flush(self) -> None:
        self.display.flush(); self.saved.flush()


def run_native(tool: str, target: str, argv: list[str], action: Callable[[], int]) -> int:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    started, head, tree = now(), verify_scope.git(ROOT, "rev-parse", "HEAD").strip(), verify_scope.tree_fingerprint(ROOT)
    stem = f"{safe(tool)}-{safe(target)}-{started.strftime('%Y%m%dT%H%M%S%z')}"
    stdout_path, stderr_path = RECEIPTS / f"{stem}.stdout.log", RECEIPTS / f"{stem}.stderr.log"
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
    started, head, tree = now(), verify_scope.git(ROOT, "rev-parse", "HEAD").strip(), verify_scope.tree_fingerprint(ROOT)
    stem = f"{safe(tool)}-{safe(args.target)}-{started.strftime('%Y%m%dT%H%M%S%z')}"
    stdout_path, stderr_path = RECEIPTS / f"{stem}.stdout.log", RECEIPTS / f"{stem}.stderr.log"
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        run = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err)
    receipt = write_receipt(tool, args.target, command, started, now(), run.returncode,
                            stdout_path, stderr_path, head, tree)
    sys.stdout.write(stdout_path.read_text(encoding="utf-8", errors="replace"))
    sys.stderr.write(stderr_path.read_text(encoding="utf-8", errors="replace"))
    print(f"Receipt: {receipt}; sha256: {sha256(receipt)}")
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
