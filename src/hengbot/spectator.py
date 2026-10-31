"""Spectator snapshot file for a public viewer (``--spectate-file``).

The bot is the control server's only client, so a viewer cannot read the
game itself.  After each decision the bot writes what it already holds -- the
screen reply its executor observed, the decision's key and reason, a few player
values and the recent messages -- to one JSON file that a separate web page
serves. A due write may request a colour screen through the existing client.
Nothing here is read back by a decision; only already received state and the
public screen are copied (fair play is unchanged).

The file is replaced atomically (``PATH.tmp`` then ``os.replace``) at most once
per 0.25 seconds. Posted decisions also append unthrottled JSONL frames.  A failed write never reaches the bot: it is reported on
stderr at most once per hour and the next decision simply tries again.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from hengbot.control_client import raw_keys_to_macro_notation
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.spectator_tiles import spectator_player, spectator_tile_player, spectator_tiles

# Owner request 2026-10-23: the last 20 messages,
# and one stderr line per hour at most for a failing write.
# Owner decision 2026-10-25 (「0.25秒ごと」): at most one write per 0.25 s (was one per second).
SPECTATE_WRITE_INTERVAL_SECONDS = 0.25
# Compact the complete newest records to half the budget, using atomic replace.
SPECTATE_FRAMES_MAX_BYTES = 16 * 1024 * 1024
SPECTATE_PLAYED_MAX_AGE_SECONDS = 10.0
SPECTATE_BACKLOG_POLL_SECONDS = 0.05
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
    if "visible_monsters" in state or "detected_monsters" in state:
        monsters = []
        known = {monster.index: monster for monster in (
            *snapshot.visible_monsters, *snapshot.detected_monsters)} \
            if snapshot is not None else {}
        listed = set()
        # 視界の外でもテレパシー・感知で見えているものは detected_monsters にある。
        # ゲーム側で視界の一覧と分けてあるが、同じ index は一度だけ載せる。
        for field in ("visible_monsters", "detected_monsters"):
            for row in state.get(field, ()):
                index = row.get("index")
                if index is not None:
                    if index in listed:
                        continue
                    listed.add(index)
                monster = {name: row[name] for name in (
                    "name", "distance", "asleep", "stunned", "confused",
                    "fearful", "friendly", "pet", "speed") if name in row}
                observed = known.get(index)
                if observed is not None:
                    monster["distance"] = observed.distance
                    monster["speed"] = observed.speed
                monster["hp"] = ([row["hp"], row["max_hp"]]
                                 if row.get("hp") is not None and
                                 row.get("max_hp") is not None else None)
                if field == "detected_monsters":
                    monster["sensed"] = "esp" if row.get("esp") else "detected"
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


def spectator_recall_destination(policy, snapshot) -> dict | None:
    """The recall destination the policy pursues and why, or None without one.

    Read only from what the bot already holds: the target and its reason
    code, the dungeon's name from the bot's static dungeon knowledge (omitted
    when it has none) and the arrival floor the bot itself expects
    (``_dungeon_entry_depth`` with ``via_recall=True``).  No decision reads
    this projection.
    """
    dungeon_id = getattr(policy, "_target_dungeon_id", None)
    if dungeon_id is None:
        return None
    destination: dict[str, object] = {"dungeon_id": dungeon_id}
    info = (getattr(policy, "_dungeon_knowledge", None) or {}).get(dungeon_id)
    name = getattr(info, "name", None)
    if name:
        destination["dungeon_name"] = name
    destination["depth"] = policy._dungeon_entry_depth(
        snapshot, dungeon_id, via_recall=True)
    destination["reason"] = getattr(policy, "_target_dungeon_reason", None)
    return destination


SPECTATE_MAGIC_EATER_KINDS = ("staff", "wand", "rod")


def observe_magic_eater_powers(cache: dict, snapshot, now: float | None = None) -> dict:
    """Update the per-life cache of power lists the game displayed to the bot.

    Each entry is a list the executor read from the game's own power list
    screen (``Snapshot.magic_eater_power_list``) plus the game turn of the
    board that followed it.  Nothing is estimated between observations: the
    viewer shows the turn so a stale list is visible.  A different class or
    a game turn going backwards (a new life) clears the cache.  ``now`` (wall
    clock) records when each list was read, the refresh cadence's clock.
    """
    player = snapshot.player
    turn = getattr(snapshot, "turn", 0)
    if (cache.get("class_id") != player.class_id
            or turn < cache.get("turn", turn)):
        cache.clear()
    cache["class_id"], cache["turn"] = player.class_id, turn
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, Mapping) and listed.get("kind") in SPECTATE_MAGIC_EATER_KINDS:
        cache.setdefault("lists", {})[listed["kind"]] = {
            "turn": turn, "rows": [dict(row) for row in listed.get("rows", ())]}
        if now is not None:
            cache.setdefault("observed_at", {})[listed["kind"]] = now
    return cache


def resume_magic_eater_powers(content: Mapping[str, object]) -> dict:
    """The cache a previous bot process of this viewer wrote to spectate.json.

    The soak runner restarts a stopped bot within seconds; without this each
    restart forgot the lists (未確認) and their age.  A new life is still
    told apart by observe_magic_eater_powers (class or game turn backwards).
    """
    # Only a class-16 frame carries the field (SpectatorWriter.observe).
    powers = content.get("magic_eater_powers")
    if not isinstance(powers, Mapping):
        return {}
    lists = {kind: value for kind, value in powers.items()
             if kind in SPECTATE_MAGIC_EATER_KINDS and isinstance(value, Mapping)
             and isinstance(value.get("turn"), int) and isinstance(value.get("rows"), list)}
    if not lists:
        return {}
    observed = content.get("magic_eater_powers_observed_at")
    observed_at = {kind: value for kind, value in (
        observed.items() if isinstance(observed, Mapping) else ())
        if kind in lists and type(value) in (int, float) and math.isfinite(value)}
    return {"class_id": PLAYER_CLASS_MAGIC_EATER,
            "turn": max(value["turn"] for value in lists.values()),
            "lists": {kind: dict(value) for kind, value in lists.items()},
            "observed_at": observed_at}


def magic_eater_refresh_due(cache: Mapping[str, object], now: float,
                            interval_seconds: float) -> bool:
    """A class-16 cache with a kind unread, or read longer ago than the interval."""
    if cache.get("class_id") != PLAYER_CLASS_MAGIC_EATER:
        return False
    observed = cache.get("observed_at", {})
    return any(kind not in observed or now - observed[kind] >= interval_seconds
               for kind in SPECTATE_MAGIC_EATER_KINDS)


def spectator_magic_eater_powers(cache: Mapping[str, object]) -> dict:
    """Viewer field: each type's last observed list, or None (未確認)."""
    lists = cache.get("lists", {})
    return {kind: lists.get(kind) for kind in SPECTATE_MAGIC_EATER_KINDS}


