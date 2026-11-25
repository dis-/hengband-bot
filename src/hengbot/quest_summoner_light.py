"""A plan's summoner in a dark room: lit by the plan's light, then walked to or shot by the higher figure.

QUEST_32 (ダークエルフの王) ``engagement_plan.summoner_light`` = ``{"race": 263, "area": "西の中部屋"}``.

Owner 2026-11-26 (n1-a life-538, Zombie warrior Lv30: 27 summons by 何か in Q32 between turns
1312077 and 1314967, 14 of 15 Teleportation scrolls read -- summons:leave-teleport 9 --, one
閾に棲む者 of six killed):

 1. 「戦士も光の巻物で部屋を照らす」: the warrior lights the dark west middle room with the plan's
    Scroll of Light (``light_areas``, one per area; until then only the Magic-Eater's shot read
    them, quest_light_areas), so the summoner is an enemy in view, and walks to it and strikes.
    「見えた召喚者には『見えない召喚が2回で離れる』を当てない」 (summon-response-decision-20261104
    rule 2): the casts counted in the dark were the room's, and with the plan's summoner in view
    the leave does not come (``spares_leave``).
 2. 「期待値の高い方（殴る）」: where the summoner can be shot, the shot and the walk to it and the
    blows are compared by expected damage per 10 game turns, the walk's time included (owner
    2026-11-19 「攻撃力の判定を…10ゲームターンあたりのダメージで評価して」), and the higher is
    taken (``walks_to``).  n1-a life-538 at [15,6] (turn 1314500): arrows 62 a turn at the
    閾に棲む者 at [10,1] (summoner:ranged-kill), the melee turn about 497.

When the light is read (``light_key``): the summoner race is not in view, the area is not read on
this floor, and either a summon by 何か is on this board, or the player stands in the area.  The
game's side (C:/hengband/src, spell-kind/spells-lite.cpp ``lite_room``): the read floods CAVE_GLOW
from the player's cell over every CAVE_ROOM cell joined through LOS terrain; every cell of the
Q32 map is ROOM (lib/edit/quests/032_DarkElvenLords.jsonc), and a caster casts only along its
line to the player (a projectable path of LOS cells), so a read on the board of the unseen cast
reaches the caster's cell, and the caster on a glowing cell in the player's line is seen
(update_monster).  The area is marked read in ``_quest_light_areas_read`` (quest_light_areas: one
scroll per area, the Magic-Eater's shot in the area reads no second one).

The walk (``walks_to``): ``steps`` is the walk model's (``_walkable_neighbors``) to a cell beside
the target; the blows' turn then lands after ``steps`` moves, so the
walk-and-strike figure per action is the melee figure over ``steps + 1`` actions; the shot's is
the shot's own (the rounds the ranged rung fires, ``_ranged_projectile``: n1-a life-538 fired its
plain arrows, 62 a turn, not the 破邪の矢 it carried; the Magic-Eater's devices, the larger).
Both are read per 10 game turns at the board's speed.  No path: the shot.  Not the plan's
summoner race, or no plan with the field: no say (the shot rungs as before).

The plan walks to its never-moving races (``engage_never_move_races``), so on its floor they are
no stationary summoner to keep away from (``engaged``): policy_combat ``_immobile_summoner_key``
vetoed the cells in their line of fire for every route and, the quest floor having no exit, shot
them (n1-a life-538 at [15,6], 1314500-1314511, three arrows at the 閾に棲む者 at [10,1]).
"""

from __future__ import annotations

from collections import deque

from hengbot import attack_expectation, summon_response
from hengbot.model import Position

FIELD = "summoner_light"
LIGHT_REASON = "quest-strategy:summoner-light"
WALK_REASON = "quest-strategy:summoner-walk"
# Q32's map is 21 x 9: a longer walk is no walk to the target.
WALK_LIMIT = 30


def valid(value, areas) -> bool:
    """The schema of ``summoner_light``: a positive race and the name of a ``light_areas`` row."""
    names = {row.get("name") for row in areas or () if isinstance(row, dict)}
    return (isinstance(value, dict)
            and isinstance(value.get("race"), int) and not isinstance(value.get("race"), bool)
            and value["race"] > 0 and value.get("area") in names)


