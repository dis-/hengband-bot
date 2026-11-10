"""周辺感知 after a *Destruction*, and in a sealed pocket.

Owner 2026-11-05: 「*破壊*後の地形を全マス探索するのは無駄なので周辺感知があれば使って」.
Owner the same day, on the Scroll of Magic Mapping when no 周辺感知 is there: 「持っていれば読む」,
only what is held, with no keep or buy rule of its own.  And, asked whether to carry it:
「拾ったら即座に読む」 (the table's 「捨てる」 became 「拾って使う」, consumable_policy): an identified
one is read on the dungeon's first safe decision (``picked_up_scroll_key``, the moment the junk
rung used to destroy it), whatever the map shows: the words carry no condition, and the read
costs one turn.  A stack reads one scroll per safe decision, at once, without walking between.

The means, by the game (lib/edit/BaseitemDefinitions.jsonc): the staff (id 328, tval 55
sval 9) and the rod (id 371, tval 66 sval 5), both ``map_area(DETECT_RAD_MAP)``
(cmd-item/cmd-usestaff.cpp:141, cmd-zaprod.cpp:102), and a Magic-Eater's absorbed power
of either (the me_powers rows, asked first).  Last, while a *Destruction* is unmapped, the
scroll (id 189, tval 70 sval 25, object-use/read/scroll-read-executor.cpp:244, the same
map_area), which needs a grid the player can read on and never fails.

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

from hengbot import consumable_policy, junk_destroy_now, me_powers
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    SV_ROD_MAPPING, SV_SCROLL_MAPPING, SV_STAFF_MAPPING, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF,
    Position, Snapshot, game_distance,
)


REASON = "area-mapping"
AFTER_DESTRUCTION = "after-destruction"
SEALED_POCKET = "sealed-pocket"
PICKED_UP = "picked-up"
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
    circles: list = field(default_factory=list)  # (centre, radius, sure radius) of each use


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
    memory.circles.append((centre, radius, sure_radius))
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
    for centre, _, radius in (() if memory is None else memory.circles):
        cells |= mapped_area.disc_cells(snapshot, centre, radius)
    return cells


def wrecked(policy, cell: tuple) -> bool:
    """``cell`` (y, x) lies in the sure radius of a *Destruction* of the policy's current floor
    visit.  destroy_area (spell-kind/spells-floor.cpp) gives every grid there that is not
    PERMANENT a new random granite, quartz, magma or floor terrain: no secret door is left in
    it, so its walls are not searched (n1-b life-367, 2026-11-10: 17 of 41 dives from 46F on
    searched the walls of their own circle until the stuck count read Recall at full HP)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or not memory.circles or memory.floor != getattr(policy, "_floor_key", None):
        return False
    position = Position(*cell)
    return any(game_distance(centre, position) <= sure for centre, _, sure in memory.circles)


def circle_count(policy, snapshot: Snapshot) -> int:
    """How many *Destruction*s of this floor visit were seen."""
    memory = _floor_memory(policy, snapshot)
    return 0 if memory is None else len(memory.circles)


def destroyed_since_arrival(policy, snapshot: Snapshot) -> bool:
    """The player's *Destruction* was seen on this floor visit."""
    memory = _floor_memory(policy, snapshot)
    return memory is not None and bool(memory.circles)


def in_destroyed_circle(policy, snapshot: Snapshot, cells) -> bool:
    """Every one of ``cells`` lies in reach of one *Destruction* of this floor visit."""
    memory = _floor_memory(policy, snapshot)
    return memory is not None and any(
        all(game_distance(centre, cell) <= radius for cell in cells)
        for centre, radius, _ in memory.circles)


def _due(policy, snapshot: Snapshot) -> bool:
    memory = _floor_memory(policy, snapshot)
    return (memory is not None and memory.destroyed_turn is not None
            and not me_powers.mapped_since(policy, snapshot, memory.destroyed_turn))


def device_ready(item, kind: str) -> bool:
    """An identified staff with a charge, or a rod of the stack not charging."""
    if not item.known or not item.aware:
        return False
    if kind == "staff":
        return item.charges > 0
    return (item.charging_count or 0) < item.count and (
        item.charging_count is not None or not item.charging)


def _carried_device(snapshot: Snapshot):
    for item in snapshot.inventory:
        kind = CARRIED.get((item.tval, item.sval))
        if kind is not None and device_ready(item, kind):
            return item, kind
    return None


def device_usable_now(policy, snapshot: Snapshot) -> bool:
    """A utility device may be used on this board (the mapping row's hostile rule)."""
    player = snapshot.player
    return (not (player.blind or player.confused or player.hallucinated or player.paralyzed)
            and me_powers.utility_device_permitted(policy, snapshot))


def means_held(policy, snapshot: Snapshot) -> bool:
    """A 周辺感知 to use: an absorbed power with a charge or a ready carried device."""
    return me_powers.map_charged(policy, snapshot) or _carried_device(snapshot) is not None


def _held_scroll(snapshot: Snapshot):
    return next((item for item in snapshot.inventory
                 if (item.tval, item.sval) == (TVAL_SCROLL, SV_SCROLL_MAPPING)
                 and item.known and item.aware), None)


def _held_scroll_key(policy, snapshot: Snapshot) -> str | None:
    """The read of a held Scroll of Magic Mapping, for an unmapped *Destruction*."""
    item = _held_scroll(snapshot)
    if item is None or not _due(policy, snapshot) or not policy._can_read_scrolls(snapshot):
        return None
    return policy._read_key(snapshot, item)


def picked_up_scroll_key(policy, snapshot: Snapshot) -> str | None:
    """A carried Scroll of Magic Mapping, read on the first safe decision; its disc counts."""
    item = _held_scroll(snapshot)
    if (item is None or not junk_destroy_now.safe(policy, snapshot)
            or not policy._can_read_scrolls(snapshot)):
        return None
    memory = _memory(policy, snapshot)
    if not consumable_policy.read_allowed(policy, snapshot, item):
        memory.pending = None  # the refused read mapped nothing
        return None
    policy.last_reason = f"{REASON}:{PICKED_UP}"
    memory.pending = (snapshot.turn, snapshot.player.position, me_powers.map_radius(policy, snapshot))
    return policy._read_key(snapshot, item)


def _carried_key(policy, snapshot: Snapshot, trigger: str) -> str | None:
    memory, position = _memory(policy, snapshot), snapshot.player.position
    if (memory.failed[position] >= me_powers.FAILURES_PER_PLACE
            or not device_usable_now(policy, snapshot)):
        return None
    carried = _carried_device(snapshot)
    used = None if carried is None else reserved_item_command(policy, snapshot, carried[1], carried[0])
    if used is None:
        used = _held_scroll_key(policy, snapshot)
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