class SpectatorWriter:
    """Atomic snapshot plus bounded, unthrottled frames; I/O fails open."""

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time,
                 stderr=None) -> None:
        self.path = Path(path)
        self.clock = clock
        self.stderr = stderr
        self.frames_path = self.path.with_name("spectate-frames.jsonl")
        self.played_path = self.path.with_name("spectate-played.json")
        self.last_frame = self._resume_frame()
        self.pending_frame: dict | None = None
        self.messages: list[str] = []
        self.last_write: float | None = None
        self.last_error_report: float | None = None
        self.tile_panel_counts: dict[str, int] = {}
        self.magic_eater_powers: dict[str, object] = self._resume_magic_eater_powers()

    def observe(self, snapshot, key: str | None, reason: str | None,
                decision_sequence: int | None,
                screen_value: Mapping[str, object] | None, *,
                state_line: str | None = None, screen_client=None,
                policy=None, append_frame: bool = False,
                defer_frame: bool = False) -> bool:
        """Project a decision; refresh the snapshot at most every 0.25 seconds.

        append_frame requests colours even between snapshot writes. defer_frame
        holds that pre-action projection until the caller confirms a real post.
        Returns True when the compatibility snapshot was replaced by this call.
        """
        if append_frame:
            self.pending_frame = None
        try:
            observe_magic_eater_powers(self.magic_eater_powers, snapshot, self.clock())
        except Exception as error:
            self._report(self.clock(), error)
        self.messages = merge_seen_messages(
            self.messages, getattr(snapshot, "messages", ()) or ()
        )[-SPECTATE_MESSAGE_LINES:]
        now = self.clock()
        snapshot_due = (self.last_write is None or
                        now - self.last_write >= SPECTATE_WRITE_INTERVAL_SECONDS)
        if not snapshot_due and not append_frame:
            return False
        if snapshot_due:
            self.last_write = now
        try:
            if screen_client is not None:
                try:
                    coloured = screen_client.request("screen", term=0, attrs=True)
                except Exception as error:
                    if not append_frame:
                        raise
                    self._report(now, error)
                    coloured = None
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
                "player": spectator_player({"race_id": player.race_id,
                                             "class_id": player.class_id}),
            }
            if player.class_id == PLAYER_CLASS_MAGIC_EATER:
                content["magic_eater_powers"] = spectator_magic_eater_powers(
                    self.magic_eater_powers)
                content["magic_eater_powers_observed_at"] = dict(
                    self.magic_eater_powers.get("observed_at", {}))
            content["tile_player"] = spectator_tile_player(
                player.class_id, getattr(policy, "_spectator_sex_title", None))
            if policy is not None:
                destination = spectator_recall_destination(policy, snapshot)
                if destination is not None:
                    content["recall_destination"] = destination
                # getattr also handles checkpoints made before this display cache.
                expected = getattr(policy, "_spectator_melee_expected", None)
                if expected is not None:
                    per_round = expected["per_round"]
                    content["melee_expected"] = {
                        "per_round": per_round,
                        "total": sum(per_round) if per_round is not None else None,
                        "stale": sorted(
                            (item.slot, item.name) for item in snapshot.equipment
                            if item.slot in ("main_hand", "sub_hand")
                        ) != sorted(
                            (slot, name) for slot, name in expected["equipment"]
                            if slot in ("main_hand", "sub_hand")
                        ),
                        "turn": expected["turn"],
                    }
            screen = spectator_screen(screen_value)
            if screen is not None:
                content["screen"] = screen
            content["messages"] = list(self.messages)
            temporary = self.path.with_name(self.path.name + ".tmp")
            if state_line is not None:
                state = json.loads(state_line)
                content.update(spectator_details(state, snapshot))
                content["player"] = spectator_player(state.get("player", {}))
                if screen is not None:
                    tiles = spectator_tiles(state, screen, panel_counts=self.tile_panel_counts)
                    if tiles is not None:
                        content["tiles"] = tiles
            # The two outputs fail independently; a broken compatibility snapshot
            # must not suppress frames (or vice versa).
            if append_frame:
                self.pending_frame = content
                if not defer_frame:
                    self.commit_frame()
            if snapshot_due:
                temporary.write_text(
                    json.dumps(content, ensure_ascii=False), encoding="utf-8", newline="\n")
                os.replace(temporary, self.path)
        except Exception as error:
            self._report(now, error)
            return False
        return snapshot_due

    def magic_eater_refresh_due(self, interval_seconds: float) -> bool:
        return magic_eater_refresh_due(self.magic_eater_powers, self.clock(), interval_seconds)

    def _resume_magic_eater_powers(self) -> dict:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return resume_magic_eater_powers(content) if isinstance(content, Mapping) else {}

    def commit_frame(self) -> None:
        """Publish the pre-action screen only after the action was posted."""
        content, self.pending_frame = self.pending_frame, None
        if content is not None:
            try:
                self._append_frame(content)
            except Exception as error:
                self._report(content["time"], error)

    def _resume_frame(self) -> int:
        """Resume numbering across bot restarts without scanning a large log."""
        try:
            with self.frames_path.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - SPECTATE_FRAMES_MAX_BYTES))
                tail = stream.read()
            # A torn last append is ignored; only complete JSONL rows count.
            for line in reversed(tail.split(b"\n")[:-1]):
                try:
                    value = json.loads(line).get("frame")
                    if type(value) is int and value >= 0:
                        return value
                except (ValueError, AttributeError, UnicodeError):
                    continue
        except OSError:
            pass
        return 0

    def _append_frame(self, content: dict) -> None:
        number = self.last_frame + 1
        row = (json.dumps(dict(content, frame=number), ensure_ascii=False)
               + "\n").encode("utf-8")
        # An exceptional oversized screen cannot make the bounded file unbounded.
        if len(row) > SPECTATE_FRAMES_MAX_BYTES:
            raise ValueError("spectator frame exceeds file budget")
        try:
            size = self.frames_path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size + len(row) > SPECTATE_FRAMES_MAX_BYTES:
            # Compact BEFORE appending. If replace fails (e.g. a Windows reader
            # holds the file open), do not grow a file we cannot compact.
            keep = max(0, SPECTATE_FRAMES_MAX_BYTES // 2 - len(row))
            tail = b""
            if keep:
                with self.frames_path.open("rb") as stream:
                    stream.seek(max(0, size - keep))
                    if stream.tell():
                        stream.readline()
                    tail = stream.read()
                # A previous failed write may have left a torn final record.
                tail = tail[:tail.rfind(b"\n") + 1]
            temporary = self.frames_path.with_name(self.frames_path.name + ".tmp")
            temporary.write_bytes(tail + row)
            os.replace(temporary, self.frames_path)
        else:
            with self.frames_path.open("ab+") as stream:
                if size:
                    stream.seek(-1, 2)
                    if stream.read(1) != b"\n":
                        stream.seek(max(0, size - SPECTATE_FRAMES_MAX_BYTES))
                        tail = stream.read()
                        end = tail.rfind(b"\n")
                        stream.truncate(size - len(tail) + end + 1 if end >= 0 else 0)
                stream.write(row)
        self.last_frame = number

    def backlog_full(self, maximum: int) -> bool:
        """Fail open on absent, invalid or expired server acknowledgements."""
        if maximum <= 0:
            return False
        try:
            played = json.loads(self.played_path.read_text(encoding="utf-8"))
            frame, stamp = played["frame"], played["time"]
            if type(frame) is not int or frame < 0 or frame > self.last_frame:
                return False
            if type(stamp) not in (int, float) or not math.isfinite(stamp):
                return False
            age = self.clock() - stamp
            if age < 0 or age > SPECTATE_PLAYED_MAX_AGE_SECONDS:
                return False
            return self.last_frame - frame >= maximum
        except (OSError, ValueError, KeyError, TypeError, OverflowError):
            return False

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
