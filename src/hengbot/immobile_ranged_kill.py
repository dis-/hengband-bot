"""Shoot a kept-away never-moving monster when it can be killed safely from range.

Owner 2026-11-02 (immobile-weak-kill-1102): 「遠距離で安全に倒せるなら倒す方を優先
する。思ったより探索に与える不具合が大きかった。」 -- every never-moving monster
the bot keeps away from (the stat-drain or lethal ring of
immobile_threat_memory, the immobile summoner's line-of-fire zone) is killed
from range when that is safe, and avoided only when it is not.

Recorded n1-c life-107 (Labyrinth 18F, 2026-11-02 19:56-20:08): a 発光アイ
(race 80, NEVER_MOVE, GAZE:LOSE_STR, 18 HP) on the corner (6,7) of a
one-cell corridor.  Its stat-drain ring took the corridor out of every
route; from the corridor cells the eye was in view but never projectable, so
the ranged ladder fired blind ``*t`` shots and exploration turned back, round
after round, while the one cell two steps short of the ring, (8,6), sees it
on a clear bolt path and one arrow (58 expected) kills it.

"Safe ranged kill" is the existing summoner ranged-kill rule
(``_summoner_ranged_kill_key``, owner 11-01 survival2 question 2 「3発以内」)
applied to the never-moving monster:

- it dies within SUMMONER_RANGED_KILL_SHOTS shots of the expected ranged
  damage (``_summoner_shots_to_kill``), with matching ammunition and neither
  blind nor confused (``_summoner_ranged_attack_available``'s player gates);
- a shooting cell exists: the player's cell or the nearest walkable cell
  (the routes already leave the rings out) from which the player's bolt path
  reaches it (``_may_project``) within the ranged range and not beside it;
- the player survives it meanwhile: its one-turn prediction from contact
  (the lethal ring's own ``threat_prediction(..., contact=True)``, which
  over-counts a touch that cannot land) over the walk plus the shots stays
  below the current HP -- the summoner rule's ``_predicted_damage(...,
  turns=3) >= hp`` refusal with the walk counted;
- no other hostile is in view or beside the player: those go to the normal
  ladder first (survival first);
- it was not out of view from a shooting cell the player reached since it
  was last perceived (``immobile_threat_memory.unaimed``): a dark or
  invisible monster cannot be aimed at, and the walk back to that cell
  alternated with the summoner zone's step out of it (n1-c life-110,
  Orc cave 22F, 2026-11-02 22:44: a クイルスルグ remembered at (37,141),
  ``7`` to (42,141) and ``3`` back until the loop detector stopped the bot);
- the walk never came back to a cell it already stepped from on this floor
  visit (``immobile_threat_memory.walk_retired``): whatever answered the board
  at the end of the walk, a return means the walk does not end in a shot.  The
  monster stays avoided, and is shot if the player's own cell shows it.  The
  type, by what sent the player back: another hostile in view at the shooting
  cell (n1-c life-125, Dungeon 14F, 2026-11-04 07:18, seek-loot's step back);
  telepathy lifting ``unaimed`` on both cells (n1-a life-477, Angband 13F,
  08:53, a 発光アイ at (8,6), ``4`` to (4,9) and seek-downstairs' ``6`` back);
  a dark monster seen only from beside it (n1-b life-308, Orc cave 11F, 12:42,
  a 死体の塊 at (27,76), ``7`` to (25,74) and the next corpse's ``3`` back).

On a floor whose exit is locked nothing changes: the existing fight owners
decide there.

Owner 2026-11-05 (disenchant_avoid.left_alone): a disenchanting one with a breath is
not shot; an awake one whose touch alone disenchants is, as above; a sleeping one only
when its ring closes the way on (``closes_the_way``, 「通路をふさぐ時だけ撃つ」).

Owner 2026-11-06 「先にその敵を倒す」 (``blocking_key``): 「ふさいでいる動かない敵を、離れた所から
撃って倒しに行く。倒せない時だけ 11-04 の決まりに進む。」  In a maze (a dungeon with MAZE),
when a live remembered monster's ring is what leaves no frontier and no known stair
reachable (``blocks_the_way``, over the remembered floor: a forgetting maze shows only the
cells in view), the bot walks to a cell outside the ring and shoots it -- the plan above
without its three-shot bound, since only a ranged attack that cannot hurt it or no
reachable shooting cell with a line to it makes it unkillable.  The plan's other refusals
stay (the player surviving the walk and the shots, another hostile present, a monster not
in view from a reached shooting cell, a walk that came back).  When it cannot be killed so,
the ring takes the enclosure ladder (retreat_enclosure ``ring_ladder_key``: dig, disarm,
strike a weak enemy, then Teleportation, or Recall at or below the reserve).  Recorded
n1-c life-156 (Labyrinth 10F, 2026-11-06): a レッド・ゼリー's ring cut the one-wide junction;
four bolts kill it, so the ordinary plan refused it and the bot wandered.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from hengbot import disenchant_avoid, immobile_threat_memory, retreat_enclosure
from hengbot.model import MonsterState, Position
from hengbot.policy_constants import RANGED_MAX_DISTANCE, SUMMONER_RANGED_KILL_SHOTS

APPROACH_REASON = "immobile-threat:approach-to-shoot"


@dataclass(frozen=True)
class KillPlan:
    target: MonsterState
    step: Position | None  # None: shoot from here


def kept_away(policy, snapshot, monster: MonsterState) -> bool:
    """A never-moving monster an avoidance mechanism keeps the player away from."""
    return immobile_threat_memory.never_moves(policy, monster) and (
        monster.can_summon or immobile_threat_memory.avoided(policy, snapshot, monster))


def _shooting_cell(policy, snapshot, monster: MonsterState, grid) -> bool:
    distance = grid.position.distance_to(monster.position)
    return (grid.passable and not grid.has_monster
            and 2 <= distance <= RANGED_MAX_DISTANCE
            and policy._player_may_project(snapshot, grid.position, monster.position))


def _others_present(policy, snapshot, target: MonsterState) -> bool:
    return any(monster.position != target.position and (
                   monster.distance <= 1
                   or not immobile_threat_memory.never_moves(policy, monster))
               for monster in snapshot.visible_monsters if monster.hostile)


def plan(policy, snapshot, monster: MonsterState,
         shot_limit: int | None = SUMMONER_RANGED_KILL_SHOTS) -> KillPlan | None:
    """The safe ranged kill of ``monster`` (module docstring), else None.  ``shot_limit``
    None: any number of shots (a ring that blocks the way, ``blocking_key``)."""
    player = snapshot.player
    if (snapshot.in_town or player.blind or player.confused
            or policy._floor_navigation_exit_locked(snapshot)
            or policy._matching_ammo(snapshot) is None
            or _others_present(policy, snapshot, monster)
            or immobile_threat_memory.unaimed(policy, monster.position)):
        return None
    shots = policy._summoner_shots_to_kill(snapshot, monster)
    if shots is None or (shot_limit is not None and shots > shot_limit):
        return None
    here = snapshot.grid_at(player.position)
    if here is not None and _shooting_cell(policy, snapshot, monster, here):
        step, walk = None, 0
    elif immobile_threat_memory.walk_retired(policy, monster.position):
        return None
    else:
        route = _with_zone_released(policy, snapshot, lambda: policy._nearest_goal_route(
            snapshot, lambda grid: _shooting_cell(policy, snapshot, monster, grid)))
        if route is None:
            return None
        step, walk = route.first_step, route.remaining_edges + 1
    danger = policy.threat_prediction(
        snapshot, [monster], walk + shots, contact=True)["operational_total"]
    if danger >= player.hp:
        return None
    return KillPlan(monster, step)


def _with_zone_released(policy, snapshot, search):
    """Search with the immobile summoner's zone veto withdrawn (its cells are
    the shooting cells of a summoner that became killable)."""
    cells = getattr(policy, "_immobile_summoner_avoid_cells", set())
    if not cells:
        return search()
    policy._refresh_warning_avoidance(snapshot, released_cells=cells)
    try:
        return search()
    finally:
        policy._refresh_warning_avoidance(snapshot, added_cells=cells)


def _way_on_reached(policy, snapshot, through: frozenset) -> bool:
    """A walk over the routes (and ``through``) reaches a frontier or a way down."""
    start = snapshot.player.position
    seen = {start}
    queue = deque([start])
    while queue:
        position = queue.popleft()
        grid = snapshot.grids.get(position)
        if position != start and grid is not None and (
                grid.has_down_stairs or policy._is_frontier(snapshot, grid)):
            return True
        for neighbor in policy._walkable_neighbors(snapshot, position, through=through):
            if neighbor not in seen and neighbor not in policy._engagement_avoid_cells:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def closes_the_way(policy, snapshot, monster: MonsterState) -> bool:
    """The routes reach no frontier or way down, and would with this monster gone."""
    through = frozenset(
        (cell.y, cell.x) for cell in immobile_threat_memory.ring_cells(monster.position)
        if (grid := snapshot.grids.get(cell)) is not None and grid.passable)
    return (not _way_on_reached(policy, snapshot, frozenset())
            and _way_on_reached(policy, snapshot, through))


def _in_maze(policy, snapshot) -> bool:
    info = policy._dungeon_knowledge.get(snapshot.floor_key[0])
    return info is not None and "MAZE" in getattr(info, "flags", frozenset())


def _ring_through(policy, monster: MonsterState) -> frozenset:
    """The remembered walkable cells of ``monster``'s ring (its own cell too)."""
    floor = policy._remembered_floor_t
    return frozenset(key for cell in immobile_threat_memory.ring_cells(monster.position)
                     if (key := (cell.y, cell.x)) in floor)


