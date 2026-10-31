"""Read Recall from a lit grid when the own grid is too dark to read.

Owner 2026-10-31 (#47, n1-c life-055 鉄獄1階): 「明るいマスへ歩いて帰還を読むが、
そもそも光源を切らさない努力が必要」.  Where every '<' leaves for the
wilderness the return must read Recall (wilderness_exit), and the game
refuses a read when the player cannot see the own grid (cmd_limit_blind /
no_lite).  A glowing room floor is seen without a light
(geometry.cpp player_can_see_bold: CAVE_GLOW without CAVE_MNDK), so the
return walks to the nearest one it remembers and reads there.

Fair knowledge only: a floor grid the player saw lit, i.e. drawn with the
standard lighting symbol (F_LIT_STANDARD, view/display-map.cpp
decide_visible_terrain_lighting); out of view the game draws it darkened.
The keeping of the light itself is the light owners' work (_darkness_recovery_key).
"""

from hengbot.me_powers import F_LIT_STANDARD

_MEMORY = "_lit_floor_memory"


def _lit_floor(grid) -> bool:
    return (grid.known and grid.passable and not grid.wall and not grid.is_door
            and grid.map_lighting == F_LIT_STANDARD)


def observe(policy, snapshot) -> None:
    """Remember, per floor, the floor grids the player has seen lit."""
    if snapshot.in_town or snapshot.player.blind:
        return
    memory = getattr(policy, _MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        memory = (snapshot.floor_key, set())
        setattr(policy, _MEMORY, memory)
    memory[1].update(grid.position for grid in snapshot.grids.values() if _lit_floor(grid))


def remembered_lit_floors(policy, snapshot) -> set:
    memory = getattr(policy, _MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        return set()
    return memory[1]


def lit_grid_step_key(policy, snapshot) -> str | None:
    """Walk a latched return toward the nearest remembered lit floor.

    The dark locomotion asks here first; on the lit floor the return owner's
    Recall rung reads (its own darkness test passes there).
    """
    player = snapshot.player
    if (
        not policy._returning_to_town
        or player.blind or player.confused  # no grid lifts these read limits
        or policy._can_read_scrolls(snapshot)
        or not policy._up_stairs_exit_to_wilderness()
        or policy._find_recall_scroll(snapshot) is None
    ):
        return None
    lit = remembered_lit_floors(policy, snapshot)
    if not lit:
        return None
    step = policy._nearest_goal_step(snapshot, lambda grid: grid.position in lit)
    if step is None:
        return None
    policy.last_reason = "return:seek-lit-grid"
    return policy._step_toward(snapshot, step)
