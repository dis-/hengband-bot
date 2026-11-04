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
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import immobile_threat_memory
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
            and policy._may_project(snapshot, grid.position, monster.position))


def _others_present(policy, snapshot, target: MonsterState) -> bool:
    return any(monster.position != target.position and (
                   monster.distance <= 1
                   or not immobile_threat_memory.never_moves(policy, monster))
               for monster in snapshot.visible_monsters if monster.hostile)


def plan(policy, snapshot, monster: MonsterState) -> KillPlan | None:
    """The safe ranged kill of ``monster`` (module docstring), else None."""
    player = snapshot.player
    if (snapshot.in_town or player.blind or player.confused
            or policy._floor_navigation_exit_locked(snapshot)
            or policy._matching_ammo(snapshot) is None
            or _others_present(policy, snapshot, monster)
            or immobile_threat_memory.unaimed(policy, monster.position)):
        return None
    shots = policy._summoner_shots_to_kill(snapshot, monster)
    if shots is None or shots > SUMMONER_RANGED_KILL_SHOTS:
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


def killable(policy, snapshot, monster: MonsterState) -> bool:
    """The immobile summoner owner keeps no zone for a monster killed this way."""
    return plan(policy, snapshot, monster) is not None


def key(policy, snapshot) -> str | None:
    """Shoot, or step toward the cell to shoot from, the nearest kept-away
    never-moving monster that can be killed safely from range."""
    if snapshot.in_town:
        return None
    visible = {monster.position: monster for monster in snapshot.visible_monsters}
    for monster in sorted(immobile_threat_memory.remembered(policy),
                          key=lambda monster: snapshot.player.position.distance_to(
                              monster.position)):
        if not kept_away(policy, snapshot, monster):
            continue
        found = plan(policy, snapshot, monster)
        if found is None:
            continue
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
            continue
        return policy._ranged_attack_key(snapshot, [target], [])
    return None