def _remembered_way_on(policy, snapshot, through: frozenset) -> tuple[bool, frozenset]:
    """Whether a walk over the routes (and ``through``) reaches a remembered frontier or a
    stair the stuck walk would take, and the cells it reached."""
    stairs = policy._remembered_stair_goals(snapshot, not policy._descent_is_blocked(snapshot))
    start = snapshot.player.position
    seen = {start}
    queue = deque([start])
    found = False
    while queue:
        position = queue.popleft()
        if position != start and (position in stairs
                                  or policy._is_remembered_frontier(snapshot, position)):
            found = True
        for neighbor in policy._walkable_neighbors(snapshot, position, through=through):
            if neighbor not in seen and neighbor not in policy._engagement_avoid_cells:
                seen.add(neighbor)
                queue.append(neighbor)
    return found, frozenset(seen)


def _blocked_sides(policy, snapshot, monster: MonsterState):
    """The player's side and the ground past ``monster``'s ring when the ring is what
    leaves no frontier and no stair reachable (``retreat_enclosure.WalledOff``), else None."""
    if not immobile_threat_memory.ringed(policy, monster):
        return None
    reached, reach = _remembered_way_on(policy, snapshot, frozenset())
    if reached:
        return None
    through = _ring_through(policy, monster)
    reached, beyond = _remembered_way_on(policy, snapshot, through)
    if not reached:
        return None
    ring = immobile_threat_memory.ring_cells(monster.position)
    return retreat_enclosure.WalledOff(reach, frozenset(beyond - reach - ring))


