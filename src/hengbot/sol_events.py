"""Validated appender and checker for ``jsonlog/sol-events.jsonl``.

The event log is one JSON object per line, UTF-8, every line terminated by
``\\n``.  Hand-written appends broke that twice: a writer that left no trailing
newline made the next append land on the same line (two objects on one line),
and a writer using the console code page produced mojibake that swallowed a
closing quote.  Every writer goes through :func:`append_event` (Python),
``scripts/append_sol_event.py`` (agents / shell) or ``scripts/SolEventLog.ps1``
(PowerShell), and ``tests/test_sol_events_hygiene.py`` fails if the file ever
holds a line that is not a JSON object.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


class InvalidEventError(ValueError):
    """The event is not a single JSON object that fits on one line."""


def serialize_event(event: object) -> str:
    """Return the event as one compact JSON line (without the newline)."""
    if isinstance(event, (str, bytes)):
        text = event.decode("utf-8") if isinstance(event, bytes) else event
        try:
            event = json.loads(text)
        except json.JSONDecodeError as error:
            raise InvalidEventError(f"event is not valid JSON: {error}") from error
    if not isinstance(event, Mapping):
        raise InvalidEventError(f"event must be a JSON object, not {type(event).__name__}")
    try:
        line = json.dumps(dict(event), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise InvalidEventError(f"event is not JSON-serializable: {error}") from error
    # json.dumps escapes control characters, so a raw newline can only appear
    # here through a bug; re-parsing proves the line is one JSON object.
    if "\n" in line or "\r" in line or not isinstance(json.loads(line), dict):
        raise InvalidEventError("event does not serialize to a single JSON line")
    return line


def append_event(path: os.PathLike[str] | str, event: object) -> str:
    """Append one validated event line; repair a missing final newline first."""
    line = serialize_event(event)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a+b") as stream:
        stream.seek(0, os.SEEK_END)
        prefix = b""
        if stream.tell() > 0:
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b"\n":
                prefix = b"\n"
            stream.seek(0, os.SEEK_END)
        stream.write(prefix + line.encode("utf-8") + b"\n")
    return line


def invalid_lines(data: bytes) -> list[tuple[int, str]]:
    """Return ``(1-based line, reason)`` for every line that breaks the format."""
    problems: list[tuple[int, str]] = []
    if data.startswith(b"\xef\xbb\xbf"):
        problems.append((1, "UTF-8 byte order mark"))
        data = data[3:]
    if not data:
        return problems
    if not data.endswith(b"\n"):
        problems.append((data.count(b"\n") + 1, "missing trailing newline"))
    for number, raw in enumerate(data.rstrip(b"\n").split(b"\n") if data.strip(b"\n") else [], 1):
        try:
            value: Any = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as error:
            problems.append((number, f"not UTF-8: {error}"))
            continue
        except json.JSONDecodeError as error:
            problems.append((number, f"not JSON: {error}"))
            continue
        if not isinstance(value, dict):
            problems.append((number, f"not a JSON object: {type(value).__name__}"))
    if data.endswith(b"\n\n"):
        problems.append((data.count(b"\n"), "blank line"))
    return problems


def format_problems(problems: Iterable[tuple[int, str]]) -> str:
    return "\n".join(f"line {number}: {reason}" for number, reason in problems)
