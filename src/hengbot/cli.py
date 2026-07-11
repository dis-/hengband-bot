from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Iterable

from hengbot.model import MissingMonraceKnowledgeError, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import PACK_CAPACITY, ConservativePolicy


# Character posted to the window to dismiss a message / "-more-" prompt that the
# game shows without emitting a new bot snapshot (e.g. the level feeling printed
# right after descending). Escape (0x1B) clears any such prompt and is a harmless
# no-op if the game has already returned to the command loop.
NUDGE_KEY = "\x1b"

# After issuing a rest, the game runs many turns without emitting a snapshot;
# hold off the stall nudge this long so it does not cut the rest short.
REST_STALL_GRACE = 20.0

# When the character dies, the game leaves the command loop for the tombstone /
# death-info / high-score screens (close_game) and never emits another snapshot;
# Escape nudges cannot revive it. After this many fruitless nudges in a row we
# treat it as a terminal screen and drive the shutdown so the game quit()s.
TERMINAL_NUDGE_LIMIT = 8
# Keys that march through close_game: Escape clears the tombstone and aborts the
# death-info dump, "n" answers the NO_ESCAPE "stand by for score registration?"
# prompt, Return confirms anything else. Repeated to cover every screen.
DEATH_EXIT_KEYS = ("\x1b", "n", "\r")
DEATH_EXIT_ROUNDS = 8

# Every tenth level Hengband blocks outside the command loop and asks for a stat
# (a-f), then confirmation; the screen ignores Escape and no JSON snapshot is
# emitted while it is up. After two harmless Esc nudges, alternate the stat
# choice (Strength, for the warrior bot) with a confirm — alternating retries
# both keys, so a single lost keystroke cannot strand the game there. The gate
# accepts levels ending in 8 or 9: one strong kill can jump two levels (8→10),
# which still lands on the stat screen while our last snapshot said clvl 8.
LEVEL_UP_STAT_CHOICE = "a"
LEVEL_UP_RECOVERY_START = 2

# Loop / stuck detection. If the character stays confined to a handful of tiles
# on a single floor for this many consecutive decisions, it is looping — an
# exploration oscillation the policy's own anti-stuck guards (visit penalty,
# probe, livelock breaker) could not break (e.g. a 2-cycle between two tiles that
# gate the only routes to both frontiers, where the keys alternate so the
# same-key livelock guard never trips). Rather than flail forever, STOP the bot
# so the situation can be investigated from the preserved game state.
LOOP_WINDOW = 40
LOOP_MAX_DISTINCT = 4
# The emitter can present the exact same command state several times while a
# posted Windows key is still waiting to be consumed. Sending on every copy
# builds a large input backlog and makes the loop detector judge stale positions.
# A genuinely rejected move still needs retries so the policy can break out;
# throttle exact duplicates instead of dropping them forever.
DUPLICATE_RETRY_SECONDS = 2.0

# Decision reasons that legitimately hold the player on one tile for many
# consecutive snapshots and so must NOT feed the loop detector: searching a
# dead-end, meleeing in place, and waiting out a Word of Recall countdown
# (~15-35 stationary turns — enough to trip a ≤4-cell window by itself).
STATIONARY_REASONS = frozenset(
    {"search", "melee", "return:wait-recall", "town:wait-recall"}
)


def _objective_for_reason(reason: str) -> str:
    if reason == "loop-detected":
        return "Stopped for loop investigation"
    prefix = reason.split(":", 1)[0]
    if prefix in {"flee", "unseen", "summoner", "item"}:
        return "Survive and disengage"
    if prefix in {"melee", "hunt"}:
        return "Fight visible threats"
    if prefix == "return":
        return "Return to town"
    if prefix in {"shop", "home", "town", "identify", "equipment"}:
        return "Town maintenance and resupply"
    if prefix == "fundraise":
        return "Raise funds on Yeek cave level 1"
    if prefix == "victory":
        return "Collect conquest drops and return"
    if reason in {"pickup", "seek-loot"}:
        return "Collect visible floor items"
    if prefix in {"descend", "seek-downstairs", "approach-descent", "clear-descent"}:
        return "Reach the next dungeon level"
    if prefix in {"explore", "probe", "search", "breakout", "stuck"}:
        return "Explore and break out of dead ends"
    if prefix in {"rest", "eat", "wield-light", "refill-light"}:
        return "Recover and maintain supplies"
    if prefix in {"confused", "wait"}:
        return "Wait safely"
    return "Continue conservative progression"