def blocks_the_way(policy, snapshot, monster: MonsterState) -> bool:
    """In a maze, ``monster``'s ring leaves no remembered frontier and no stair reachable,
    and they would be with it gone (owner 2026-11-06)."""
    return _in_maze(policy, snapshot) and _blocked_sides(policy, snapshot, monster) is not None


def killable(policy, snapshot, monster: MonsterState) -> bool:
    """The immobile summoner owner keeps no zone for a monster killed this way: a
    kept-away never-moving one (``key`` shoots no other) with a safe ranged kill.

    A summoner avoided only because it did not come to the choke (summoner_wait's
    expired wait) moves; ``key`` never walks to shoot it, so withdrawing its zone hands
    the cells to every other owner with nothing carrying the kill out.  n1-c life-205
    (2026-11-13, ガラスの城60F): from (28,39) the two ノーム・メイジ sensed by telepathy
    read as killable (a third, asleep, out of range), their zone was withdrawn and the
    exploration stepped '1' back into (29,38), where the third was in view, the kill
    refused and the zone laid again ('9' out), eight times up to the oscillation break."""
    return kept_away(policy, snapshot, monster) and plan(policy, snapshot, monster) is not None


def key(policy, snapshot) -> str | None:
    """Shoot, or step toward the cell to shoot from, the nearest kept-away
    never-moving monster that can be killed safely from range."""
    if snapshot.in_town:
        return None
    visible = {monster.position: monster for monster in snapshot.visible_monsters}
    for monster in sorted(immobile_threat_memory.remembered(policy),
                          key=lambda monster: snapshot.player.position.distance_to(
                              monster.position)):
        if (not kept_away(policy, snapshot, monster)
                or disenchant_avoid.left_alone(policy, snapshot, monster, closes_the_way)):
            continue
        found = plan(policy, snapshot, monster)
        if found is None:
            continue
        answer = _carry_out(policy, snapshot, found, visible)
        if answer is not None:
            return answer
    return None


def _carry_out(policy, snapshot, found: KillPlan, visible: dict) -> str | None:
    """Step toward the shooting cell, or shoot from here; None when the monster is not
    in view from the shooting cell."""
    monster = found.target
    if found.step is not None:
        policy.last_reason = APPROACH_REASON
        immobile_threat_memory.note_walk(policy, monster.position, snapshot.player.position)
        policy._declare_reach(found.step)
        return policy._step_toward(snapshot, found.step)
    target = visible.get(monster.position)
    if target is None:
        # Out of sight from the shooting cell: nothing to aim at until
        # it is perceived again.
        immobile_threat_memory.mark_unaimed(policy, monster.position)
        return None
    return policy._ranged_attack_key(snapshot, [target], [])


def blocking_key(policy, snapshot) -> str | None:
    """Owner 2026-11-06 「先にその敵を倒す」 (module docstring): with nothing left to explore
    and no stair to take, shoot the never-moving monster whose ring blocks the way in a
    maze, any number of shots; when it cannot be killed so, the enclosure ladder."""
    if (snapshot.in_town or not _in_maze(policy, snapshot)
            or policy._floor_navigation_exit_locked(snapshot)):
        return None
    visible = {monster.position: monster for monster in snapshot.visible_monsters}
    for monster in sorted(immobile_threat_memory.remembered(policy),
                          key=lambda monster: snapshot.player.position.distance_to(
                              monster.position)):
        sides = _blocked_sides(policy, snapshot, monster)
        if sides is None:
            continue
        if not disenchant_avoid.left_alone(policy, snapshot, monster, blocks_the_way):
            found = plan(policy, snapshot, monster, shot_limit=None)
            if found is not None:
                answer = _carry_out(policy, snapshot, found, visible)
                if answer is not None:
                    return answer
        return retreat_enclosure.ring_ladder_key(policy, snapshot, sides)
    return None
