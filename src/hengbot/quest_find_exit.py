"""A FIND_EXIT quest's floor: walk to the exit, fighting at chokes one by one.

``engagement_plan.find_exit`` on an approved strategy is the data:

 * ``choke_cells``: the cells to stand on while an awake enemy is about, chosen from
   the map (QUEST_18's plan gives its reasons);
 * ``choke_hold_turns``: how long one choke waits for an enemy that does not come;
 * ``rest_below_ratio``: below this HP the quiet floor is rested on before walking on.

``engagement_plan.sealed_races`` are monsters no route reaches; they count for nothing
here nor in the acceptance projection.

Game (C:/hengband/src, player-move.cpp:256): stepping on the QUEST_EXIT of a FIND_EXIT
quest completes it there and then and leaves the floor; no stair command is sent, and
a Word of Recall under way is cancelled (word_recall = 0).  Nothing needs killing.

Owner 2026-11-04, Q18: 「狭い閉鎖空間であるため、隔離されているクラーケン二種以外との戦闘は
基本的には回避できない。隘路で各個撃破することを目標とする。」 and for an emergency
「薬で戦い線より下で帰還」: at the choke with Healing and Speed potions, and below the
strategy's line (``abort_conditions.hp_ratio``) with an enemy, Recall is read and the
fight goes on with potions and blows until it fires.  Cure Critical Wounds is no HP
recovery (owner 2026-11-03).  With no enemy the floor is rested on (owner 2026-11-03).

``key`` runs before the shared survival ladders while an enemy is about on such a
floor: their answers walk away from the choke, which is what this plan refuses.  A
quiet board stays with them (food, light, the unseen) and reaches ``walk_key`` through
the navigator.
"""

from __future__ import annotations

from hengbot import combat_answer, once_quest_recall, speed_dose, status_cure
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


def _never_moves(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "NEVER_MOVE" in knowledge.flags


def _pulls(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "TELE_TO" in knowledge.abilities


def _rank(profile, monster) -> tuple[int, int]:
    targets = profile.priority_targets
    index = targets.index(monster.race_id) if monster.race_id in targets else len(targets)
    return index, monster.hp


class _Board:
    """The enemies of one board, as this plan weighs them."""

    def __init__(self, policy, snapshot, profile):
        sealed = sealed_races(profile)
        position = snapshot.player.position
        known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                 if monster.hostile and monster.race_id not in sealed]
        self.in_view = [monster for monster in known if monster.perception != "detected"]
        self.occupied = {monster.position for monster in known}
        # A monster that cannot come is no reason to hold a choke; one beside the player
        # is left behind by walking on (a siren's pull ends beside it, 840 HP unfought).
        self.mobile_awake = [monster for monster in known if not monster.asleep
                             and not _never_moves(policy, monster)]
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
    return {Position(*cell) for cell in plan["choke_cells"]} - navigator.exit_spent_chokes


def _hold(policy, snapshot, navigator, plan, position, board) -> str | None:
    """Wait on this choke for what comes; a shot first.  None once its wait is spent."""
    if navigator.exit_hold_cell != position:
        navigator.exit_hold_cell, navigator.exit_hold_turns = position, 0
    navigator.exit_hold_turns += 1
    if navigator.exit_hold_turns > int(plan["choke_hold_turns"]):
        navigator.exit_spent_chokes = navigator.exit_spent_chokes | {position}
        return None
    shot = (policy._ranged_attack_key(snapshot, board.coming_in_view, [])
            if board.coming_in_view else None)
    if shot is not None:
        return shot
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _to_choke(policy, snapshot, navigator, plan, board) -> str | None:
    """Stand on the nearest choke still worth waiting on; None when there is none."""
    position = snapshot.player.position
    chokes = _chokes(navigator, plan)
    if position in chokes:
        held = _hold(policy, snapshot, navigator, plan, position, board)
        if held is not None:
            return held
        chokes = _chokes(navigator, plan)
    path = navigator._static_path(position, chokes, blocked=board.occupied)
    if len(path) < 2:
        return None
    policy.last_reason = TO_CHOKE_REASON
    policy._declare_reach(path[-1])
    return policy._step_toward(snapshot, path[1])


def _advance(policy, snapshot, navigator, board) -> str | None:
    """A step toward the exit, round a monster when that is a sidestep; else it is struck.

    Rubble is dug only when no water leads on: a dig is turns spent on one cell.
    """
    position, exit_cell = snapshot.player.position, _exit_cell(navigator)
    rubble = {Position(*cell) for cell, kind in navigator.battlefield.terrain.items()
              if kind == "rubble"}
    through = (navigator._static_path(position, {exit_cell}, blocked=rubble)
               or navigator._static_path(position, {exit_cell}))
    around = navigator._static_path(position, {exit_cell}, blocked=board.occupied | rubble)
    path = around if around and len(around) <= len(through) + SIDESTEP_LIMIT else through
    if len(path) < 2:
        return None
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
    """The board with an enemy about, or with HP to rest back; None leaves it shared."""
    plan = _plan(policy, snapshot)
    if plan is None or snapshot.player.food_state in STARVING:
        return None
    quest_id = snapshot.floor_key[2]
    profile = policy.approved_quest_strategy(quest_id)
    navigator = _navigator(policy, snapshot, quest_id)
    board = _Board(policy, snapshot, profile)
    if not board.enemy_for_the_line:
        return (
            _step_on_exit(policy, snapshot, navigator, board)
            or _rest(policy, snapshot, plan, board)
            or (_to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None)
            or (_advance(policy, snapshot, navigator, board) if board.in_view else None)
        )
    return (
        _step_on_exit(policy, snapshot, navigator, board)
        or _below_line_recall(policy, snapshot, profile)
        or (_engaged(policy, snapshot, profile, navigator, plan, board) if board.engaged else None)
        or _advance(policy, snapshot, navigator, board)
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
        target = min(board.adjacent_mobile, key=lambda monster: _rank(profile, monster))
        answer = combat_answer.adjacent_attack(policy, snapshot, [target], MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
        # A blow the game refuses (fear) and no missile: the choke is still the place.
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    return _to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None


def walk_key(policy, snapshot) -> str | None:
    """A quiet board on such a floor, through the navigator: walk on."""
    plan = _plan(policy, snapshot)
    if plan is None:
        return None
    quest_id = snapshot.floor_key[2]
    navigator = _navigator(policy, snapshot, quest_id)
    board = _Board(policy, snapshot, policy.approved_quest_strategy(quest_id))
    return (_step_on_exit(policy, snapshot, navigator, board)
            or _advance(policy, snapshot, navigator, board))