def _decision_record(snapshot, key: str, reason: str) -> dict:
    player = snapshot.player
    active_status = [
        name
        for name in (
            "blind",
            "confused",
            "afraid",
            "poisoned",
            "stunned",
            "cut",
            "paralyzed",
            "hallucinated",
        )
        if getattr(player, name)
    ]
    return {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "turn": snapshot.turn,
        "objective": _objective_for_reason(reason),
        "reason": reason,
        "key": key,
        "floor": {
            "dungeon_id": snapshot.floor_key[0],
            "level": snapshot.floor_key[1],
        },
        "position": {"y": player.position.y, "x": player.position.x},
        "player": {
            "level": player.level,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "mp": player.mp,
            "max_mp": player.max_mp,
            "gold": player.gold,
            "food_state": player.food_state,
            "status": active_status,
        },
        "inventory": {
            "used": len(snapshot.inventory),
            "free": max(0, PACK_CAPACITY - len(snapshot.inventory)),
        },
        "visible_hostiles": sum(monster.hostile for monster in snapshot.visible_monsters),
        "store_type": snapshot.store.store_type if snapshot.store is not None else None,
    }


def _write_decision(path: Path | None, snapshot, key: str, reason: str) -> None:
    if path is None:
        return
    try:
        with path.open("a", encoding="utf-8") as file:
            json.dump(_decision_record(snapshot, key, reason), file, ensure_ascii=False)
            file.write("\n")
    except OSError as exc:
        print(f"failed to write decision log: {exc}", file=sys.stderr)


def _rewind_if_truncated(file, path: Path) -> bool:
    """Rewind a tail reader after the emitter rolls over its JSONL file."""
    try:
        if path.stat().st_size >= file.tell():
            return False
        file.seek(0)
        return True
    except OSError:
        return False


def _duplicate_snapshot_ready(
    line: str, previous_line: str | None, elapsed: float
) -> bool:
    return line != previous_line or elapsed >= DUPLICATE_RETRY_SECONDS


