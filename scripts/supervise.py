#!/usr/bin/env python3
"""One-line event supervisors for solver, suite, and bot runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def process_rows(output: str) -> list[tuple[int, str]]:
    try: rows = json.loads(output or "[]")
    except json.JSONDecodeError: return []
    if isinstance(rows, dict): rows = [rows]
    return [(int(row["ProcessId"]), str(row.get("CommandLine") or "")) for row in rows]


def codex_pids(rows: list[tuple[int, str]], prompt_name: str) -> set[int]:
    needle = prompt_name.lower()
    return {pid for pid, command in rows if needle in command.lower() and "codex" in command.lower()}


def matching_reasons(lines: list[str], seen: set[str]) -> list[str]:
    emitted = []
    for line in lines:
        try: row = json.loads(line)
        except json.JSONDecodeError: continue
        reason = str(row.get("reason", ""))
        if any(word in reason.lower() for word in ("town:blocked", "stuck", "loop", "emergency")) and reason not in seen:
            seen.add(reason); emitted.append(reason)
    return emitted


def alive(pid: int) -> bool:
    run = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
                         capture_output=True, text=True)
    return run.returncode == 0 and bool(run.stdout.strip())


def cim_rows() -> list[tuple[int, str]]:
    command = "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    run = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True)
    return process_rows(run.stdout)


def process_identity(pid: int | None) -> tuple[str, str] | None:
    """(image name, command line) of a live pid, or None when nothing holds it."""
    if not pid:
        return None
    command = (f"Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | "
               "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    run = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True)
    try: row = json.loads(run.stdout or "null")
    except json.JSONDecodeError: return None
    if isinstance(row, list): row = row[0] if row else None
    if not isinstance(row, dict): return None
    return str(row.get("Name") or ""), str(row.get("CommandLine") or "")


def identified_alive(pid: int | None, needle: str) -> tuple[bool, str]:
    """Liveness AND identity, because a pid file outlives the process that wrote it.

    A recycled pid passes ``alive()`` while belonging to an unrelated program, so
    a stale ``bot.pid`` would read as a healthy bot (the 2026-09-23 regression).
    """
    if not pid:
        return False, "no pid recorded"
    identity = process_identity(pid)
    if identity is None:
        return False, f"pid {pid} holds no process (stale pid)"
    name, command = identity
    if needle.lower() not in command.lower():
        shown = command[:80] or name
        return False, f"pid {pid} is {name} ({shown!r}), not {needle} (stale pid)"
    return True, f"pid {pid} alive as {name}"


def sol(args) -> int:
    prompt_name = Path(args.prompt_file).name
    initial = codex_pids(cim_rows(), prompt_name)
    if not initial:
        print("SOL-EXIT", flush=True); return 0
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    size = Path(args.log).stat().st_size if Path(args.log).exists() else 0
    growth = time.monotonic()
    silent_reported = False
    while True:
        now_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if now_head != head:
            oneline = subprocess.check_output(["git", "show", "-s", "--oneline", now_head], cwd=ROOT, text=True).strip()
            print(f"COMMIT {oneline}", flush=True); head = now_head
        log = Path(args.log); now_size = log.stat().st_size if log.exists() else 0
        if now_size != size: size, growth, silent_reported = now_size, time.monotonic(), False
        minutes = (time.monotonic() - growth) / 60
        if minutes >= args.silent_minutes and not silent_reported:
            print(f"SOL-SILENT {int(minutes)}", flush=True); silent_reported = True
        pid_file = ROOT / "jsonlog" / "hengband.pid"
        if pid_file.exists() and not alive(int(pid_file.read_text().strip())):
            print("GAME-DEAD", flush=True); return 1
        current = codex_pids(cim_rows(), prompt_name)
        if initial and not (initial & current):
            print("SOL-EXIT", flush=True); return 0
        time.sleep(args.interval)


def suite_commands(head: str, runs: int) -> list[list[str]]:
    commands = []
    for index in range(1, runs + 1):
        commands.append([sys.executable, "scripts/run_receipt.py", "--tool", "suite", "--target", f"run-{index}", "--",
                         sys.executable, "scripts/test_parallel_runner.py"])
    commands.append([sys.executable, "-m", "unittest", "tests.test_cli"])
    return commands


def suite(args) -> int:
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if current != args.head:
        print(f"SUITE-HEAD-MISMATCH expected={args.head} actual={current}")
        print("SUITE-DONE red"); return 1
    commands = suite_commands(args.head, args.runs)
    if args.dry_run:
        for command in commands: print("DRY-RUN " + subprocess.list2cmdline(command))
        print("SUITE-DONE green"); return 0
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join(("src", "tests"))
    receipts_before = set((ROOT / "jsonlog" / "receipts").glob("*.json"))
    for index, command in enumerate(commands, 1):
        run = subprocess.run(command, cwd=ROOT, env=env)
        print(f"SUITE-RUN {index} {'green' if run.returncode == 0 else 'red'}", flush=True)
        if run.returncode:
            print("SUITE-DONE red"); return 1
    receipts = sorted(set((ROOT / "jsonlog" / "receipts").glob("*.json")) - receipts_before)
    for receipt in receipts:
        run = subprocess.run([sys.executable, "scripts/verify_receipt.py", str(receipt)], cwd=ROOT, env=env)
        if run.returncode:
            print("SUITE-DONE red"); return 1
    print("SUITE-DONE green"); return 0


def bot(args) -> int:
    path = ROOT / "jsonlog" / "bot-decisions.jsonl"
    stderr = ROOT / "jsonlog" / "bot-stderr.log"
    offset = path.stat().st_size if path.exists() else 0
    stderr_size = stderr.stat().st_size if stderr.exists() else 0
    last_decision = time.monotonic(); seen: set[str] = set()
    while True:
        if not alive(args.pid): print("BOT-DEAD"); return 0
        if path.exists() and path.stat().st_size > offset:
            with path.open(encoding="utf-8", errors="replace") as stream:
                stream.seek(offset); lines = stream.readlines(); offset = stream.tell()
            last_decision = time.monotonic()
            for reason in matching_reasons(lines, seen): print(f"BOT-REASON {reason}", flush=True)
        if stderr.exists() and stderr.stat().st_size > stderr_size:
            growth = stderr.stat().st_size - stderr_size; stderr_size += growth
            print(f"BOT-STDERR +{growth}", flush=True)
        if time.monotonic() - last_decision >= 180:
            print("BOT-STALL 180s", flush=True); last_decision = time.monotonic()
        time.sleep(args.interval)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("sol"); p.add_argument("--prompt-file", required=True); p.add_argument("--log", required=True)
    p.add_argument("--silent-minutes", type=float, default=10); p.add_argument("--interval", type=float, default=5); p.set_defaults(action=sol)
    p = subs.add_parser("suite"); p.add_argument("--head", required=True); p.add_argument("--runs", type=int, required=True); p.add_argument("--dry-run", action="store_true"); p.set_defaults(action=suite)
    p = subs.add_parser("bot"); p.add_argument("--pid", type=int, required=True); p.add_argument("--interval", type=float, default=2); p.set_defaults(action=bot)
    args = parser.parse_args(argv); return args.action(args)


if __name__ == "__main__": raise SystemExit(main())
