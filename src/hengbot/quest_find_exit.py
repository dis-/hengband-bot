"""A FIND_EXIT quest's floor: walk to the exit, fighting at chokes one by one.

``engagement_plan.find_exit`` on an approved strategy is the data:

 * ``choke_cells``: the cells to stand on while an awake enemy is about, chosen from
   the map (QUEST_18's plan gives its reasons);
 * ``choke_hold_turns``: how long one choke waits for an enemy that does not come;
 * ``rest_below_ratio``: below this HP the quiet floor is rested on before walking on.

``engagement_plan.sealed_races`` are monsters no route reaches; they count for nothing
here.  ``find_exit.exposure_races`` are never-moving casters: the cells their spells reach
are derived from the map (quest_exposure).  Owner 2026-11-04 「叫びを受ける位置を特定して
可能な限り避ける」: the walk takes the fewest such cells, nobody holds, rests or fights by
choice on one, and on one the walk goes on to the next free cell unless a monster
is in the only way.  A shriek wakes the whole floor and hastes every monster the player
has in view (spells-sight.cpp aggravate_monsters); n1-a took 47 of them on one cell and died.

Game (C:/hengband/src, player-move.cpp:256): stepping on the QUEST_EXIT of a FIND_EXIT
quest completes it there and then and leaves the floor; no stair command is sent, and
a Word of Recall under way is cancelled (word_recall = 0).  Nothing needs killing.

Owner 2026-11-04, Q18: 「狭い閉鎖空間であるため、隔離されているクラーケン二種以外との戦闘は
基本的には回避できない。隘路で各個撃破することを目標とする。」 and for an emergency
「薬で戦い線より下で帰還」: at the choke with Healing and Speed potions, and below the
strategy's line (``abort_conditions.hp_ratio``) with an enemy, Recall is read and the
fight goes on with potions and blows until it fires.  Cure Critical Wounds is no HP
recovery (owner 2026-11-03).  With no enemy the floor is rested on (owner 2026-11-03).

Owner 2026-11-04 「隘路で敵を十分倒してから先に進むことを明記する」: on an unexposed choke
nothing advances while ``comes_for_player`` holds for an awake enemy in view, or one known
beside the next leg.  ``choke_hold_turns`` ends only a wait with no such enemy, the quiet
wait after a fight on that choke; ``choke_enemy_wait_turns`` is the far bound on an enemy
that stays in view without ever making contact (a blow resets it).  With nothing fought or
known, the walk goes on at once.  An enemy that does not come does not freeze the walk: it
is shot from the choke when it stands in the way, otherwise passed.  A sleeper stays asleep
unless it is in the way or beside the next choke.

``key`` runs before the shared survival ladders while an enemy is about on such a
floor: their answers walk away from the choke, which is what this plan refuses.  A
quiet board stays with them (food, light, the unseen) and reaches ``walk_key`` through
the navigator.
"""

from __future__ import annotations

from hengbot import combat_answer, once_quest_recall, quest_exposure, speed_dose, status_cure
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, SV_POTION_HEALING
from hengbot.policy_constants import HEAL_POTION_SVALS, REST_MACRO, WAIT_KEY
from hengbot.quest_navigator import QuestFloorNavigator

MELEE_REASON = "quest-strategy:melee"
HOLD_REASON = "quest-strategy:hold"
TO_CHOKE_REASON = "quest-strategy:exit-to-choke"
WALK_REASON = "quest-strategy:exit-walk"
STEP_ON_EXIT_REASON = "quest-strategy:exit-step"
RECALL_REASON = "emergency:recall-quest-fail"
HEAL_REASON = "quest-strategy:heal"
CURE_REASON = "quest-strategy:cure"
SPEED_REASON = "quest-strategy:quaff-speed"
_PLANNED_STEPS = frozenset({TO_CHOKE_REASON, WALK_REASON, STEP_ON_EXIT_REASON})
STARVING = frozenset({"weak", "fainting"})
# Going round a monster on the way costs at most this many steps, else it is fought.
SIDESTEP_LIMIT = 2
PERMANENT_HASTE_SPEED = 120
DEFAULT_SPEED_RATIO = 0.5


