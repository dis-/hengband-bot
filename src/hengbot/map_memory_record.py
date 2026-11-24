"""The remembered map of a dungeon floor, carried across a bot restart (n1-c life-221, 2026-11-24).

The policy's map memory (``_remembered_grids``, merged under every board by
``HengbotPolicy._with_grid_memory``) holds what the board no longer shows.  Game facts
(src/view/display-map.cpp ``is_map_terrain_visible``, src/bot/bot-json-output.cpp
``make_grid_map_json``): the board carries a REMEMBER terrain (wall, door, rubble, stairs) only
while its grid has CAVE_MARK, and a floor only while it is marked, lit or in view; a dark floor the
player saw by the torch is not marked and leaves the board once out of sight.  A magic mapping
(map_area) marks the walls, never the floor.  The game keeps CAVE_MARK in its own floor (and in the
save), so after a bot restart the board still shows the marked walls; what was lost is the bot's
own observation of the unmarked cells.

n1-c life-221 (Angband 100F, 2026-11-24 09:54, a deploy's restart): the ground west of the vault
went unshown, the finale found no stand on the Serpent's rays (``rays=0``) while the floor's map
discs (exploration_ledger ``mapped_areas``, which a restart keeps) read the player covered, and the
battle held until the stall bound.  Owner 2026-11-24: 「長期戦になる99F 100Fにおいて無駄な行動は許さ
れない」.

The record (``map-memory.pkl`` beside the decision log) is the map memory of the dungeon floor the
policy is on, with its region (``_with_grid_memory``'s: floor key, size, town, in town) and the game
turn of the board that wrote it.  It is written at the ``choose_key`` exit when the memory changed:
at once when the region changed or a cell was forgotten (a *Destruction*, a melted or dug wall),
otherwise at most every ``SAVE_CADENCE`` decisions (a write pickles the whole map, ~40 ms).  Off a
dungeon floor (town, the surface) it holds nothing, so a later visit to the same floor key never
reads an earlier visit's map.  The first region a process reads restores it, once, before that
board merges over it (the board stays authoritative), only

- for the same region (the same floor: dungeon, level, quest, and the same size), and
- at the same or a later game turn: a game reloaded from an older save is not the map the record saw.

A restart loses at most the last ``SAVE_CADENCE`` decisions' new cells, mostly the ones the board
still shows.  Nothing is invented: what is restored is what the previous process remembered.

The floor's map discs stay as they are: what they claim holds after a restart too (the game kept
the walls the mapping marked, and a blank grid inside a disc is floor, mapped_area); what the
restart lost was this memory, and it is this memory that is now carried.
"""
from __future__ import annotations

import pickle
from pathlib import Path

VERSION = 1
FILE_NAME = "map-memory.pkl"
# Decisions a changed memory waits before it is written (a forgotten cell or a new region at once).
SAVE_CADENCE = 16

PATH = "_map_memory_record_path"
WRITTEN = "_map_memory_record"
READ = "_map_memory_record_read"


def _carried(region) -> bool:
    """The region is a dungeon floor's (not the town, not the surface's (0, 0, 0))."""
    return region is not None and not region[6] and tuple(region[:3]) != (0, 0, 0)


def _mark(policy) -> tuple:
    region = getattr(policy, "_remembered_grid_region", None)
    return (region, len(getattr(policy, "_remembered_grids", {})),
            getattr(policy, "_remembered_grid_revision", 0))


def record(policy, snapshot) -> None:
    """The ``choose_key`` exit: write the map memory when it changed (see the module docstring)."""
    path = getattr(policy, PATH, None)
    if path is None:
        return
    mark = _mark(policy)
    written = getattr(policy, WRITTEN, None)   # (mark written, decisions changed since)
    if written is not None and written[0] == mark:
        return
    if written is not None:
        last_region, last_size = written[0][0], written[0][1]
        pending = written[1] + 1
        if last_region == mark[0] and mark[1] >= last_size and pending < SAVE_CADENCE:
            policy.__dict__[WRITTEN] = (written[0], pending)
            return
    region = mark[0]
    held = None
    if _carried(region):
        held = {"version": VERSION, "region": tuple(region), "turn": int(snapshot.turn),
                "grids": dict(policy._remembered_grids)}
    try:
        payload = pickle.dumps(held, protocol=pickle.HIGHEST_PROTOCOL)
        temporary = Path(path).with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
    except (OSError, pickle.PicklingError, TypeError, AttributeError):
        return
    policy.__dict__[WRITTEN] = (mark, 0)


def load(path) -> dict | None:
    """The record at ``path``, or None when there is none or it does not load."""
    try:
        held = pickle.loads(Path(path).read_bytes())
    except Exception:  # noqa: BLE001 -- an unreadable record restores nothing (a restart as before)
        return None
    if not isinstance(held, dict) or held.get("version") != VERSION:
        return None
    return held


def restorable(held: dict | None, region, snapshot) -> bool:
    """The record is of this region (a dungeon floor's) and not of a later game turn than this board's."""
    return (held is not None and _carried(region) and tuple(held["region"]) == tuple(region)
            and int(snapshot.turn) >= int(held["turn"]))


def restored_grids(policy, region, snapshot) -> dict:
    """The first region of a process (``_with_grid_memory``, before the board's merge): the
    remembered grids of the record, or {} (once per process)."""
    path = getattr(policy, PATH, None)
    if path is None or getattr(policy, READ, False):
        return {}
    policy.__dict__[READ] = True
    held = load(path)
    if not restorable(held, region, snapshot):
        return {}
    return dict(held["grids"])
