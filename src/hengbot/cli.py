from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Iterable

from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy


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

# Loop / stuck detection. If the character stays confined to a handful of tiles
# on a single floor for this many consecutive decisions, it is looping — an
# exploration oscillation the policy's own anti-stuck guards (visit penalty,
# probe, livelock breaker) could not break (e.g. a 2-cycle between two tiles that
# gate the only routes to both frontiers, where the keys alternate so the
# same-key livelock guard never trips). Rather than flail forever, STOP the bot
# so the situation can be investigated from the preserved game state.
LOOP_WINDOW = 40
LOOP_MAX_DISTINCT = 4


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
    parser.add_argument(
        "--stall-timeout",
        type=float,
        default=1.5,
        help="seconds without a new snapshot before nudging a stuck prompt (0 disables)",
    )
    args = parser.parse_args(argv)

    if args.list_windows:
        from hengbot.input_windows import list_windows

        for window in list_windows():
            line = f"{window.hwnd}\tpid={window.process_id}\tclass={window.class_name}\ttitle={window.title}"
            encoding = sys.stdout.encoding or "utf-8"
            print(line.encode(encoding, errors="replace").decode(encoding))
        return 0

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
                snapshot = parse_snapshot(json.loads(line))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                print(f"invalid snapshot: {exc}", file=sys.stderr)
                return 2
            key = policy.choose_key(snapshot)
            print(key, flush=True)
            if not send(key):
                return 3
            return 0
        return 1

    return _run_follow(args, policy, send)


def _run_follow(args, policy, send) -> int:
    path = args.state_file
    while not path.exists():
        time.sleep(args.poll_interval)

    with path.open("r", encoding="utf-8") as file:
        file.seek(0, 2)
        pending = ""
        last_activity = time.monotonic()
        quiet_ok_until = 0.0  # suppress the nudge while a rest is expected to run
        nudge_streak = 0  # consecutive nudges with no snapshot in between
        # (floor_key, y, x) of the last LOOP_WINDOW decisions, for loop detection.
        recent_cells: deque[tuple] = deque(maxlen=LOOP_WINDOW)
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
                # re-emit the same board and are handled by the policy's own
                # livelock breaker, so we deliberately do NOT skip duplicates here.
                snapshot = _newest_snapshot(complete_lines)
                if snapshot is not None:
                    # A snapshot means the game is alive and awaiting a command.
                    nudge_streak = 0
                    key = policy.choose_key(snapshot)
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
                    # Searching a dead-end for a secret door, and fighting/drinking
                    # in place during combat, all hold position but are NOT
                    # exploration oscillations — don't let them trip the guard (it
                    # is meant to catch a stuck sweep, not abandon a long fight).
                    if policy.last_reason == "search" or policy.last_reason == "melee" or policy.last_reason.startswith("item:"):
                        continue
                    pos = snapshot.player.position
                    recent_cells.append((snapshot.floor_key, pos.y, pos.x))
                    if _is_looping(recent_cells):
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

            # The emitter truncates the JSONL at game start. If we opened the file
            # and seeked to its end BEFORE that truncation, our read offset is now
            # stranded past the new (smaller) EOF: we would read nothing forever
            # and then falsely declare death. Detect the shrink and re-read from
            # the new start (drain-to-newest still picks the latest snapshot).
            try:
                if args.state_file.stat().st_size < file.tell():
                    file.seek(0)
                    pending = ""
                    nudge_streak = 0
                    continue
            except OSError:
                pass

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
                if send(NUDGE_KEY):
                    print("<esc>", flush=True)
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
    """True when the last LOOP_WINDOW decisions stayed on ONE floor and visited at
    most LOOP_MAX_DISTINCT distinct tiles — an unbroken exploration oscillation.

    Needs a full window so a genuinely small room or a brief back-and-forth while
    routing does not trip it; a real sweep visits far more than a few tiles over
    this many moves. Rest is bounded well under the window, and combat that pins
    the player to one spot for this long without resolving is itself a stuck state
    worth stopping on.
    """
    if len(recent_cells) < LOOP_WINDOW:
        return False
    floors = {c[0] for c in recent_cells}
    if len(floors) != 1:
        return False
    cells = {(c[1], c[2]) for c in recent_cells}
    return len(cells) <= LOOP_MAX_DISTINCT


def _newest_snapshot(complete_lines: list[str]):
    """Return the most recent parseable snapshot in a read batch, or ``None``.

    Only the newest snapshot matters: older lines in the same read are stale
    command prompts a fast monster raced past (or exact duplicates it emitted for
    one turn), and answering each would post one key per stale board — desyncing
    our key stream from the game by a step. Parsing walks newest-first and stops
    at the first good line; a malformed tail line simply falls through to the one
    before it.
    """
    for line in reversed(complete_lines):
        if not line.strip():
            continue
        try:
            return parse_snapshot(json.loads(line))
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
