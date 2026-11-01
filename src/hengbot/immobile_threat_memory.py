"""Never-moving monsters perceived on this floor visit, and the cells beside
those whose one-turn damage is lethal or whose blows drain a stat (#47 D57,
n1-c life-079; survival2-1101, n1-c life-092).

Owner 2026-11-01 (memory d57-survival-answers-decision-20261101, question 3):
「その階の間覚えて隣を避ける」 -- remember a detected monster that never moves
for as long as the floor visit lasts, and when its one-turn damage can kill
the player, take its cell and the cells beside it out of every route.

Recorded n1-c life-079 (Angband 12F, 2026-11-01 04:28): the absorbed Detect
Evil showed a デスソード (race 107, NEVER_MOVE, speed +20, SLASH 5d5 x2) at
(14,63) on the board of turn 600499.  The game drops a detection mark on the
next player turn (core/player-processor.cpp:363-378; the next board's
``detected_monsters`` is empty), nobody kept it, and the descent route of
turns 600521-600610 stepped to (13,62) beside it: HP 151 -> -2 in one step.

Remembering a monster the player was shown is fair play: the game displayed
it.  A NEVER_MOVE monster stays where it was shown
(monster-floor/monster-move.cpp:430), so its cell is remembered until the
player sees the cell empty (the certification the paralyzer and
immobile-summoner memories use).  "Lethal" is the combat ladder's own
one-turn prediction from contact (``threat_prediction(..., turns=1,
contact=True)["operational_total"]``) at or above the current HP.  On a floor
whose exit is locked (a quest) no cell is removed: retreat is impossible
there, so the existing fight owners decide.

The route cells are removed from the per-decision walk index
(``policy_navigation._build_grid_index``), so every router that walks the
index -- descent, exploration, loot, flight, hunting -- prices them alike,
and a committed explore or descent path through a cell is dropped.

Owner 2026-11-01 21h (memory owner-answers-9-decisions-20261101, answer 1):
「近づかずに避ける」 -- a never-moving monster whose blows drain a stat
(赤いジェリーなど) is avoided like an immobile summoner; firing at it from a
distance stays allowed, and where retreat is impossible it is fought as
today.  Recorded: n1-c life-092 (Angband 14F, turn 1065156) hunted a レッド・
ゼリー (race 131, NEVER_MOVE, TOUCH:LOSE_STR) at (16,86) to the cell beside
it and was drained eight times; n1-b life-287 (a warrior, Labyrinth 15F, turn
929114) hunted a sleeping one and was drained twice; n1-c life-096 lost STR
18/31 -> 6 the same way.  A stat-drain blow lowers the stat unless it is
sustained (monster-attack-switcher.cpp:466-486 -> do_dec_stat,
status/base-status.cpp:209).  Its touch reaches only the cells beside it, so
the same ring leaves the routes, and a player already standing in a ring
steps out of it (``step_out_key``) before the combat rungs answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot.claim_goal_typing import GOAL_NOTE_ONE_STEP
from hengbot.model import MonsterState, Position
from hengbot.policy_constants import NEIGHBOR_OFFSETS, ExplorationPathOutcome

MEMORY = "_immobile_threat_memory"
PREDICTION_TURNS = 1
STEP_OUT_REASON = "immobile-threat:step-out"
# The blow effects that lower a stat (race-info-tokens-table.cpp:72-78).
STAT_DRAIN_BLOW_EFFECTS = frozenset({
    "LOSE_STR", "LOSE_INT", "LOSE_WIS", "LOSE_DEX", "LOSE_CON", "LOSE_CHR", "LOSE_ALL",
})


@dataclass
class FloorVisit:
    floor: tuple
    monsters: dict[Position, MonsterState] = field(default_factory=dict)
    cells: frozenset[Position] = frozenset()


def never_moves(policy, monster: MonsterState) -> bool:
    """The race knowledge says the monster never leaves its cell (NEVER_MOVE)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "NEVER_MOVE" in knowledge.flags


