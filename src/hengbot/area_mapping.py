"""周辺感知 after a *Destruction*, and in a sealed pocket.

Owner 2026-11-05: 「*破壊*後の地形を全マス探索するのは無駄なので周辺感知があれば使って」.
Not the Scroll of Magic Mapping: the owner named 周辺感知, and that is a different item.

The means, by the game (lib/edit/BaseitemDefinitions.jsonc): the staff (id 328, tval 55
sval 9) and the rod (id 371, tval 66 sval 5), both ``map_area(DETECT_RAD_MAP)``
(cmd-item/cmd-usestaff.cpp:141, cmd-zaprod.cpp:102), and a Magic-Eater's absorbed power
of either (the me_powers rows, asked first).

``destruction_use.observe`` reports the flash (``note_destruction``): the circle's map is
gone, so the next decision that asks (the FLOOR occasion's row, then
``after_destruction_key``, below the survival rungs) maps it once, under the rule a utility
device has near monsters (me_powers.utility_device_permitted).  A *Destruction* blinds
without the resistance: the map waits until sight returns.  A failed use keeps it due, up
to me_powers.FAILURES_PER_PLACE at one place.

A carried device's discs join mapped_area's sources (``carried_areas``), and that is what
stops exploration walking them (owner 2026-11-01 「部屋だけ見て回る」).  That rule still goes
to see a room, for its items; destroy_area deleted every item of the circle
(spell-kind/spells-floor.cpp) and half of its grids are floor, so most of it reads as a
room.  Hence the mapped blanks of the sure radius (``destroyed_cells``) all count as
explored.  A disc that met the circle is forgotten (``note_destruction``) so its old
blanks no longer read as floor.

In a sealed pocket (sealed_pocket) the map is read before anything is melted, while it is
due or the player stands in no live map: it may show the way (``sealed_key``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from hengbot import me_powers
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    SV_ROD_MAPPING, SV_STAFF_MAPPING, TVAL_ROD, TVAL_STAFF, Position, Snapshot, game_distance,
)


REASON = "area-mapping"
AFTER_DESTRUCTION = "after-destruction"
SEALED_POCKET = "sealed-pocket"
MEMORY = "_area_mapping_memory"
CARRIED = {(TVAL_STAFF, SV_STAFF_MAPPING): "staff", (TVAL_ROD, SV_ROD_MAPPING): "rod"}
FAILED = frozenset({
    "杖をうまく使えなかった。", "You failed to use the staff properly.",
    "うまくロッドを使えなかった。", "You failed to use the rod properly.",
})


@dataclass
class Memory:
    floor: tuple
    destroyed_turn: int | None = None   # the last *Destruction* not mapped since
    discs: list = field(default_factory=list)  # (centre, radius) a carried device mapped
    pending: tuple | None = None        # (turn, position, radius) of the last use
    failed: Counter = field(default_factory=Counter)  # position -> failed uses
    circles: list = field(default_factory=list)  # (centre, sure radius) of each use


def _memory(policy, snapshot: Snapshot) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Memory(snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    return memory


def _floor_memory(policy, snapshot: Snapshot) -> Memory | None:
    memory = getattr(policy, MEMORY, None)
    return memory if memory is not None and memory.floor == snapshot.floor_key else None


def note_destruction(policy, snapshot: Snapshot, centre: Position, radius: int, sure_radius: int) -> None:
    """The flash on this board: no disc that met the circle (at most ``radius``) still
    maps it, and within ``sure_radius`` nothing is left to go and see."""
    memory = _memory(policy, snapshot)
    memory.destroyed_turn = snapshot.turn
    memory.circles.append((centre, sure_radius))
    memory.discs = [disc for disc in memory.discs
                    if game_distance(centre, disc[0]) > radius + disc[1]]
    me_powers.forget_maps(policy, snapshot, centre, radius)


def observe(policy, snapshot: Snapshot) -> None:
    """Every decision: settle the last use of a carried device."""
    memory = _floor_memory(policy, snapshot)
    if memory is None or memory.pending is None or snapshot.turn == memory.pending[0]:
        return
    _, position, radius = memory.pending
    memory.pending = None
    if any(message in FAILED for message in snapshot.messages):
        memory.failed[position] += 1
    else:
        memory.discs.append((position, radius))
        memory.destroyed_turn = None


def carried_areas(policy, snapshot: Snapshot) -> tuple:
    """mapped_area's source: what a carried device mapped on this floor visit."""
    memory = _floor_memory(policy, snapshot)
    return () if memory is None else tuple(memory.discs)


