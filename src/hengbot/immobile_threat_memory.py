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

Owner 2026-11-02 (immobile-weak-kill-1102): 「弱い動かない敵まで避けると不具合が
大きそうなので遠距離攻撃、召喚魔法がなければ普通に倒して」 -- a never-moving
monster without a ranged attack or a summon spell (``is_avoidable_immobile``)
is an ordinary enemy: its touch alone no longer rings it or makes the
engagement gate retreat from it (``fought_normally``).  The survival rings
stay: a one-turn lethal contact and a stat-draining blow (owner 11-01 21h)
are kept until the owner says otherwise.  「遠距離で安全に倒せるなら倒す方を
優先する」: every never-moving monster that is still kept away from is shot
when the bot can kill it safely from range (immobile_ranged_kill).

Owner 2026-11-05 (disenchant_avoid): a never-moving monster that disenchants an
unresisting player is ringed as well.

Owner 2026-11-06 「脅威が見えなくなったら消す」 (retreat_veto_life): a remembered
monster is also forgotten when it died or changed shape -- its floor list index
shows another race, or its kill or shape-change line follows a board it was shown
on (``retreat_veto_life.seen_or_ended``).  Recorded n1-c life-156 (Labyrinth 10F,
2026-11-06 23:0x): a レッド・ゼリー at (10,42) was shot dead from (13,42) (turn
1033667, 「レッド・ゼリーは死んだ。」), but on the forgetting maze its cell three
away stayed unlit, so the empty-cell test never certified it gone; its ring kept
cutting the one-wide junction and sealed the explored east from every frontier and
both known stairs (442 stuck:wander).  The retreat veto's third lifting condition
(not shown for a while) is not applied here: a never-moving monster not shown is
still where it was shown (owner 11-01 「その階の間覚えて」).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import disenchant_avoid, retreat_veto_life
from hengbot.model import MonsterState, Position
from hengbot.monrace_knowledge import SUMMON_ABILITIES
from hengbot.policy_constants import NEIGHBOR_OFFSETS, ExplorationPathOutcome

MEMORY = "_immobile_threat_memory"
PREDICTION_TURNS = 1
STEP_OUT_REASON = "immobile-threat:step-out"
# The blow effects that lower a stat (race-info-tokens-table.cpp:72-78).
STAT_DRAIN_BLOW_EFFECTS = frozenset({
    "LOSE_STR", "LOSE_INT", "LOSE_WIS", "LOSE_DEX", "LOSE_CON", "LOSE_CHR", "LOSE_ALL",
})
# The abilities outside the game's attack masks (race-ability-mask.cpp:81-88
# RF_ABILITY_ATTACK_MASK): RF_ABILITY_INDIRECT_MASK (101-105) less its
# summons, and SPECIAL.  Every other ability -- bolts, beams, balls, breaths,
# arrows, rockets and the spells aimed at the player (SCARE, SLOW, HOLD,
# TELE_TO, DRAIN_MANA, ...) -- is a ranged attack.
NON_ATTACK_ABILITIES = frozenset({
    "SHRIEK", "HASTE", "HEAL", "INVULNER", "BLINK", "WORLD", "TPORT", "RAISE_DEAD", "SPECIAL",
})


@dataclass
class FloorVisit:
    floor: tuple
    monsters: dict[Position, MonsterState] = field(default_factory=dict)
    cells: frozenset[Position] = frozenset()
    # Remembered monsters not in view from a reached shooting cell
    # (immobile_ranged_kill), until perceived again.
    unaimed: set[Position] = field(default_factory=set)
    # The cells each target's walk to a shooting cell stepped from, the targets
    # whose walk came back to one of them, and the player's cell on the last board.
    walked_from: dict[Position, set[Position]] = field(default_factory=dict)
    walk_retired: set[Position] = field(default_factory=set)
    last_cell: Position | None = None
    # Who each remembered monster is (its floor list index and race) and the
    # board it was last shown on, for its kill or shape change; the previous
    # observed board.
    threats: dict[Position, tuple] = field(default_factory=dict)
    last_turn: int | None = None


def never_moves(policy, monster: MonsterState) -> bool:
    """The race knowledge says the monster never leaves its cell (NEVER_MOVE)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "NEVER_MOVE" in knowledge.flags


def has_ranged_attack(knowledge) -> bool:
    """The race casts or shoots something at the player from a distance."""
    return any(ability not in NON_ATTACK_ABILITIES and ability not in SUMMON_ABILITIES
               for ability in knowledge.abilities)


def is_avoidable_immobile(policy, monster: MonsterState) -> bool:
    """A never-moving monster with a ranged attack or a summon spell (owner
    2026-11-02): the only kind the avoidance mechanisms keep away from, apart
    from the survival rings (``avoided``)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return (knowledge is not None and "NEVER_MOVE" in knowledge.flags
            and (knowledge.can_summon or has_ranged_attack(knowledge)))


def fought_normally(policy, snapshot, monster: MonsterState) -> bool:
    """A never-moving monster no avoidance applies to: no ring, no retreat,
    no detour -- the ordinary combat ladder fights it (owner 2026-11-02)."""
    return (never_moves(policy, monster) and not is_avoidable_immobile(policy, monster)
            and not avoided(policy, snapshot, monster))


def _lethal(policy, snapshot, monster: MonsterState) -> bool:
    prediction = policy.threat_prediction(
        snapshot, [monster], PREDICTION_TURNS, contact=True)
    return prediction["operational_total"] >= snapshot.player.hp


