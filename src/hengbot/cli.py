from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterable

from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument("--send-to-window", action="store_true")
    parser.add_argument("--window-title")
    parser.add_argument("--window-title-contains", action="store_true")
    parser.add_argument("--window-class", default="ANGBAND")
    parser.add_argument("--window-pid", type=int)
    parser.add_argument("--list-windows", action="store_true")
    args = parser.parse_args(argv)

    if args.list_windows:
        from hengbot.input_windows import list_windows

        for window in list_windows():
            line = f"{window.hwnd}\tpid={window.process_id}\tclass={window.class_name}\ttitle={window.title}"
            encoding = sys.stdout.encoding or "utf-8"
            print(line.encode(encoding, errors="replace").decode(encoding))
        return 0

    policy = ConservativePolicy()
    lines = _read_last_line(args.state_file) if args.once else _follow(args.state_file, args.poll_interval)
    for line in _deduplicate_consecutive(lines):
        if not line.strip():
            continue
        try:
            snapshot = parse_snapshot(json.loads(line))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid snapshot: {exc}", file=sys.stderr)
            if args.once:
                return 2
            continue

        key = policy.choose_key(snapshot)
        print(key, flush=True)
        if args.send_to_window:
            try:
                from hengbot.input_windows import send_key_to_window

                send_key_to_window(
                    key,
                    args.window_title,
                    contains=args.window_title_contains,
                    class_name=args.window_class,
                    process_id=args.window_pid,
                )
            except RuntimeError as exc:
                print(f"failed to send key: {exc}", file=sys.stderr)
                if args.once:
                    return 3

        if args.once:
            return 0

    return 1


def _read_last_line(path: Path) -> Iterable[str]:
    if not path.exists():
        return []

    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        chunks: list[bytes] = []
        newline_count = 0

        while position > 0 and newline_count < 2:
            chunk_size = min(64 * 1024, position)
            position -= chunk_size
            file.seek(position)
            chunk = file.read(chunk_size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")

    data = b"".join(reversed(chunks))
    lines = data.splitlines()
    if data and not data.endswith(b"\n"):
        lines = lines[:-1]
    if not lines:
        return []
    return [lines[-1].decode("utf-8")]


def _follow(path: Path, poll_interval: float) -> Iterable[str]:
    while not path.exists():
        time.sleep(poll_interval)

    with path.open("r", encoding="utf-8") as file:
        file.seek(0, 2)
        pending = ""
        while True:
            chunk = file.read()
            if chunk:
                complete_lines, pending = _split_complete_lines(pending + chunk)
                yield from complete_lines
                continue
            time.sleep(poll_interval)


def _split_complete_lines(data: str) -> tuple[list[str], str]:
    parts = data.split("\n")
    complete_lines = [part + "\n" for part in parts[:-1]]
    return complete_lines, parts[-1]


def _deduplicate_consecutive(lines: Iterable[str]) -> Iterable[str]:
    previous: str | None = None
    for line in lines:
        snapshot = line.strip()
        if snapshot and snapshot == previous:
            continue
        previous = snapshot
        yield line