def _plan(policy, snapshot):
    """(profile, field) of this floor's approved plan naming ``summoner_light``, else None."""
    quest_id = snapshot.floor_key[2]
    if not quest_id or snapshot.in_town:
        return None
    profile = policy.approved_quest_strategy(quest_id)
    if profile is None:
        return None
    field = profile.engagement_plan.get(FIELD)
    return (profile, field) if isinstance(field, dict) else None


def _summoners_in_view(snapshot, race: int) -> list:
    return [monster for monster in snapshot.visible_monsters
            if monster.hostile and monster.race_id == race and monster.perception != "detected"]


def _bounds(profile, area: str):
    return next((row["bounds"] for row in profile.engagement_plan.get("light_areas", ())
                 if row.get("name") == area), None)


def _inside(bounds, position: Position) -> bool:
    top, left, bottom, right = bounds
    return top <= position.y <= bottom and left <= position.x <= right


def _unseen_summon(snapshot) -> bool:
    return any(not summon.seen for message in snapshot.messages
               for summon in summon_response.summons_of(message))


def light_key(policy, snapshot) -> str | None:
    """The plan's light for the summoner's room when it is due (module docstring), else None."""
    found = _plan(policy, snapshot)
    if found is None:
        return None
    profile, field = found
    race, area = int(field["race"]), field["area"]
    spent = (snapshot.floor_key, area)
    if spent in policy._quest_light_areas_read or _summoners_in_view(snapshot, race):
        return None
    bounds = _bounds(profile, area)
    if not (_unseen_summon(snapshot)
            or (bounds is not None and _inside(bounds, snapshot.player.position))):
        return None
    if not policy._can_read_scrolls(snapshot):
        return None
    light = policy._quest_light_key(snapshot, LIGHT_REASON)
    if light is not None:
        policy._quest_light_areas_read.add(spent)
        # The casts counted in the dark were the room's: the room is lit (owner 2026-11-26).
        summon_response.end_unseen_run(policy)
    return light


def spares_leave(policy, snapshot) -> bool:
    """The plan's summoner is in view: rule 2's leave does not come (owner 2026-11-26)."""
    found = _plan(policy, snapshot)
    return found is not None and bool(_summoners_in_view(snapshot, int(found[1]["race"])))


def steps_beside(policy, snapshot, target, limit: int = WALK_LIMIT) -> int | None:
    """The fewest moves of the walk model (``_walkable_neighbors``, the board's eight ways) from the
    player to a cell beside ``target``; None without a walk within ``limit``."""
    here = snapshot.player.position
    seen, frontier = {here}, deque([(here, 0)])
    while frontier:
        cell, steps = frontier.popleft()
        if cell.distance_to(target.position) <= 1:
            return steps
        if steps >= limit:
            continue
        for neighbor in policy._walkable_neighbors(snapshot, cell):
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append((neighbor, steps + 1))
    return None


def engaged(policy, snapshot, monster) -> bool:
    """A never-moving race a plan with ``summoner_light`` walks to (``engage_never_move_races``):
    not a summoner to keep away from (policy_combat ``_immobile_summoner_key``)."""
    return engaged_race(policy, snapshot, monster.race_id)


def engaged_race(policy, snapshot, race_id: int) -> bool:
    found = _plan(policy, snapshot)
    return found is not None and race_id in found[0].engagement_plan.get("engage_never_move_races", ())


def shot_figure(policy, snapshot, target) -> float:
    """The shot's expected damage per action: the rounds the ranged rung fires
    (``_ranged_projectile``), and for the classes of ``one_turn_kill.device_classes`` (the
    Magic-Eater) its devices, the larger."""
    from hengbot import quest_one_turn_kill

    distance = snapshot.player.position.distance_to(target.position)
    chosen = policy._ranged_projectile(snapshot)
    shot = (attack_expectation.ammo_against(policy, snapshot, target.race_id, chosen[1], distance)
            if chosen is not None and chosen[0] == "fire" else 0.0)
    found = _plan(policy, snapshot)
    required = quest_one_turn_kill.requirement(found[0].required_force) if found is not None else None
    if required is not None and snapshot.player.class_id in required.get("device_classes", ()):
        shot = max(shot, attack_expectation.devices_against(policy, snapshot, target.race_id))
    return shot