def _drains_stats(policy, monster: MonsterState) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and any(
        blow.effect in STAT_DRAIN_BLOW_EFFECTS for blow in knowledge.blows)


def avoided(policy, snapshot, monster: MonsterState) -> bool:
    """A remembered never-moving monster whose ring leaves the routes.

    A never-moving summoner that drains (キリス・ウンゴルの番人) stays the
    immobile-summoner owner's (``_immobile_summoner_key``), which already
    keeps out of its sight and fights it when no retreat is left.  A
    ranged never-moving monster whose touch the engagement gate counts as
    material (``_material_melee_damage``) is passed around by its ring
    instead of retreated from at a distance (shoot-immobile-sleeper-1102);
    without a ranged attack its touch alone is fought (owner 2026-11-02)."""
    if monster.can_summon:
        return _lethal(policy, snapshot, monster)
    return (_drains_stats(policy, monster) or _lethal(policy, snapshot, monster)
            or disenchant_avoid.kept_away(policy, snapshot, monster)
            or (is_avoidable_immobile(policy, monster)
                and policy._material_melee_damage(snapshot, monster)))


def ring_cells(position: Position) -> set[Position]:
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
    _retire_returned_walks(visit, snapshot.player.position)
    perceived = {monster.position: monster
                 for monster in policy._perceived_hostiles(snapshot)
                 if never_moves(policy, monster)}
    visit.monsters.update(perceived)
    visit.unaimed.difference_update(perceived)
    _forget_ended(visit, snapshot, perceived)
    for position, monster in list(visit.monsters.items()):
        if position not in perceived and policy._player_can_see_empty_cell(
                snapshot, position, race_id=monster.race_id):
            del visit.monsters[position]
    visit.cells = frozenset() if policy._floor_navigation_exit_locked(snapshot) else frozenset(
        cell
        for position, monster in visit.monsters.items()
        if avoided(policy, snapshot, monster)
        for cell in ring_cells(position)
    )
    _drop_committed_paths(policy, visit.cells)


def _forget_ended(visit: FloorVisit, snapshot, perceived: dict) -> None:
    """Forget the remembered monsters that died or changed shape (owner 2026-11-06)."""
    threats = visit.__dict__.setdefault("threats", {})  # restored checkpoints predate it
    last_turn = visit.__dict__.get("last_turn")
    shown = retreat_veto_life.shown_by_index(snapshot)
    for position, monster in list(visit.monsters.items()):
        if position in perceived:
            threats[position] = (
                (monster.index, monster.race_id),
                retreat_veto_life.Threat(monster.name, snapshot.turn))
            continue
        entry = threats.get(position)
        if entry is None:
            continue
        key, threat = entry
        if retreat_veto_life.seen_or_ended(snapshot, key, threat, shown, last_turn):
            del visit.monsters[position]
            del threats[position]
            visit.unaimed.discard(position)
    for position in set(threats) - set(visit.monsters):
        del threats[position]
    visit.last_turn = snapshot.turn


def remembered(policy) -> tuple[MonsterState, ...]:
    """Every never-moving monster this floor visit remembers (avoided or not)."""
    visit = getattr(policy, MEMORY, None)
    return () if visit is None else tuple(visit.monsters.values())


def mark_unaimed(policy, position: Position) -> None:
    """The monster at ``position`` was not in view from a reached shooting cell."""
    visit = getattr(policy, MEMORY, None)
    if visit is not None:
        visit.unaimed.add(position)


def unaimed(policy, position: Position) -> bool:
    """Not in view from a reached shooting cell, and not perceived since."""
    visit = getattr(policy, MEMORY, None)
    return visit is not None and position in visit.unaimed


def note_walk(policy, target: Position, cell: Position) -> None:
    """This decision steps from ``cell`` toward a cell to shoot the monster at ``target``."""
    visit = getattr(policy, MEMORY, None)
    if visit is not None:
        visit.walked_from.setdefault(target, set()).add(cell)


def _retire_returned_walks(visit: FloorVisit, cell: Position) -> None:
    """A player back on a cell a walk stepped from: that walk ends in no shot.
    A step that did not move the player (a door, a refused step) is no return."""
    if cell != visit.last_cell:
        visit.walk_retired.update(target for target, cells in visit.walked_from.items()
                                  if cell in cells)
    visit.last_cell = cell


def walk_retired(policy, position: Position) -> bool:
    """This floor visit no longer walks to shoot it (it may still be shot from where
    the player stands, and it stays avoided)."""
    visit = getattr(policy, MEMORY, None)
    return visit is not None and position in visit.walk_retired


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
    return step_out_of(policy, snapshot, cells, STEP_OUT_REASON)


def step_out_of(policy, snapshot, cells, reason: str) -> str | None:
    """The step toward the nearest free cell outside ``cells``, labelled ``reason``.

    None when the current routing reaches no such cell.  Shared by the ring
    above and the immobile summoner's line-of-fire zone
    (``CombatMixin._immobile_summoner_key``)."""
    step = policy._nearest_goal_step(
        snapshot, lambda grid: grid.passable and not grid.has_monster
        and grid.position not in cells)
    if step is None:
        return None
    policy.last_reason = reason
    policy._declare_reach(step)
    return policy._step_toward(snapshot, step)


def _drop_committed_paths(policy, cells: frozenset[Position]) -> None:
    if not cells:
        return
    if any(step in cells for step in policy._explore_path):
        policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
    if any(step in cells for step in policy._nav_ledger.descent_path):
        policy._nav_ledger.replace_descent_path(())
