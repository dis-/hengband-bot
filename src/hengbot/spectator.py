"""Spectator snapshot file for a public viewer (``--spectate-file``).

The bot is the control server's only client, so a viewer cannot read the
game itself.  After each decision the bot writes what it already holds -- the
screen reply its executor observed, the decision's key and reason, a few player
values and the recent messages -- to one JSON file that a separate web page
serves. A due write may request a colour screen through the existing client.
Nothing here is read back by a decision; only already received state and the
public screen are copied (fair play is unchanged).

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

# Owner request 2026-10-23: the last 20 messages,
# and one stderr line per hour at most for a failing write.
# Owner decision 2026-10-25 (「0.25秒ごと」): at most one write per 0.25 s (was one per second).
SPECTATE_WRITE_INTERVAL_SECONDS = 0.25
SPECTATE_MESSAGE_LINES = 20
SPECTATE_ERROR_REPORT_INTERVAL_SECONDS = 3600.0
# Fields of the control server's screen reply (bot-screen.cpp, handle_screen_request)
# that describe the cursor and the input wait rather than what is on screen.
SPECTATE_SCREEN_FIELDS_NOT_SHOWN = ("cursor", "input_context", "term")


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
    """The viewer's copy of one screen reply, or None without a reply.

    The reply is passed through as the game sent it (width, height, the text
    rows, and attrs when the bot asked for them) minus the fields that only
    describe the bot's own input wait.  Nothing here reads the rows: the
    viewer shows them, the bot does not infer anything from this copy.
    """
    if not isinstance(screen_value, Mapping):
        return None
    return {
        field: value for field, value in screen_value.items()
        if field not in SPECTATE_SCREEN_FIELDS_NOT_SHOWN
    }


def spectator_details(state: Mapping[str, object], snapshot=None) -> dict:
    """Small viewer-only projection; omitted emitter fields stay omitted."""
    details = {}
    for field, columns in (("equipment", ("slot", "name")),
                           ("inventory", ("slot", "name", "count"))):
        if field in state:
            details[field] = [
                {name: row[name] for name in columns if name in row}
                for row in state[field]
            ]
    if "visible_monsters" in state:
        monsters = []
        known = {monster.index: monster for monster in snapshot.visible_monsters} \
            if snapshot is not None else {}
        for row in state["visible_monsters"]:
            monster = {name: row[name] for name in (
                "name", "distance", "asleep", "stunned", "confused",
                "fearful", "friendly", "pet", "speed") if name in row}
            observed = known.get(row.get("index"))
            if observed is not None:
                monster["distance"] = observed.distance
                monster["speed"] = observed.speed
            monster["hp"] = ([row["hp"], row["max_hp"]]
                             if row.get("hp") is not None and
                             row.get("max_hp") is not None else None)
            monsters.append(monster)
        details["monsters"] = sorted(
            monsters, key=lambda row: row.get("distance", float("inf")))
    player = state.get("player", {})
    if "speed" in player:
        details["speed"] = player["speed"]
    if "melee" in player:
        melee = dict(player["melee"])
        for row in state.get("equipment", []):
            slot = row.get("slot")
            dice = row.get("damage_dice", {})
            if slot in ("main_hand", "sub_hand") and \
                    "num" in dice and "sides" in dice:
                melee[slot + "_dice"] = "{num}d{sides}".format(**dice)
        details["melee"] = melee
    abilities = {}
    for source, target in (("ability_sources", "sources"),
                           ("immunities", "immunities"),
                           ("vulnerabilities", "vulnerabilities")):
        if source in player:
            abilities[target] = {
                name: [source for source, enabled in sources.items() if enabled is True]
                for name, sources in player[source].items()
                if any(enabled is True for enabled in sources.values())
            }
    if abilities:
        details["abilities"] = abilities
    status = {}
    for source, target in (("status_bar", "bar"), ("speed_display", "speed")):
        if source in player:
            status[target] = player[source]
    if "status" in player:
        flags = player["status"]
        status["flags"] = [name for name, enabled in flags.items() if enabled is True]
        for source, target in (("cut_rank_name", "cut"), ("stun_rank_name", "stun")):
            if source in flags:
                status[target] = flags[source]
    if status:
        details["status"] = status
    return details


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
                screen_value: Mapping[str, object] | None, *,
                state_line: str | None = None, screen_client=None) -> bool:
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
        try:
            if screen_client is not None:
                coloured = screen_client.request("screen", term=0, attrs=True)
                if coloured is not None:
                    screen_value = coloured
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
            if state_line is not None:
                content.update(spectator_details(json.loads(state_line), snapshot))
            temporary.write_text(
                json.dumps(content, ensure_ascii=False), encoding="utf-8", newline="\n")
            os.replace(temporary, self.path)
        except Exception as error:
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
