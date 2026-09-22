"""Append one validated event to jsonlog/sol-events.jsonl.

Usage (the event is a single JSON object):
    python scripts/append_sol_event.py --json '{"time":"...","type":"fix",...}'
    python scripts/append_sol_event.py --file event.json
    <producer> | python scripts/append_sol_event.py

The event is re-serialized as one compact UTF-8 line and appended with a
trailing newline; a missing newline at the end of the log is repaired first.
Invalid JSON, a non-object, or an unreadable file is refused (exit 2) and
nothing is written.  ``--check`` validates the whole log instead (exit 1 on a
bad line).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hengbot.sol_events import (  # noqa: E402
    InvalidEventError,
    append_event,
    format_problems,
    invalid_lines,
)

DEFAULT_LOG = ROOT / "jsonlog" / "sol-events.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--json", help="the event as a JSON object string")
    source.add_argument("--file", type=Path, help="a UTF-8 file holding the event")
    source.add_argument("--check", action="store_true", help="validate the log and exit")
    args = parser.parse_args(argv)

    if args.check:
        problems = invalid_lines(args.log.read_bytes()) if args.log.exists() else []
        if problems:
            print(format_problems(problems), file=sys.stderr)
            return 1
        print(f"{args.log}: OK")
        return 0

    if args.json is not None:
        text = args.json
    elif args.file is not None:
        text = args.file.read_text(encoding="utf-8-sig")
    else:
        text = sys.stdin.buffer.read().decode("utf-8-sig")
    try:
        line = append_event(args.log, text.strip())
    except InvalidEventError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    # Echo as UTF-8 bytes: a cp932 console must not turn a completed append
    # into an error exit.
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
