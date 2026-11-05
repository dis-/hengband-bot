"""A plan's dark room, lit when something not seen acts on the player.

Owner 2026-11-05 「Q25で敵が見えないなら部屋が暗いということのはずなので、光の巻物か啓蒙の薬で適宜
照らすことを要求する」 (``room_sweep.light_dark_room``).

Game (C:/hengband/src):
 * Scroll of Light: lite_area (spells-lite.cpp), a radius 2 LITE_WEAK burst, then lite_room: CAVE_GLOW
   from the player's cell over every CAVE_ROOM cell joined through LOS terrain, so up to and
   including a closed door and on through an open one.  Every cell of Quest 25's map is CAVE_ROOM.
   A sleeper there wakes (SMART always, STUPID 1/10, else 1/4; cave_temp_room_lite).
 * Absorbed Light: the same, by the shared _quest_light_key.
 * Potion of Enlightenment: wiz_lite (spells-floor.cpp): CAVE_GLOW and CAVE_KNOWN on the whole floor,
   permanently, floor objects marked; it wakes nobody and detects no monster.  What stands in the
   player's line on a glowing cell is seen by update_monster.  Hence the potion goes first when
   carried: it spends no read in any later room and wakes nobody.
 * What unlights: DARKNESS (mspell-floor.cpp, unlite_area, the whole room) and a dark bolt or ball
   (effect-feature.cpp, its radius only).  Fire does not touch CAVE_GLOW; it burns the scrolls.
 * A caster needs its line to the player (mspell), and the player sees a monster on a glowing or
   torch-lit cell in his line unless it hides by CAVE_MNDK or is invisible without see_invisible.
   So 何か in a room is on a dark cell of it, or past an open door.

What the board shows (view/display-map.cpp decide_visible_terrain_lighting, protocol 3): a floor cell in
view and glowing is drawn F_LIT_STANDARD; the player's and a monster's own light F_LIT_LITE whatever
the glow; an unlit one out of the light is blank or remembered dark.  Terrain whose symbols do not
differ merges into F_LIT_STANDARD (decide_map_terrain_lighting), so only plain floor is read.  The room is
dark when the floor cells in the player's line beyond his light exist and none is drawn lit.  A
small room inside his light hides nothing and is never dark.

「適宜」: once a room; ``sweep_light_read`` holds the rooms read and not yet seen lit, so a reading
that lit nothing is not repeated, and a room seen lit and dark again (DARKNESS) is read again.
"""

from __future__ import annotations

import re

from hengbot import quest_exposure, summon_response, unseen_strike
from hengbot.item_reservation import reserved_item_command
from hengbot.me_powers import F_LIT_STANDARD
from hengbot.model import Position, TVAL_POTION
from hengbot.policy_constants import QUEST_POTION_SVALS

LIGHT_REASON = "quest-strategy:sweep-light"
UNSEEN_LIGHT_REASON = "quest-strategy:sweep-light-unseen"
ROOM_LIGHT_POTION = "enlightenment"

# 「何かが」 opens every monster spell line but these (floor-object.cpp, world-turn-processor.cpp).
_NOT_A_CAST = ("何かが足下", "何かが聞こえ")
_UNSEEN_CAST_START = "何かが"
_UNSEEN_HASTE = "何かの動きが速くなった"
_REPEAT_RE = re.compile(r" <x[1-9]\d*>$")


def carried_potion(policy, snapshot, name: str):
    """The aware potion of a QUEST_POTION_SVALS name, carried."""
    return policy._first_item(snapshot, lambda item: item.tval == TVAL_POTION and item.aware
                              and item.sval == QUEST_POTION_SVALS[name])


def _casts_unseen(policy, message: str) -> bool:
    text = _REPEAT_RE.sub("", message)
    if text.startswith(_NOT_A_CAST):
        return False
    return (text.startswith(_UNSEEN_CAST_START) or text.startswith(_UNSEEN_HASTE)
            or any(not summon.seen for summon in summon_response.summons_of(text))
            or (policy._is_unseen_attack_message(text) and policy._is_unseen_spell_message(text)))


def acted_on_by_unseen(policy, snapshot, hit_by_unseen: bool) -> bool:
    """Cast at, or hit from afar, by what the player does not see.  A blow is from beside him:
    his own light is on it, and a room's light shows nothing more."""
    if any(_casts_unseen(policy, message) for message in snapshot.messages):
        return True
    return hit_by_unseen and not unseen_strike.hit_in_melee(policy, snapshot)


def drawn_lit(snapshot, cell: tuple[int, int]) -> bool:
    grid = snapshot.grid_at(Position(*cell))
    return (grid is not None and grid.known and grid.map_lighting == F_LIT_STANDARD
            and not grid.trap and not grid.is_door)


def room_of(terrain, here: tuple[int, int]) -> frozenset:
    """The cells lite_room reaches from ``here`` over a map with its open doors as floor."""
    room, pending = {here}, [here]
    while pending:
        y, x = pending.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell = (y + dy, x + dx)
                if cell not in room and terrain.get(cell) in quest_exposure.PROJECTING_KINDS:
                    room.add(cell)
                    pending.append(cell)
    return frozenset(room)


def _far_floor(terrain, snapshot, room) -> list[tuple[int, int]]:
    """The room's plain floor in the player's line, beyond his own light."""
    here = (snapshot.player.position.y, snapshot.player.position.x)
    reach = max(1, snapshot.light_radius or 1)
    return [cell for cell in room
            if terrain.get(cell) == "floor" and quest_exposure.game_distance(here, cell) > reach
            and quest_exposure.projectable(terrain, here, cell)]


def _light_key(policy, snapshot, reason: str) -> str | None:
    potion = carried_potion(policy, snapshot, ROOM_LIGHT_POTION)
    if potion is not None:
        policy.last_reason = reason
        return reserved_item_command(policy, snapshot, "quaff", potion)
    if not policy._can_read_scrolls(snapshot):
        return None
    return policy._quest_light_key(snapshot, reason)


def light_room_key(policy, snapshot, navigator, terrain, reason: str) -> str | None:
    """The light when this room is dark and its reading is due; ``terrain`` has open doors as floor."""
    if snapshot.player.blind:
        return None
    room = room_of(terrain, (snapshot.player.position.y, snapshot.player.position.x))
    far = _far_floor(terrain, snapshot, room)
    if any(drawn_lit(snapshot, cell) for cell in far):
        navigator.sweep_light_read = navigator.sweep_light_read - {room}
        return None
    if not far or room in navigator.sweep_light_read:
        return None
    key = _light_key(policy, snapshot, reason)
    if key is not None:
        navigator.sweep_light_read = navigator.sweep_light_read | {room}
    return key


def unseen_light_key(policy, snapshot, navigator, plan, terrain, hit_by_unseen: bool) -> str | None:
    """Owner 2026-11-05: acted on by what is not seen, in a dark room: light it."""
    if not plan.get("light_dark_room") or not acted_on_by_unseen(policy, snapshot, hit_by_unseen):
        return None
    return light_room_key(policy, snapshot, navigator, terrain, UNSEEN_LIGHT_REASON)