def _plan(policy, snapshot) -> dict | None:
    """The plan of the TAKEN quest on this floor; a completed one has left the floor."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    return None if profile is None else profile.engagement_plan.get("find_exit")


def holds_choke(policy, snapshot) -> bool:
    """This board's wait is a choke hold of such a floor: under fire it still holds."""
    return policy.last_reason == HOLD_REASON and _plan(policy, snapshot) is not None


def planned_step(policy, snapshot) -> bool:
    """This board's step is the plan's own: the low-HP walk gate does not rewrite it."""
    return policy.last_reason in _PLANNED_STEPS and _plan(policy, snapshot) is not None


def sealed_races(profile) -> frozenset[int]:
    return frozenset(profile.engagement_plan.get("sealed_races", ()))


def _navigator(policy, snapshot, quest_id: int) -> QuestFloorNavigator:
    navigator = policy._quest_navigators.setdefault(
        quest_id, QuestFloorNavigator(quest_id, policy._quest_knowledge[quest_id].battlefield))
    navigator.allow_deep_water = True  # hp-mp-processor.cpp:210 drowns only the overweight
    navigator.allow_diagonal = True
    navigator.reset_for_floor(snapshot.floor_key)
    return navigator


_EXPOSURES: dict[tuple[int, tuple[int, ...]], quest_exposure.Exposure] = {}


def _exposure(navigator, plan) -> quest_exposure.Exposure:
    """The cells the plan's casters reach, derived once from the quest map."""
    races = tuple(plan.get("exposure_races", ()))
    key = (navigator.quest_id, races)
    if key not in _EXPOSURES:
        battlefield = navigator.battlefield
        _EXPOSURES[key] = quest_exposure.exposure_map(
            battlefield.terrain,
            [cell for cell, race in battlefield.monster_placements if race in races])
    return _EXPOSURES[key]


def _cell(position: Position) -> tuple[int, int]:
    return position.y, position.x


