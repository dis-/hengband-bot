"""The hunted random-quest target or dungeon guardian while it is out of sight.

Owner 2026-11-02: 「ランダムクエスト討伐対象やガーディアンを討伐するとき、対象が
邪悪なら邪悪感知を用いて探すロジックが欲しい」, and 「全感知を使うケースは対象が
邪悪であることに拘らない」.

Recorded: n1-c life-103 (Lv30 Magic-Eater, Angband 24F, RANDOM quest 41, the
non-evil 『金のスニッチ』 race 1329) and n1-c life-098 (Lv21, Angband 12F,
RANDOM quest 43, the EVIL 鬼殺隊の『先輩』 race 1164) wandered their quest
floors without the target in sight until livelock:exhausted
(viewing-incidents-20261102).

The hunted race (``target_race``):
 - the runtime RANDOM / KILL_LEVEL quest occupying this floor without an
   approved fixed-map strategy (the race ``_locked_kill_quest_targets``
   fights: ``_quest_target_race_id``), unless it read T1 judged from contact when last
   shown (``_judge_quest_target``; a T1 gives the floor up, owner 2026-11-13);
 - else the final guardian of the target dungeon on its final floor, while the
   dungeon is not conquered and the kit can beat it (the floor the guardian
   rung ``_viable_target_guardian_visible`` fights on, its
   ``_guardian_fight_viable``).

A detection marks a monster for one player turn only
(core/player-processor.cpp, spells-detection.cpp keep_detected_monsters: MARK
falls on the next action without SHOW), so the cell the game showed is
remembered for this floor visit (fair play: the game displayed it) until the
player sees the cell empty, the certification immobile_threat_memory uses.
The search powers are the me_powers rows whose effect reveals the race
(``REVEALS``); ``route_key`` walks to the remembered cell, and the ordinary
combat and hunt rungs take over once the target is in their reach.

Recorded n1-a life-485 (Angband 38F, RANDOM quest 45, 2026-11-05 08:48): the
never-moving target showed along a corridor from 20 cells, the game's sight
limit, while the hunt rung reaches 8 and the ranged ladder 10.  The walk stopped
at the first sight, nothing else approached, seek-loot stepped back out of
sight, and the walk stepped in again until the loop detector stopped the bot.
So the walk asks the same question in and out of view (``_walk_ends_in_refusal``),
and one that would end in a refusal gives the cell up where it stands.

Recorded n1-b life-335 (Angband 24F, RANDOM quest 41, 2026-11-07 09:00 and 09:03):
the target 『アルベリヒ』 (race 419, INVISIBLE, TPORT) vanished beside the player.
The goal "a cell within 1 of the shown cell" never counts the player's own cell
(goal_route), so the walk stepped between two cells beside it until the loop
detector stopped the bot, and no board certified the cell empty: an INVISIBLE race
is never seen gone (``_player_can_see_empty_cell``).  So a walk that is already
beside the shown cell is done: it waits one turn there (``SEARCH_KEY``) and then
gives the cell up.  Recorded n1-b life-334 04:57 and life-335 09:03: two sleeping
Black ogres 8-9 away, or a Yeek 14 away, sent the walk back to seek-loot, which
stepped out of their sight, and the walk stepped in again.  A hostile the combat
rungs passed over that sleeps, or stands beyond ``HUNT_RANGE``, no longer stops the
walk -- unless its melee is one the engagement retreat keeps away from.

Recorded n1-c life-186 (Orc cave 23F, its final floor, 2026-11-10 02:29, build 7404002a7):
Detect Evil showed the guardian (race 373, lib/edit/DungeonDefinitions.jsonc:309) at [52,153]
past the explored ground, and the walk went to the nearest frontier "closer to it than the
player" (game distance, Grid::calc_distance, system/grid-type-definition.cpp:19-38): a bound
that moves with every step.  From [32,131] (30) the frontier was one through [33,132]; from
[33,132] (29) it was no longer closer, the walk turned to another back through [32,131], and
stepped '3' and '7' between the two cells, 38 times, until the loop detector.  (Replayed from
the capture with a fresh policy: [31,134] (29), chosen from [32,131], gave way to [33,135]
(27) from [33,132].)  The frontier the walk chose is now kept until the player stands on it
(then it is spent) or it stops being a frontier; once the player is as near the target as the
kept frontier, the walk spends the frontiers and gives the cell up, as when none is closer
(n1-a life-485 above), instead of turning to one closer than the new cell.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import retreat_enclosure
from hengbot.model import Position, game_distance
from hengbot.policy_constants import HUNT_RANGE, SEARCH_KEY
from hengbot.quest_knowledge import QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_RANDOM

MEMORY = "_hunt_target_memory"
REASON = "hunt:detected-target"
ARRIVED_REASON = "hunt:detected-target-arrived"
# The quest types whose target race is hunted on the quest floor (owner 2026-11-02).
HUNTED_QUEST_TYPES = frozenset({QUEST_TYPE_RANDOM, QUEST_TYPE_KILL_LEVEL})
# The monsters each detection effect marks (spell-kind/spells-detection.cpp:
# detect_monsters_evil marks kind_flags EVIL; detect_all runs
# detect_monsters_invis and detect_monsters_normal, every monster).
REVEALS = {
    "detect-evil": lambda flags: "EVIL" in flags,
    "detect-all": lambda flags: True,
}


@dataclass
class FloorVisit:
    floor: tuple
    race: int | None = None
    position: Position | None = None  # the cell the game last showed the target on
    # The frontiers known when the walk found none closer to the target: they are explore's,
    # however often a detection shows the target again (n1-a life-485: one step back made
    # the same frontier "closer", and seek-loot and the walk traded (21,121) and (22,121)).
    spent_frontiers: frozenset = frozenset()
    # The shown cell the walk already waited beside: the next board there gives it up.
    waited_beside: Position | None = None
    # The frontier the walk chose closer to ``frontier_goal`` than the player then was.
    frontier: Position | None = None
    frontier_goal: Position | None = None
    # The guardian's contact tier when last shown was not T2 or T3 (``_guardian_beatable``).
    guardian_declined: bool = False
    # The random-quest target read T1 when last shown (``_judge_quest_target``): not hunted,
    # and the floor is given up (``quest_target_unbeatable``).
    quest_unbeatable: bool = False


def _quest_race(policy, snapshot) -> int | None:
    quest_id = policy._active_kill_quest_id(snapshot)
    if quest_id is None or policy.approved_quest_strategy(quest_id) is not None:
        return None
    quest = snapshot.quests[quest_id]
    info = policy._quest_knowledge.get(quest_id)
    if (info.type if info is not None else quest.type) not in HUNTED_QUEST_TYPES:
        return None
    race = policy._quest_target_race_id(quest)
    return race if race is not None and race > 0 else None


def _guardian_race(policy, snapshot, *, judged: bool = True) -> int | None:
    """The guardian hunted here; ``judged`` False leaves out the tier verdict."""
    guardian_id = policy._target_guardian_floor_id(snapshot)
    if guardian_id is None or snapshot.floor_key[0] in snapshot.conquered_dungeon_ids:
        return None
    visit = _visit(policy, snapshot)
    if judged and visit is not None and visit.guardian_declined:
        return None
    info = policy._dungeon_knowledge[snapshot.floor_key[0]]
    return guardian_id if policy._guardian_fight_viable(snapshot, info) else None


def _guardian_beatable(policy, snapshot, guardian) -> bool:
    """Owner 2026-11-08 (question 4 of the n1-c life-171 report, verbatim 「勝てる段の時だけ
    追う」): the guardian is hunted only while its tier on its own, judged from contact, is T2
    or T3; T1 or undecided (the projection's cost cap) is not hunted.  n1-c life-171 (城65階)
    hunted 皇帝『レイザーク』 (Lv65, +25, contact tier undecided, no-supply damage at least 1345
    against HP 993) to three cells and died to its summons."""
    from hengbot import threat_tiers  # threat_tiers imports this module
    tier = threat_tiers.tiered(policy, snapshot, [guardian], contact=True).tier
    return tier in (threat_tiers.T2, threat_tiers.T3)


def _judge_quest_target(policy, snapshot, visit: FloorVisit, target) -> None:
    """Owner 2026-11-13 (the n1-c life-205 question 「ランダムクエストの討伐の標的が T1 と分かった
    時、どうしますか？」, answer 「階を諦めて帰還する」: 「T1 の標的と分かったら追わずに帰還を読み、
    クエストは失敗にする。標的が近づく前に離れる。」).  The quest target is judged from contact as
    the guardian is (``_guardian_beatable``); T1 (``threat_tiers.cannot_win``: a cost-capped
    reading whose no-supply damage is known to reach the HP is T1 too) is not hunted and gives
    the floor up (``quest_target_unbeatable``, the return owner's ``quest-unviable`` latch), at
    whatever distance the target is shown.

    Unlike the guardian, a reading past the cost cap with no such bound is still hunted: the
    quest floor's exit lock keeps the player there either way, and n1-a life-485 (38F RANDOM
    quest 45) shot the never-moving 『マニマニのあくま』 (race 1293, past the cap from contact)
    dead from range.  As the duel latch (``_visible_unviable_quest_target``), a board without
    the projection's inputs (no main-hand weapon or no blows) gives no verdict.

    n1-c life-205 (Angband 76F, RANDOM quest 42, 2026-11-13 01:31): 深淵の帝王『カントラス』 (race
    830, Lv84, unique, a QUESTOR: *Destruction* only heals and teleports it, spells-floor.cpp
    destroy_area) was walked toward by detection at T1 (decisions 2464-2467) until one step took
    the HP from 365 to 67."""
    from hengbot import threat_tiers  # threat_tiers imports this module
    weapon = next((item for item in snapshot.equipment if item.slot == "main_hand"), None)
    if weapon is None or snapshot.player.main_hand_blows <= 0:
        return
    reading = threat_tiers.tiered(policy, snapshot, [target], contact=True)
    visit.quest_unbeatable = threat_tiers.cannot_win(reading, snapshot.player.hp)


def quest_target_unbeatable(policy, snapshot) -> bool:
    """The random-quest target was shown on this floor visit as a T1 (``_judge_quest_target``)."""
    visit = _visit(policy, snapshot)
    return visit is not None and visit.quest_unbeatable and _quest_race(policy, snapshot) is not None


def target_race(policy, snapshot) -> int | None:
    """The race hunted on this floor, else None."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        return None
    quest_race = _quest_race(policy, snapshot)
    if quest_race is not None:
        visit = _visit(policy, snapshot)
        return None if visit is not None and visit.quest_unbeatable else quest_race
    return _guardian_race(policy, snapshot)


def _perceived(policy, snapshot, race: int) -> list:
    return [monster for monster in policy._sighted_or_detected_hostiles(snapshot)
            if monster.race_id == race]


def forget_floor_visit(policy) -> None:
    """A floor transition ends the visit (called beside the other per-visit resets)."""
    setattr(policy, MEMORY, None)


def observe(policy, snapshot) -> None:
    """Every dungeon decision: remember the shown target, retire a stale cell."""
    if snapshot.in_town:
        setattr(policy, MEMORY, None)
        return
    visit = getattr(policy, MEMORY, None)
    if visit is None or visit.floor != snapshot.floor_key:
        visit = FloorVisit(snapshot.floor_key)
        setattr(policy, MEMORY, visit)
    # Re-decided every board: a killed target ends the quest, a kit change the guardian hunt.
    # The guardian's tier is judged on each board that shows it; the verdict stands while
    # it is not shown.
    if (quest := _quest_race(policy, snapshot)) is not None:
        if shown_target := _perceived(policy, snapshot, quest):
            _judge_quest_target(policy, snapshot, visit,
                                min(shown_target, key=lambda monster: monster.distance))
    elif (guardian := _guardian_race(policy, snapshot, judged=False)) is not None:
        if shown_guardian := _perceived(policy, snapshot, guardian):
            visit.guardian_declined = not _guardian_beatable(
                policy, snapshot, min(shown_guardian, key=lambda monster: monster.distance))
    visit.race = target_race(policy, snapshot)
    if visit.race is None:
        visit.position = None
        return
    shown = _perceived(policy, snapshot, visit.race)
    if shown:
        visit.position = min(shown, key=lambda monster: monster.distance).position
    elif visit.position is not None and (
            visit.position == snapshot.player.position
            or policy._player_can_see_empty_cell(snapshot, visit.position, race_id=visit.race)):
        visit.position = None


def _visit(policy, snapshot) -> FloorVisit | None:
    visit = getattr(policy, MEMORY, None)
    return visit if visit is not None and visit.floor == snapshot.floor_key else None


def unseen_race(policy, snapshot) -> int | None:
    """The hunted race when the game shows it nowhere and no shown cell is kept."""
    visit = _visit(policy, snapshot)
    if visit is None or visit.race is None or visit.position is not None:
        return None
    return None if _perceived(policy, snapshot, visit.race) else visit.race


def race_flags(policy, race: int) -> frozenset:
    return getattr(policy._monrace_knowledge.get(race), "flags", frozenset())


def _walk_ends_in_refusal(policy, snapshot, target) -> bool:
    """The target is in sight, and walking on would only reach a rung that refuses it.

    The combat and hunt rungs answered this board first, so a target inside their
    reach is one they turned down.  Past it, the walk goes on when the ranged ladder
    or the hunt rung will take the target at the end of the walk."""
    return target.distance <= HUNT_RANGE or not (
        policy._has_usable_ranged_option(snapshot)
        or policy._hunt_would_close(snapshot, target))


def _holds_the_walk(policy, snapshot, monster, race) -> bool:
    """Another hostile in sight that the combat rungs own: awake within HUNT_RANGE, or,
    awake or asleep, one whose melee the engagement retreat keeps away from (owner
    2026-11-07 「眠っていても強い敵からは離れる」: ``_material_melee_fight``), so the
    walk never steps toward the retreat's own threat."""
    if monster.race_id == race:
        return False
    if not monster.asleep and monster.distance <= HUNT_RANGE:
        return True
    return policy._material_melee_fight(snapshot, monster)


def _instant_death_ahead(policy, snapshot) -> bool:
    """3.1 即死 holds on this board (``threat_tiers.instant_death``: the engagement, sensed
    monsters included, deals the HP or more in the next player action), outside a quest plan
    (there the plan's own 即死 rung, ``threat_tiers.instant_death_key``, answers).  No step is
    taken toward the target then.  n1-c life-205 decision 2467 (Angband 76F, 2026-11-13 01:31):
    next_action_p95 408 against HP 365 with カントラス detected two cells off, and the walk
    stepped toward it; the next board read 67 HP."""
    if policy.approved_quest_strategy(snapshot.floor_key[2]) is not None:
        return False
    from hengbot import threat_tiers  # threat_tiers imports this module
    return threat_tiers.instant_death(policy, snapshot).holds


def _frontier_step(policy, snapshot, visit: FloorVisit, goal: Position) -> Position | None:
    """The step toward the frontier the walk keeps (``FloorVisit.frontier``), else toward a new
    one closer to ``goal`` than the player, kept from this board on; None with neither.

    A kept frontier the player has come as near the target as is spent with the others (None):
    the walk does not turn to another frontier closer than the new cell, which is the bound
    that moved (n1-c life-186), and gives the cell up as when none is closer (n1-a life-485)."""
    here = snapshot.player.position
    distance = game_distance(here, goal)
    if visit.frontier == here:
        visit.spent_frontiers |= {here}
        visit.frontier = None
    kept = visit.frontier
    if kept is not None and visit.frontier_goal == goal and kept not in visit.spent_frontiers:
        grid = snapshot.grids.get(kept)
        if grid is not None and policy._is_frontier(snapshot, grid):
            if game_distance(kept, goal) >= distance:
                visit.frontier = visit.frontier_goal = None
                return None
            step = policy._nearest_goal_step(snapshot, lambda grid: grid.position == kept)
            if step is not None:
                return step
    visit.frontier = visit.frontier_goal = None
    route = policy._nearest_goal_route(
        snapshot, lambda grid: game_distance(grid.position, goal) < distance
        and grid.position not in visit.spent_frontiers
        and policy._is_frontier(snapshot, grid))
    if route is None:
        return None
    visit.frontier, visit.frontier_goal = route.target, goal
    return route.first_step


def route_key(policy, snapshot, hostiles) -> str | None:
    """The step toward the cell the target was last shown on, else None.

    Only while no other hostile in sight holds the walk (``_holds_the_walk``) and the
    character was not just hit (the combat rungs own those boards) and no town return is running.  A detection
    reaches past the explored ground, so when no known route reaches the cell
    the walk goes to the nearest exploration frontier closer to it than the
    player (``_is_frontier``, the explore walk's own goal test); with neither,
    the cell is given up and the next search follows the me_powers spacing
    rule.  When the floor's retreat vetoes are what closes the way,
    retreat_enclosure.walled_off_key answers first."""
    visit = _visit(policy, snapshot)
    if (visit is None or visit.position is None
            or any(_holds_the_walk(policy, snapshot, monster, visit.race) for monster in hostiles)
            or getattr(policy, "_took_damage", False) or policy._returning_to_town
            or _instant_death_ahead(policy, snapshot)):
        return None
    targets = [monster for monster in hostiles if monster.race_id == visit.race]
    if targets and _walk_ends_in_refusal(
            policy, snapshot, min(targets, key=lambda monster: monster.distance)):
        visit.position = None
        return None
    goal = visit.position
    if snapshot.player.position.distance_to(goal) <= 1:
        # Beside the shown cell the walk is done: one turn's wait for what is
        # there to show itself, then the cell is given up.
        if visit.waited_beside == goal:
            visit.position = None
            visit.waited_beside = None
            return None
        visit.waited_beside = goal
        policy.last_reason = ARRIVED_REASON
        return SEARCH_KEY
    step = policy._nearest_goal_step(
        snapshot, lambda grid: grid.position.distance_to(goal) <= 1)
    if step is None:
        step = _frontier_step(policy, snapshot, visit, goal)
    else:
        visit.frontier = visit.frontier_goal = None
    if step is None:
        visit.spent_frontiers |= {position for position, grid in snapshot.grids.items()
                                  if policy._is_frontier(snapshot, grid)}
        visit.position = None
        return retreat_enclosure.walled_off_key(policy, snapshot)
    policy.last_reason = REASON
    policy._declare_reach(goal)
    return policy._step_toward(snapshot, step)
