"""A monster's reach across glass: seen through, and stopped (ガラスの城, glass rooms and doors).

The game.  A glass wall or a closed glass door has LOS without PROJECTION
(lib/edit/TerrainDefinitions.jsonc; terrain_knowledge.load_los_only_terrain_ids): the player
sees what stands behind it, and projectable() stops on it (projection-path-calculator.cpp:94).
Every ranged attack of a monster is a spell of make_attack_spell, cast only when
decide_lite_projection succeeds (mspell-attack.cpp): the player's grid is projectable from the
monster, or a grid next to the player with PROJECTION is (adjacent_grid_check,
mspell-lite.cpp:208-230; the bot's ``_offset_spell_reach``).  Across glass neither is, and only
three spells still reach the player (mspell-lite.cpp:95-190):

- BR_LITE along the line of sight: decide_lite_range keeps it on a LOS line, and
  check_lite_area_by_mspell / decide_lite_breath cast it at cdis below / up to half of
  get_max_range() (18 / 2 = 9);
- BR_DISI, which melts the glass on its way (CAN_DISINTEGRATE), at cdis below 9
  (check_lite_area_by_mspell, in_disintegration_range);
- BA_LITE within get_max_range(), its ball landing within 3 grids of the player on a LOS line
  (check_lite_area_by_mspell).

The game draws each of them only now and then (one_in_(5), one_in_(10)); the bot counts the
attempt as the forced cast, the larger reading.

n1-c life-207 (Magic-Eater Lv46, ガラスの城 60F, 2026-11-14, the owner's 「帰還の条件がおかしい
気がする」): the bot read every monster it saw through the glass as able to breathe at it.
Sixteen to ninety-four awake monsters behind glass read 即死 (next action's p95 636 to 20631
against HP 603) on the arrival boards: Teleportation was read, counted as an escape, the next
landing showed another glassed room, and the second escape returned to town -- about one dive a
minute.  The same boards read across the glass have no 即死 and mostly T3.
"""
from __future__ import annotations

from hengbot.policy_constants import MONSTER_SPELL_MAX_RANGE

HALF_RANGE = MONSTER_SPELL_MAX_RANGE // 2  # get_max_range() / 2 (mspell-lite.cpp)
# (ability, the largest cdis it is cast at across glass)
PASSING = (("BR_LITE", HALF_RANGE), ("BR_DISI", HALF_RANGE - 1), ("BA_LITE", MONSTER_SPELL_MAX_RANGE))


def stops(policy, grid) -> bool:
    """A known grid seen through that stops a projection (LOS without PROJECTION)."""
    return (grid is not None and grid.known
            and grid.terrain_id in getattr(policy, "_los_only_terrain_ids", frozenset()))


def passing_abilities(policy, snapshot, monster, knowledge, target) -> frozenset:
    """The race's abilities that reach ``target`` from ``monster`` where the ordinary reach
    (a projectable line, or a projectable grid beside the target) fails: on a line read through
    glass, within each spell's distance; none without such a line."""
    if knowledge is None or not knowledge.abilities:
        return frozenset()
    distance = policy._monster_cast_distance(monster.position, target)
    held = frozenset(ability for ability, reach in PASSING
                     if ability in knowledge.abilities and distance <= reach)
    if not held:
        return frozenset()
    # The two lines the ordinary reach reads (threat_prediction): the board's and the map
    # memory's, and projectable() with the unknown grids open (owner 2026-11-08), through glass.
    sight = (policy._has_line_of_fire(snapshot, monster.position, target,
                                      remembered=policy._remembered_grids, across_glass=True)
             or policy._may_project(snapshot, monster.position, target, across_glass=True))
    return held if sight else frozenset()