def _stall_recovery_key(nudge_streak: int, last_player_level: int | None) -> tuple[str, str]:
    if (
        last_player_level is not None
        and last_player_level % 10 in (8, 9)
        and nudge_streak >= LEVEL_UP_RECOVERY_START
    ):
        if (nudge_streak - LEVEL_UP_RECOVERY_START) % 2 == 0:
            return LEVEL_UP_STAT_CHOICE, f"<level-stat:{LEVEL_UP_STAT_CHOICE}>"
        return "y", "<level-stat:y>"
    return NUDGE_KEY, "<esc>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument(
        "--decision-log",
        type=Path,
        help="append structured policy decisions for an external live viewer",
    )
    parser.add_argument(
        "--monrace-definitions",
        type=Path,
        help="path to Hengband's lib/edit/MonraceDefinitions.jsonc",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument("--send-to-window", action="store_true")
    parser.add_argument("--window-title")
    parser.add_argument("--window-title-contains", action="store_true")
    parser.add_argument("--window-class", default="ANGBAND")
    parser.add_argument("--window-pid", type=int)
    parser.add_argument("--list-windows", action="store_true")
    parser.add_argument(
        "--stall-timeout",
        type=float,
        default=1.5,
        help="seconds without a new snapshot before nudging a stuck prompt (0 disables)",
    )
    args = parser.parse_args(argv)

    if args.decision_log is not None and not args.once:
        try:
            args.decision_log.parent.mkdir(parents=True, exist_ok=True)
            args.decision_log.write_text("", encoding="utf-8")
        except OSError as exc:
            print(f"failed to initialize decision log: {exc}", file=sys.stderr)
            return 2

    if args.list_windows:
        from hengbot.input_windows import list_windows

        for window in list_windows():
            line = f"{window.hwnd}\tpid={window.process_id}\tclass={window.class_name}\ttitle={window.title}"
            encoding = sys.stdout.encoding or "utf-8"
            print(line.encode(encoding, errors="replace").decode(encoding))
        return 0

    monrace_path = find_monrace_definitions(args.state_file, args.monrace_definitions)
    if monrace_path is None:
        print("MonraceDefinitions.jsonc was not found", file=sys.stderr)
        return 2
    else:
        try:
            monrace_knowledge = load_monrace_knowledge(monrace_path)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid monster definitions: {exc}", file=sys.stderr)
            return 2

    def send(key: str) -> bool:
        if not args.send_to_window:
            return True
        try:
            from hengbot.input_windows import send_key_to_window

            # A decision may be a multi-key macro (e.g. "qf" = quaff item f). Post
            # each key in turn; the small gap lets the game raise its item-select
            # prompt before the follow-up letter arrives so it is not flushed.
            multi = len(key) > 1
            for char in key:
                send_key_to_window(
                    char,
                    args.window_title,
                    contains=args.window_title_contains,
                    class_name=args.window_class,
                    process_id=args.window_pid,
                )
                if multi:
                    time.sleep(0.05)
            return True
        except RuntimeError as exc:
            print(f"failed to send key: {exc}", file=sys.stderr)
            return False

    policy = ConservativePolicy()

    if args.once:
        for line in _read_last_line(args.state_file):
            if not line.strip():
                continue
            try:
                snapshot = parse_snapshot(json.loads(line), monrace_knowledge)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                print(f"invalid snapshot: {exc}", file=sys.stderr)
                return 2
            key = policy.choose_key(snapshot)
            _write_decision(args.decision_log, snapshot, key, policy.last_reason)
            print(key, flush=True)
            if not send(key):
                return 3
            return 0
        return 1

    try:
        return _run_follow(args, policy, send, monrace_knowledge)
    except MissingMonraceKnowledgeError as exc:
        # The definitions file we loaded does not match the running game (e.g. a
        # different lib/ was resolved). Fail fast but CLEANLY — a raw traceback
        # here would leave the game blocked with no hint of what to fix.
        print(
            f"monster definitions mismatch: {exc}; "
            "pass --monrace-definitions with the lib/edit the game actually loads",
            file=sys.stderr,
        )
        return 2


def _run_follow(args, policy, send, monrace_knowledge) -> int:
    path = args.state_file
    while not path.exists():
        time.sleep(args.poll_interval)

    initial_snapshot = _newest_snapshot(
        list(_read_last_line(path)), monrace_knowledge
    )
    if initial_snapshot is not None:
        policy.prime(initial_snapshot)
    # errors="replace": a poll can catch the emitter mid-write inside a multibyte
    # character (Japanese monster names); a strict read would raise
    # UnicodeDecodeError and kill the loop. Replacement characters at a torn
    # boundary at worst spoil that one line, and drain-to-newest skips past it.
    with path.open("r", encoding="utf-8", errors="replace") as file:
        file.seek(0, 2)
        pending = ""
        last_activity = time.monotonic()
        quiet_ok_until = 0.0  # suppress the nudge while a rest is expected to run
        nudge_streak = 0  # consecutive nudges with no snapshot in between
        last_player_level = initial_snapshot.player.level if initial_snapshot is not None else None
        # (floor_key, y, x) of the last LOOP_WINDOW decisions, for loop detection.
        recent_cells: deque[tuple] = deque(maxlen=LOOP_WINDOW)
        last_decision_line: str | None = None
        last_decision_at = 0.0
        while True:
            chunk = file.read()
            if chunk:
                complete_lines, pending = _split_complete_lines(pending + chunk)
                # Act ONLY on the newest complete snapshot in this batch. The game
                # emits a snapshot then blocks on request_command, so the file's
                # newest line is ALWAYS the current board the game is waiting on;
                # any older lines in the same read are prompts a fast monster raced
                # us past. The old code answered every line, posting one key per
                # stale board, so the key stream lagged the game by a step and
                # "step onto the monster" (an attack) degraded into a side-step —
                # a speed-118 archer shot a full-HP character to death while it
                # merely circled the archer, whose HP never dropped. Acting on the
                # newest line keeps every key matched to the live board and is
                # self-healing: even after a stray desync the next decision re-syncs
                # to the current state. Rejected moves (wall/door bumps) still
                # re-emit the same board and are retried at a bounded interval so
                # the policy's livelock breaker can act without flooding the
                # Windows input queue.
                entry = _newest_snapshot_entry(complete_lines, monrace_knowledge)
                if entry is not None:
                    snapshot, snapshot_line = entry
                    # A snapshot means the game is alive and awaiting a command.
                    nudge_streak = 0
                    last_player_level = snapshot.player.level
                    now = time.monotonic()
                    last_activity = now
                    if not _duplicate_snapshot_ready(
                        snapshot_line,
                        last_decision_line,
                        now - last_decision_at,
                    ):
                        continue
                    last_decision_line = snapshot_line
                    last_decision_at = now
                    key = policy.choose_key(snapshot)
                    _write_decision(args.decision_log, snapshot, key, policy.last_reason)
                    print(key, flush=True)
                    send(key)
                    last_activity = time.monotonic()
                    # A rest runs many turns emitting no snapshot; give it room so
                    # the stall nudge does not immediately disturb it.
                    if key.startswith("R"):
                        quiet_ok_until = last_activity + REST_STALL_GRACE
                    # Loop detection: confined to a few tiles on one floor for a
                    # long stretch means the policy is stuck oscillating. Stop so
                    # the cause can be investigated rather than looping forever.
                    # Shopping legitimately pins us to the store tile for many
                    # decisions (one per item bought), so it must not count.
                    if snapshot.store is not None:
                        recent_cells.clear()
                        continue
                    # Searching a dead-end for a secret door, fighting/drinking in
                    # place during combat, and deliberately waiting out a Word of
                    # Recall countdown all hold position but are NOT exploration
                    # oscillations — don't let them trip the guard (it is meant to
                    # catch a stuck sweep, not abandon a long fight or stop the bot
                    # in the middle of a safe recall home). Recall takes ~15-35
                    # turns of standing still, easily enough to trip a ≤4-cell
                    # window on its own.
                    if (
                        policy.last_reason in STATIONARY_REASONS
                        or policy.last_reason.startswith("item:")
                    ):
                        continue
                    pos = snapshot.player.position
                    recent_cells.append((snapshot.floor_key, pos.y, pos.x))
                    if _is_looping(recent_cells):
                        _write_decision(
                            args.decision_log, snapshot, "", "loop-detected"
                        )
                        cells = sorted({(c[1], c[2]) for c in recent_cells})
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} turn={snapshot.turn} "
                            f"confined to {cells} over {LOOP_WINDOW} decisions; stopping the bot "
                            f"for investigation",
                            flush=True,
                        )
                        print(
                            f"loop detected at floor={snapshot.floor_key} cells={cells}; "
                            f"stopping bot (game left running)",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 0
                continue

            # The emitter truncates the JSONL at game start and when it reaches
            # its size limit. Rewind after either shrink so the reader is not
            # stranded beyond the new EOF.
            if _rewind_if_truncated(file, args.state_file):
                pending = ""
                nudge_streak = 0
                continue

            # No new snapshot. If the game has gone quiet for too long it is
            # probably blocked on a message/"-more-" prompt that emits no
            # snapshot; nudge it with Escape to get back to the command loop.
            now = time.monotonic()
            if (
                args.send_to_window
                and args.stall_timeout > 0
                and now - last_activity > args.stall_timeout
                and now >= quiet_ok_until
            ):
                recovery_key, recovery_marker = _stall_recovery_key(
                    nudge_streak, last_player_level
                )
                if send(recovery_key):
                    print(recovery_marker, flush=True)
                last_activity = now
                nudge_streak += 1
                # Nudges that never bring back a snapshot mean a terminal screen
                # (the character died): drive close_game to completion so the
                # game quit()s, then exit the bot.
                if nudge_streak >= TERMINAL_NUDGE_LIMIT and args.send_to_window:
                    print("<dead>", flush=True)
                    for _ in range(DEATH_EXIT_ROUNDS):
                        for exit_key in DEATH_EXIT_KEYS:
                            send(exit_key)
                            time.sleep(0.3)
                    return 0

            time.sleep(args.poll_interval)


def _is_looping(recent_cells) -> bool:
    """True for a confined single-floor oscillation or rapid two-floor ping-pong.

    Needs a full window so a genuinely small room or a brief back-and-forth while
    routing does not trip it. A normal floor change happens once; a stair loop
    alternates between two floors on nearly every decision.
    """
    if len(recent_cells) < LOOP_WINDOW:
        return False
    floors = {c[0] for c in recent_cells}
    if len(floors) == 1:
        cells = {(c[1], c[2]) for c in recent_cells}
        return len(cells) <= LOOP_MAX_DISTINCT
    if len(floors) != 2:
        return False

    states = set(recent_cells)
    floor_transitions = sum(
        previous[0] != current[0]
        for previous, current in zip(recent_cells, list(recent_cells)[1:])
    )
    return (
        len(states) <= LOOP_MAX_DISTINCT
        and floor_transitions >= LOOP_WINDOW // 2
    )


def _newest_snapshot(
    complete_lines: list[str], monrace_knowledge=None
):
    """Return the most recent parseable snapshot in a read batch, or ``None``.

    Only the newest snapshot matters: older lines in the same read are stale
    command prompts a fast monster raced past (or exact duplicates it emitted for
    one turn), and answering each would post one key per stale board — desyncing
    our key stream from the game by a step. Parsing walks newest-first and stops
    at the first good line; a malformed tail line simply falls through to the one
    before it.
    """
    entry = _newest_snapshot_entry(complete_lines, monrace_knowledge)
    return entry[0] if entry is not None else None


def _newest_snapshot_entry(
    complete_lines: list[str], monrace_knowledge=None
):
    """Return the newest parseable snapshot together with its exact JSONL line."""
    for line in reversed(complete_lines):
        if not line.strip():
            continue
        try:
            return parse_snapshot(json.loads(line), monrace_knowledge), line
        except MissingMonraceKnowledgeError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid snapshot: {exc}", file=sys.stderr)
    return None


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