def _never_moves(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "NEVER_MOVE" in knowledge.flags


def _pulls(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "TELE_TO" in knowledge.abilities


def comes_for_player(policy, navigator, snapshot, monster) -> bool:
    """Awake, not NEVER_MOVE, and with a walk to beside the player for its kind of
    movement (an aquatic one in a sealed pocket has none)."""
    if monster.asleep or _never_moves(policy, monster):
        return False
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    flags = knowledge.flags if knowledge is not None else frozenset()
    return quest_exposure.can_reach(navigator.battlefield.terrain, flags,
                                    _cell(monster.position), _cell(snapshot.player.position))


def _rank(profile, monster) -> tuple[int, int]:
    targets = profile.priority_targets
    index = targets.index(monster.race_id) if monster.race_id in targets else len(targets)
    return index, monster.hp


class _Board:
    """The enemies of one board, as this plan weighs them."""

    def __init__(self, policy, snapshot, profile, navigator):
        sealed = sealed_races(profile)
        position = snapshot.player.position
        known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                 if monster.hostile and monster.race_id not in sealed]
        self.in_view = [monster for monster in known if monster.perception != "detected"]
        self.occupied = {monster.position for monster in known}
        # A monster that cannot come is no reason to hold a choke; one beside the player
        # is left behind by walking on (a siren's pull ends beside it, 840 HP unfought).
        self.mobile_awake = [monster for monster in known
                             if comes_for_player(policy, navigator, snapshot, monster)]
        self.coming_in_view = [monster for monster in self.mobile_awake
                               if monster.perception != "detected"]
        self.adjacent_mobile = [monster for monster in self.coming_in_view
                                if monster.position.distance_to(position) <= 1]
        # A never-moving puller (a siren's TELE_TO) in view: no place to rest, and an
        # enemy for the line, but the answer to it is to walk out of its sight.
        self.pulling = [monster for monster in self.in_view
                        if not monster.asleep and _never_moves(policy, monster)
                        and _pulls(policy, monster)]
        self.hit_by_unseen = once_quest_recall._hit_by_unseen(policy, snapshot)

    @property
    def engaged(self) -> bool:
        """Something can act on the player now: the potions and the fight are for this."""
        return bool(self.coming_in_view or self.hit_by_unseen)

    @property
    def enemy_for_the_line(self) -> bool:
        return self.engaged or bool(self.pulling)


def _exit_cell(navigator) -> Position:
    return Position(*navigator.battlefield.exit)


def _step_on_exit(policy, snapshot, navigator, board) -> str | None:
    """The exit beside the player and free: the quest is done and the danger behind."""
    exit_cell = _exit_cell(navigator)
    if (snapshot.player.position.distance_to(exit_cell) > 1
            or exit_cell in board.occupied):
        return None
    policy.last_reason = STEP_ON_EXIT_REASON
    return policy._step_toward(snapshot, exit_cell)


def _healing_potion(policy, snapshot):
    """HP recovery on this floor: Healing, or stronger; never Cure Critical."""
    return policy._find_exact_potion(snapshot, SV_POTION_HEALING) or policy._first_item(
        snapshot, lambda item: item.is_potion and item.aware and item.sval in HEAL_POTION_SVALS
        and item.sval > SV_POTION_HEALING)


def _below_line_recall(policy, snapshot, profile) -> str | None:
    line = profile.abort_conditions.get("hp_ratio")
    if line is None or snapshot.player.hp_ratio > float(line):
        return None
    if snapshot.player.blind or snapshot.player.confused:
        return _cure(policy, snapshot)  # the scroll cannot be read until it is cured
    return once_quest_recall.read_key(policy, snapshot, RECALL_REASON)


def _cure(policy, snapshot) -> str | None:
    if not (snapshot.player.blind or snapshot.player.confused):
        return None
    potion = status_cure.cure_potion(policy, snapshot)
    if potion is None:
        return None
    policy.last_reason = CURE_REASON
    return reserved_item_command(policy, snapshot, "quaff", potion)


def _heal(policy, snapshot, profile) -> str | None:
    threshold = profile.consumable_plan.get("heal_threshold_ratio")
    if threshold is None or snapshot.player.hp_ratio >= float(threshold):
        return None
    potion = _healing_potion(policy, snapshot)
    if potion is None:
        return None
    policy.last_reason = HEAL_REASON
    return reserved_item_command(policy, snapshot, "quaff", potion)


def _speed(policy, snapshot, profile, board) -> str | None:
    """Haste while it is off, for a row that lives by it, else when the fight is heavy."""
    if (not board.coming_in_view or policy._player_hasted(snapshot)
            or snapshot.player.speed >= PERMANENT_HASTE_SPEED):
        return None
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    if not force.get("always_hasted"):
        ratio = float(profile.consumable_plan.get("speed_potion_use_when", {}).get(
            "expected_damage_hp_ratio_min", DEFAULT_SPEED_RATIO))
        projected = policy.threat_prediction(snapshot, board.coming_in_view, turns=3)
        if projected["operational_total"] < ratio * snapshot.player.hp:
            return None
    return speed_dose.key(policy, snapshot, SPEED_REASON)


def _chokes(navigator, plan) -> set[Position]:
    exposure = _exposure(navigator, plan)
    return {Position(*cell) for cell in plan["choke_cells"]
            if not exposure.exposed(tuple(cell))} - navigator.exit_spent_chokes


def _next_leg(navigator, plan, position: Position) -> list[Position]:
    """The walk ahead up to and including the next choke."""
    chokes = {Position(*cell) for cell in plan["choke_cells"]}
    leg = []
    for cell in _least_exposed(navigator, plan, position, {_exit_cell(navigator)})[1:]:
        leg.append(cell)
        if cell in chokes:
            break
    return leg


def _must_wait(navigator, plan, position, board) -> bool:
    """An awake enemy that comes is in view, or known beside the next leg."""
    if board.coming_in_view:
        return True
    leg = _next_leg(navigator, plan, position)
    return any(monster.position.distance_to(cell) <= 1
               for monster in board.mobile_awake for cell in leg)


def _hold(policy, snapshot, navigator, plan, position, board) -> str | None:
    """Wait on this choke for what comes; a shot first.  None once its wait is spent."""
    if navigator.exit_hold_cell != position:
        navigator.exit_hold_cell, navigator.exit_hold_turns = position, 0
        navigator.exit_enemy_turns = 0
    if _must_wait(navigator, plan, position, board):
        navigator.exit_fought_at = position
        navigator.exit_hold_turns = 0
        navigator.exit_enemy_turns += 1
        spent = navigator.exit_enemy_turns > int(plan["choke_enemy_wait_turns"])
    else:
        navigator.exit_hold_turns += 1
        spent = navigator.exit_hold_turns > int(plan["choke_hold_turns"])
    if spent:
        navigator.exit_spent_chokes = navigator.exit_spent_chokes | {position}
        navigator.exit_fought_at = None
        return None
    shot = (policy._ranged_attack_key(snapshot, board.coming_in_view, [])
            if board.coming_in_view else None)
    if shot is not None:
        return shot
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _wait_after_fight(policy, snapshot, navigator, plan, board) -> str | None:
    """Nothing in sight on the choke that fought: what the noise woke may still come."""
    position = snapshot.player.position
    if navigator.exit_fought_at != position or position in navigator.exit_spent_chokes:
        return None
    return _hold(policy, snapshot, navigator, plan, position, board)


def _clear_the_way_key(policy, snapshot, navigator, plan, board, path) -> str | None:
    """From a choke, a shot at what stands in the walk ahead and will not come, or sleeps
    in it or beside the next choke.  No shot to be had: the walk goes on."""
    position = snapshot.player.position
    chokes = {Position(*cell) for cell in plan["choke_cells"]}
    if position not in chokes or _exposure(navigator, plan).exposed(_cell(position)):
        return None
    leg = []
    for cell in path[1:]:
        leg.append(cell)
        if cell in chokes:
            break
    next_choke = leg[-1] if leg and leg[-1] in chokes else None
    targets = [
        monster for monster in board.in_view
        if not _never_moves(policy, monster) or monster.position in leg
    ]
    targets = [
        monster for monster in targets
        if monster.position in leg
        or (monster.asleep and next_choke is not None
            and monster.position.distance_to(next_choke) <= 1)
    ]
    return policy._ranged_attack_key(snapshot, targets, []) if targets else None


def _to_choke(policy, snapshot, navigator, plan, board) -> str | None:
    """Stand on the nearest choke still worth waiting on; None when there is none."""
    position = snapshot.player.position
    chokes = _chokes(navigator, plan)
    if position in chokes:
        held = _hold(policy, snapshot, navigator, plan, position, board)
        if held is not None:
            return held
        chokes = _chokes(navigator, plan)
    path = _least_exposed(navigator, plan, position, chokes, board.occupied)
    if len(path) < 2:
        return None
    policy.last_reason = TO_CHOKE_REASON
    policy._declare_reach(path[-1])
    return policy._step_toward(snapshot, path[1])


def _least_exposed(navigator, plan, start: Position, goals, blocked=()) -> list[Position]:
    path = quest_exposure.least_exposed_path(
        navigator.battlefield.terrain, _exposure(navigator, plan), _cell(start),
        {_cell(goal) for goal in goals}, frozenset(_cell(cell) for cell in blocked))
    return [Position(*cell) for cell in path]


def _exposed_count(navigator, plan, path: list[Position]) -> int:
    exposure = _exposure(navigator, plan)
    return sum(exposure.exposed(_cell(cell)) for cell in path)


def _advance(policy, snapshot, navigator, plan, board) -> str | None:
    """A step of the least exposed walk to the exit, round a monster when that exposes no
    more and is a sidestep; else it is struck."""
    position, exit_cell = snapshot.player.position, _exit_cell(navigator)
    through = _least_exposed(navigator, plan, position, {exit_cell})
    around = _least_exposed(navigator, plan, position, {exit_cell}, board.occupied)
    path = around if (
        around and len(around) <= len(through) + SIDESTEP_LIMIT
        and _exposed_count(navigator, plan, around) <= _exposed_count(navigator, plan, through)
    ) else through
    if len(path) < 2:
        return None
    shot = _clear_the_way_key(policy, snapshot, navigator, plan, board, path)
    if shot is not None:
        return shot
    step = path[1]
    if step in board.occupied:
        blocker = next((monster for monster in board.in_view if monster.position == step), None)
        if blocker is None:
            policy.last_reason = HOLD_REASON
            return WAIT_KEY
        return combat_answer.strike_key(policy, snapshot, blocker, MELEE_REASON)
    policy.last_reason = WALK_REASON
    policy._declare_reach(exit_cell)
    return policy._step_toward(snapshot, step)


def _rest(policy, snapshot, plan, board) -> str | None:
    """Below the plan's ratio on a board with nothing to answer: rest, however low."""
    player = snapshot.player
    if (player.hp_ratio >= float(plan["rest_below_ratio"]) or player.confused or board.pulling
            or player.food_state not in {"normal", "full", "gorged"}):
        return None
    policy.last_reason = "rest"
    return REST_MACRO


def key(policy, snapshot) -> str | None:
    """The board with an enemy about, or with HP to rest back, or on a cell the casters
    reach; None leaves it shared."""
    plan = _plan(policy, snapshot)
    if plan is None or snapshot.player.food_state in STARVING:
        return None
    quest_id = snapshot.floor_key[2]
    profile = policy.approved_quest_strategy(quest_id)
    navigator = _navigator(policy, snapshot, quest_id)
    board = _Board(policy, snapshot, profile, navigator)
    exposed = _exposure(navigator, plan).exposed(_cell(snapshot.player.position))
    stepped = _step_on_exit(policy, snapshot, navigator, board)
    if stepped is not None:
        return stepped
    if exposed:
        # Survival first, then out of their reach: no hold, rest or chosen fight here.
        return (
            (_below_line_recall(policy, snapshot, profile) if board.enemy_for_the_line else None)
            or (_heal(policy, snapshot, profile) if board.engaged else None)
            or _advance(policy, snapshot, navigator, plan, board)
        )
    if not board.enemy_for_the_line:
        return (
            _rest(policy, snapshot, plan, board)
            or (_to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None)
            or _wait_after_fight(policy, snapshot, navigator, plan, board)
            or (_advance(policy, snapshot, navigator, plan, board) if board.in_view else None)
        )
    return (
        _below_line_recall(policy, snapshot, profile)
        or (_engaged(policy, snapshot, profile, navigator, plan, board) if board.engaged else None)
        or _advance(policy, snapshot, navigator, plan, board)
    )


def _engaged(policy, snapshot, profile, navigator, plan, board) -> str | None:
    return (
        _cure(policy, snapshot)
        or _heal(policy, snapshot, profile)
        or _speed(policy, snapshot, profile, board)
        or _fight(policy, snapshot, profile, navigator, plan, board)
    )


def _fight(policy, snapshot, profile, navigator, plan, board) -> str | None:
    if board.adjacent_mobile:
        _note_contact(navigator, plan, snapshot.player.position)
        target = min(board.adjacent_mobile, key=lambda monster: _rank(profile, monster))
        answer = combat_answer.adjacent_attack(policy, snapshot, [target], MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
        # A blow the game refuses (fear) and no missile: the choke is still the place.
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    moved = _to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None
    if moved is None and board.coming_in_view and not _spent_here(navigator, snapshot):
        # No choke to be had: it is still fought here, not walked into.
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    return moved


def _spent_here(navigator, snapshot) -> bool:
    return snapshot.player.position in navigator.exit_spent_chokes


def _note_contact(navigator, plan, position: Position) -> None:
    """A blow on a choke: its waits start over and it is worth waiting on again."""
    if [position.y, position.x] in plan["choke_cells"]:
        navigator.exit_hold_cell = position
        navigator.exit_hold_turns = navigator.exit_enemy_turns = 0
        navigator.exit_fought_at = position
        navigator.exit_spent_chokes = navigator.exit_spent_chokes - {position}


def walk_key(policy, snapshot) -> str | None:
    """A quiet board on such a floor, through the navigator: walk on."""
    plan = _plan(policy, snapshot)
    if plan is None:
        return None
    quest_id = snapshot.floor_key[2]
    navigator = _navigator(policy, snapshot, quest_id)
    board = _Board(policy, snapshot, policy.approved_quest_strategy(quest_id), navigator)
    return (_step_on_exit(policy, snapshot, navigator, board)
            or _wait_after_fight(policy, snapshot, navigator, plan, board)
            or _advance(policy, snapshot, navigator, plan, board))
