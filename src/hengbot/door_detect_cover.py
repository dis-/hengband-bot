"""The walls a door detection of this floor visit has reached count as searched.

Owner 2026-11-25 (asked 「閉じ込められた時、取り込んだドア感知などの感知が届いた壁はサーチ済みとして
扱い、すぐ岩石溶解で出ますか？」, answered 「感知が届いた壁はサーチせず溶かして出る」): a wall within the
range of a door detection the bot has cast -- an absorbed power, a staff, a rod, a scroll, or the
全感知 -- is searched already; sealed in, the bot melts out with Stone to Mud at once (sealed_pocket)
and searches only the walls outside every detection's range.  It widens the owner's 2026-11-08
「閉じた区画では感知手段を使う」 (sealed-pocket-search) to every floor.

n1-c life-222 (Magic-Eater Lv45, Mountain 50F, 2026-11-25 13:0x): after its *Destruction* the
player stood in a 171-cell pocket reaching beyond the circle (centre (23,175), worst radius 17,
farthest cell 31 off), so the melt right after the *Destruction* (sealed_pocket
``after_destruction_key``) did not answer; it cast the absorbed Detect Doors at (38,192) and then
sent the search 173 times on walls the cast had reached (ladder_idle's wall search and its walk to
the next wall).

Game (C:/hengband/src): detect_doors (spell-kind/spells-detection.cpp) runs detect_feat_flag with
TerrainCharacteristics::DOOR, which calls disclose_grid on every grid of the floor (outer wall
excluded) whose game distance (Grid::calc_distance, model.game_distance) from the player is at most
the range: every secret door there is shown, so no search of those walls can find one.  The range is
DETECT_RAD_DEFAULT 30 (spell/spells-util.h), divided by 3 in a DARKNESS dungeon (detect_feat_flag),
and DETECT_RAD_DEFAULT * 3 / 2 through Powerful Activation (cmd-usestaff.cpp:60, cmd-zaprod.cpp:50).
detect_all (the Rod of Detection, spells-detection.cpp:622) calls detect_doors with its own range.
The scroll reads DETECT_RAD_DEFAULT (scroll-read-executor.cpp:271).

The record (``MEMORY``, one floor visit):

- the absorbed uses, from me_powers (``door_detections``: the uses the game settled, Powerful
  Activation's radius included), copied every decision;
- a carried Rod of Door/Stair Location or of Detection, Staff of Detect Doors/Stairs or Scroll of
  Door/Stair Location, from the pack: between two boards one game turn apart or more, with the
  player on the same cell, a rod of them went charging, a staff of them lost a charge or the scrolls
  one fewer -- whichever producer sent the use (quest_target_search, kill_all_patrol, the staff
  identification...).  The radius is DETECT_RAD_DEFAULT, a third in a dungeon whose DARKNESS is
  not known yet (me_powers ``map_radius``, the smaller reading).

``covered`` is read by policy ``_undersearched_walls`` (every wall search, the shared
``_secret_wall_exit`` included, and retreat_enclosure's searched-before-melt rule) and by
quest_target_search's uncovered places.  A restart forgets the record (state_registry: may-be-lost):
the walls are searched again until the next detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import me_powers
from hengbot.model import (
    SV_ROD_DETECT_DOOR, SV_ROD_DETECTION, SV_SCROLL_DETECT_DOOR, SV_STAFF_DETECT_DOOR,
    TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, Position, game_distance,
)
from hengbot.policy_constants import NEIGHBOR_OFFSETS

MEMORY = "_door_detect_cover"
# (tval, sval) of a carried door detection.
CARRIED = frozenset({
    (TVAL_ROD, SV_ROD_DETECT_DOOR), (TVAL_ROD, SV_ROD_DETECTION),
    (TVAL_STAFF, SV_STAFF_DETECT_DOOR), (TVAL_SCROLL, SV_SCROLL_DETECT_DOOR),
})


@dataclass
class Cover:
    floor: tuple
    casts: list = field(default_factory=list)  # (centre, radius, turn) of each door detection
    last: tuple | None = None  # (turn, position, carried signature) of the previous board


def _signature(snapshot) -> dict:
    """(tval, sval) -> the pack's count of it: rods charging, staff charges, scrolls."""
    held: dict = {}
    for item in snapshot.inventory:
        kind = (item.tval, item.sval)
        if kind not in CARRIED or not item.aware:
            continue
        if item.tval == TVAL_ROD:
            value = (item.charging_count if item.charging_count is not None
                     else (item.count if item.charging else 0))
        elif item.tval == TVAL_STAFF:
            value = item.charges
        else:
            value = item.count
        held[kind] = held.get(kind, 0) + value
    return held


def _used(before: dict, after: dict) -> bool:
    """One carried door detection was used between the two signatures."""
    for kind, value in before.items():
        now = after.get(kind, 0)
        if kind[0] == TVAL_ROD:
            if kind in after and now > value:
                return True
        elif now == value - 1:
            return True
    return False


def _add(memory: Cover, centre: Position, radius: int, turn: int) -> None:
    if not any(each[0] == centre and each[2] == turn for each in memory.casts):
        memory.casts.append((centre, radius, turn))


def observe(policy, snapshot) -> None:
    """Every decision, after me_powers.observe: note the door detections that landed."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        return
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Cover(snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    for centre, radius, turn in me_powers.door_detections(policy, snapshot):
        _add(memory, centre, radius, turn)
    here, signature = snapshot.player.position, _signature(snapshot)
    if memory.last is not None:
        turn, position, before = memory.last
        if snapshot.turn > turn and position == here and _used(before, signature):
            _add(memory, position, me_powers.map_radius(policy, snapshot), turn)
    memory.last = (snapshot.turn, here, signature)


def casts(policy, snapshot) -> tuple:
    """(centre, radius) of every door detection of this floor visit."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return ()
    return tuple((centre, radius) for centre, radius, _ in memory.casts)


def covered(policy, cell: tuple) -> bool:
    """``cell`` (y, x) lies within a door detection of the policy's current floor visit."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or not memory.casts or memory.floor != getattr(policy, "_floor_key", None):
        return False
    position = Position(*cell)
    return any(game_distance(centre, position) <= radius for centre, radius, _ in memory.casts)


def around_covered(policy, position: Position) -> bool:
    """Every grid beside ``position`` lies within a door detection: a search there finds nothing."""
    return all(covered(policy, (position.y + dy, position.x + dx)) for dy, dx in NEIGHBOR_OFFSETS)