def figures(policy, snapshot, target) -> dict | None:
    """{"shot", "walk_and_strike", "steps"} per 10 game turns for the plan's summoner, else None."""
    found = _plan(policy, snapshot)
    if found is None or target.race_id != int(found[1]["race"]):
        return None
    steps = steps_beside(policy, snapshot, target)
    shot = attack_expectation.per_10_game_turns(policy, snapshot, shot_figure(policy, snapshot, target))
    if steps is None:
        return {"shot": shot, "walk_and_strike": None, "steps": None}
    strike = attack_expectation.melee_against(policy, snapshot, target.race_id)
    walk = attack_expectation.per_10_game_turns(policy, snapshot, strike / (steps + 1))
    return {"shot": shot, "walk_and_strike": walk, "steps": steps}


def walks_to(policy, snapshot, target) -> bool:
    """Walking to the plan's summoner and striking beats shooting it (module docstring)."""
    if snapshot.player.afraid:   # the blows are refused: the shot stays
        return False
    found = figures(policy, snapshot, target)
    return (found is not None and found["walk_and_strike"] is not None
            and found["walk_and_strike"] > found["shot"])


def engage_key(policy, snapshot, profile, hostiles) -> str | None:
    """The plan's summoner in view, by the higher figure (``figures``): the step toward it, or the
    shot at it; on toward the kept cell while the walk is kept (quest_sweep_target's kept target,
    its race the plan's summoner: released once the cell is seen empty); None otherwise.

    The target is the summoner in view of the highest figure, the nearer on a tie.  The walk is kept
    across the boards on which the summoner is out of view (owner 2026-11-13 「離れたマスの共通の
    記録」): a step that loses the line to it does not hand the board back to the hold's retake, the
    alternation of n1-a life-538 (quest_sweep_target's docstring).  The shot is the ranged rung's
    (``_ranged_attack_key``): the plan's summoner is no summoner kept away from (``engaged``), so
    no other rung shoots it."""
    from hengbot import quest_sweep_target

    found = _plan(policy, snapshot)
    if found is None:
        return None
    race = int(found[1]["race"])
    rows = []
    for monster in hostiles:
        if monster.race_id != race or monster.perception == "detected":
            continue
        row = figures(policy, snapshot, monster)
        walk = None if snapshot.player.afraid else row["walk_and_strike"]
        best = max(row["shot"], walk or 0.0)
        rows.append((-best, snapshot.player.position.distance_to(monster.position), monster,
                     walk is not None and walk > row["shot"]))
    for _best, _distance, target, walking in sorted(rows, key=lambda row: row[:2]):
        if walking:
            step = policy._quest_strategy_route_step(snapshot, profile, target.position)
            if step is not None:
                setattr(policy, quest_sweep_target.COMMIT_ATTRIBUTE,
                        (snapshot.floor_key, race, target.position))
                policy.last_reason = WALK_REASON
                return policy._step_toward(snapshot, step)
        adjacent = [monster for monster in hostiles if monster.distance <= 1]
        if not adjacent and target.distance >= 2:
            shot = policy._town_producer_entry(
                "_ranged_attack_key", lambda target=target: policy._ranged_attack_key(snapshot, [target], []))
            if shot is not None:
                return shot
    if rows:
        return None
    commit = getattr(policy, quest_sweep_target.COMMIT_ATTRIBUTE, None)
    if commit is None or commit[0] != snapshot.floor_key or commit[1] != race or snapshot.player.afraid:
        return None
    step = quest_sweep_target.committed_step(policy, snapshot, profile, [])
    if step is None:
        return None
    policy.last_reason = WALK_REASON
    return policy._step_toward(snapshot, step)