def destroyed_cells(policy, snapshot: Snapshot) -> set:
    """(y, x) of the sure radius of every *Destruction* of this floor visit."""
    from hengbot import mapped_area

    memory = _floor_memory(policy, snapshot)
    cells = set()
    for centre, radius in (() if memory is None else memory.circles):
        cells |= mapped_area.disc_cells(snapshot, centre, radius)
    return cells


def _due(policy, snapshot: Snapshot) -> bool:
    memory = _floor_memory(policy, snapshot)
    return (memory is not None and memory.destroyed_turn is not None
            and not me_powers.mapped_since(policy, snapshot, memory.destroyed_turn))


def _carried_device(snapshot: Snapshot):
    for item in snapshot.inventory:
        kind = CARRIED.get((item.tval, item.sval))
        if kind is None or not item.known or not item.aware:
            continue
        if kind == "staff" and item.charges > 0:
            return item, kind
        if kind == "rod" and (item.charging_count or 0) < item.count and (
                item.charging_count is not None or not item.charging):
            return item, kind
    return None


def _carried_key(policy, snapshot: Snapshot, trigger: str) -> str | None:
    memory, position, player = _memory(policy, snapshot), snapshot.player.position, snapshot.player
    if (player.blind or player.confused or player.hallucinated or player.paralyzed
            or memory.failed[position] >= me_powers.FAILURES_PER_PLACE
            or not me_powers.utility_device_permitted(policy, snapshot)):
        return None
    carried = _carried_device(snapshot)
    used = None if carried is None else reserved_item_command(policy, snapshot, carried[1], carried[0])
    if used is None:
        return None
    policy.last_reason = f"{REASON}:{trigger}"
    memory.pending = (snapshot.turn, position, me_powers.map_radius(policy, snapshot))
    return used


def after_destruction_key(policy, snapshot: Snapshot) -> str | None:
    """A carried device, where the FLOOR occasion's absorbed power did not answer."""
    return _carried_key(policy, snapshot, AFTER_DESTRUCTION) if _due(policy, snapshot) else None


def due_after_destruction(ctx) -> bool:
    """me_powers' trigger: the *Destruction* is not yet mapped."""
    return _due(ctx.policy, ctx.snapshot)


def _covered(policy, snapshot: Snapshot, discs: tuple) -> bool:
    here = snapshot.player.position
    return any(game_distance(here, centre) < radius for centre, radius in discs)


def sealed_key(policy, snapshot: Snapshot) -> str | None:
    """The map of a sealed pocket, read before anything is melted, else None."""
    from hengbot import mapped_area

    if _covered(policy, snapshot, mapped_area.floor_discs(policy, snapshot)) and not _due(policy, snapshot):
        return None
    return (me_powers.power_key(policy, snapshot, me_powers.SEALED)
            or _carried_key(policy, snapshot, SEALED_POCKET))


def blank_floor(policy, snapshot: Snapshot) -> set:
    """(y, x) a mapping left blank: walkable floor, what the player reads off the map
    (mapped_area's docstring), on any floor."""
    from hengbot import mapped_area

    cells = set()
    for centre, radius in mapped_area.floor_discs(policy, snapshot):
        cells |= mapped_area.disc_cells(snapshot, centre, radius)
    return {cell for cell in cells
            if (grid := snapshot.grid_at(Position(*cell))) is None or not grid.known}
