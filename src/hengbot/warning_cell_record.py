"""The floor's weapon-warning cells, carried across a bot restart.

The cells a warning prompt was refused on (``_warning_refused_cells``, the monster's warning
latched by ``trap_warning.note_warned``) and the trap warnings being answered
(``_trap_warning_cells``, the cell and its searches spent) lived in the process only.  The game
does not ask twice in a row: warning.cpp process_warning sets ``warning_damage`` to 3/2 of the
forecast it warned about, a player-wide figure (saved with the character), and asks again only
for a forecast above it (it halves on every quiet step).  So the step right after a refusal is
forecast no worse and is taken without a prompt.

n1-c life-200 (Quest 25, 2026-11-12 12:02-12:03): the prompt for (1,9)->(1,8) was refused, the
process stopped (no-key-exhausted), and the restarted one walked onto (1,8) unasked (a Chaos
breath, HP 570 -> 385); the prompt for (6,29)->(5,29) was refused, the process stopped again, and
the restarted one walked onto (5,29) unasked and died there.

The record beside the decision log keeps the floor, the game turn and both collections, written
at the ``choose_key`` exit when they changed.  Like breeder_floor_record and quest25_battle_record,
a process reads it once, on its first observed board, and restores it only on the same dungeon
floor at the same or a later game turn: the game does not advance between the two processes, and
every decision the previous process made on another floor rewrote the record for that floor.
"""
from __future__ import annotations

import json
from pathlib import Path

from hengbot.model import Position


def _carried(policy) -> dict:
    return {
        "refused": sorted([cell.y, cell.x] for cell in policy._warning_refused_cells),
        "trap": sorted([cell.y, cell.x, int(searches)]
                       for cell, searches in policy._trap_warning_cells.items()),
    }


def restore(policy, snapshot) -> None:
    """The first observed board of the process: adopt the previous process's cells once."""
    path = getattr(policy, "_warning_cell_record_path", None)
    if path is None or getattr(policy, "_warning_cell_record_read", False):
        return
    policy._warning_cell_record_read = True
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        floor_key = tuple(int(part) for part in record["floor"])
        turn = int(record["turn"])
        refused = [Position(int(y), int(x)) for y, x in record["state"]["refused"]]
        trap = {Position(int(y), int(x)): int(searches)
                for y, x, searches in record["state"]["trap"]}
    except (OSError, ValueError, KeyError, TypeError):
        return
    if (snapshot.in_town or floor_key != tuple(snapshot.floor_key)
            or snapshot.turn < turn):
        return
    for cell, searches in trap.items():
        policy._trap_warning_cells.setdefault(cell, searches)
    for cell in refused:
        policy._latch_warning_refusal(cell)


def record(policy, snapshot) -> None:
    """The ``choose_key`` exit: rewrite the record when the carried cells changed."""
    path = getattr(policy, "_warning_cell_record_path", None)
    if path is None:
        return
    carried = (tuple(snapshot.floor_key), _carried(policy))
    if getattr(policy, "_warning_cell_record", None) == carried:
        return
    policy._warning_cell_record = carried
    stored = {"floor": list(snapshot.floor_key), "turn": snapshot.turn, "state": carried[1]}
    try:
        Path(path).write_text(json.dumps(stored) + "\n", encoding="utf-8")
    except OSError:
        pass