def _lethal(policy, snapshot, monster: MonsterState) -> bool:
    prediction = policy.threat_prediction(
        snapshot, [monster], PREDICTION_TURNS, contact=True)
    return prediction["operational_total"] >= snapshot.player.hp


def _drains_stats(policy, monster: MonsterState) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and any(
        blow.effect in STAT_DRAIN_BLOW_EFFECTS for blow in knowledge.blows)


def _avoided(policy, snapshot, monster: MonsterState) -> bool:
    """A remembered never-moving monster whose ring leaves the routes.

    A never-moving summoner that drains (キリス・ウンゴルの番人) stays the
    immobile-summoner owner's (``_immobile_summoner_key``), which already
    keeps out of its sight and fights it when no retreat is left.  A
    monster whose touch the engagement gate counts as material
    (``_material_melee_damage``) is passed around by its ring instead of
    retreated from at a distance (shoot-immobile-sleeper-1102)."""
    if monster.can_summon:
        return _lethal(policy, snapshot, monster)
    return (_drains_stats(policy, monster) or _lethal(policy, snapshot, monster)
            or policy._material_melee_damage(snapshot, monster))


def _ring(position: Position) -> set[Position]:
    return {position, *(Position(position.y + dy, position.x + dx)
                        for dy, dx in NEIGHBOR_OFFSETS)}


def forget_floor_visit(policy) -> None:
    """A floor transition ends the visit (called beside the other per-visit resets)."""
    setattr(policy, MEMORY, None)


def observe(policy, snapshot) -> None:
    """Every dungeon decision: remember, retire, and price the route cells."""
    visit = getattr(policy, MEMORY, None)
    if snapshot.in_town:
        setattr(policy, MEMORY, None)
        return
    if visit is None or visit.floor != snapshot.floor_key:
        visit = FloorVisit(snapshot.floor_key)
        setattr(policy, MEMORY, visit)
    perceived = {monster.position: monster
                 for monster in policy._perceived_hostiles(snapshot)
                 if never_moves(policy, monster)}
    visit.monsters.update(perceived)
    for position, monster in list(visit.monsters.items()):
        if position not in perceived and policy._player_can_see_empty_cell(
                snapshot, position, race_id=monster.race_id):
            del visit.monsters[position]
    visit.cells = frozenset() if policy._floor_navigation_exit_locked(snapshot) else frozenset(
        cell
        for position, monster in visit.monsters.items()
        if _avoided(policy, snapshot, monster)
        for cell in _ring(position)
    )
    _drop_committed_paths(policy, visit.cells)


def route_cells(policy) -> frozenset[Position]:
    """The cells this floor visit's avoided never-moving monsters take out of routes."""
    visit = getattr(policy, MEMORY, None)
    return frozenset() if visit is None else visit.cells


def ringed(policy, monster: MonsterState) -> bool:
    """Its ring already leaves this floor visit's routes: routing passes around it."""
    visit = getattr(policy, MEMORY, None)
    return (visit is not None and monster.position in visit.monsters
            and monster.position in visit.cells)


def step_out_key(policy, snapshot) -> str | None:
    """Standing in a ring: the step to the nearest free cell outside it, else None.

    None also when no such cell is reachable; the combat rungs then fight as
    before (a ring is never set on a floor whose exit is locked)."""
    cells = route_cells(policy)
    if snapshot.player.position not in cells:
        return None
    step = policy._nearest_goal_step(
        snapshot, lambda grid: grid.passable and not grid.has_monster
        and grid.position not in cells)
    if step is None:
        return None
    policy.last_reason = STEP_OUT_REASON
    policy._declare_reach(step, note=GOAL_NOTE_ONE_STEP)
    return policy._step_toward(snapshot, step)


def _drop_committed_paths(policy, cells: frozenset[Position]) -> None:
    if not cells:
        return
    if any(step in cells for step in policy._explore_path):
        policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
    if any(step in cells for step in policy._nav_ledger.descent_path):
        policy._nav_ledger.replace_descent_path(())
