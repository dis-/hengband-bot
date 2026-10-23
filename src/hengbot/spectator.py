"""Spectator snapshot file for a public viewer (``--spectate-file``).

The bot is the control server's only client, so a viewer cannot read the
game itself.  After each decision the bot writes what it already holds -- the
screen reply its executor observed, the decision's key and reason, a few player
values and the recent messages -- to one JSON file that a separate web page
serves.  Nothing here is read back by a decision, and nothing asks the game
for anything (fair play is unchanged: only what the bot already saw).

The file is replaced atomically (``PATH.tmp`` then ``os.replace``) at most once
per wall-clock second.  A failed write never reaches the bot: it is reported on
stderr at most once per hour and the next decision simply tries again.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from hengbot.control_client import raw_keys_to_macro_notation

# Owner request 2026-10-23: at most one write per second, the last 20 messages,
# and one stderr line per hour at most for a failing write.
SPECTATE_WRITE_INTERVAL_SECONDS = 1.0
SPECTATE_MESSAGE_LINES = 20
SPECTATE_ERROR_REPORT_INTERVAL_SECONDS = 3600.0


def printable_key(key: str | None) -> str:
    """The key in the control server's macro notation (``\\e``, ``\\r``, ``^X``)."""
    if not key:
        return ""
    try:
        return raw_keys_to_macro_notation(key)
    except ValueError:
        return key.encode("unicode_escape").decode("ascii")


def merge_seen_messages(seen: Sequence[str], new: Sequence[str]) -> list[str]:
    """Append the lines of ``new`` the bot has not seen yet, oldest first.

    The JSONL output carries only the lines added since the previous snapshot,
    while the control server's state carries the recent history (both oldest
    first).  The longest end of ``seen`` that ``new`` repeats up to some line
    marks what is already known; only the lines after it are new.
    """
    seen, new = list(seen), list(new)
    for end in range(len(new), 0, -1):
        overlap = min(len(seen), end)
        if overlap and new[end - overlap:end] == seen[len(seen) - overlap:]:
            return seen + new[end:]
    return seen + new


def spectator_screen(screen_value: Mapping[str, object] | None) -> dict | None:
    """The viewer's copy of one screen reply, or None without a usable reply."""
    if not isinstance(screen_value, Mapping):
        return None
    lines = screen_value.get("lines")
    if not isinstance(lines, list):
        return None
    screen = {
        "width": screen_value.get("width"),
        "height": screen_value.get("height"),
        "lines": list(lines),
    }
    if "attrs" in screen_value:
        screen["attrs"] = screen_value["attrs"]
    return screen


class SpectatorWriter:
    """Throttled, atomic, never-raising writer of the spectator snapshot."""

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time,
                 stderr=None) -> None:
        self.path = Path(path)
        self.clock = clock
        self.stderr = stderr
        self.messages: list[str] = []
        self.last_write: float | None = None
        self.last_error_report: float | None = None

    def observe(self, snapshot, key: str | None, reason: str | None,
                decision_sequence: int | None,
                screen_value: Mapping[str, object] | None) -> bool:
        """Record one decision; write the file when a second has passed.

        Returns True when the file was replaced by this call.
        """
        self.messages = merge_seen_messages(
            self.messages, getattr(snapshot, "messages", ()) or ()
        )[-SPECTATE_MESSAGE_LINES:]
        now = self.clock()
        if self.last_write is not None and \
                now - self.last_write < SPECTATE_WRITE_INTERVAL_SECONDS:
            return False
        self.last_write = now
        player = snapshot.player
        content: dict[str, object] = {
            "time": now,
            "decision_sequence": decision_sequence,
            "key": printable_key(key),
            "reason": reason,
            "level": player.level,
            "depth": snapshot.dungeon_level,
            "dungeon": snapshot.floor_key[0],
            "hp": [player.hp, player.max_hp],
        }
        screen = spectator_screen(screen_value)
        if screen is not None:
            content["screen"] = screen
        content["messages"] = list(self.messages)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(
                json.dumps(content, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.path)
        except (OSError, TypeError, ValueError) as error:
            self._report(now, error)
            return False
        return True

    def _report(self, now: float, error: BaseException) -> None:
        if self.last_error_report is not None and \
                now - self.last_error_report < SPECTATE_ERROR_REPORT_INTERVAL_SECONDS:
            return
        self.last_error_report = now
        stream = self.stderr if self.stderr is not None else sys.stderr
        try:
            print(f"spectate file write failed: {self.path}: {error}",
                  file=stream, flush=True)
        except (OSError, ValueError):
            pass
