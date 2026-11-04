"""A KILL_ALL floor walked room by room: ``engagement_plan.room_sweep``.

The data (QUEST_25 gives the reasons of its cells):

 * ``stands``: the cells walked in order; ``meet_turns`` waits there for what comes;
   ``read_light`` lights the room from there, once a round, enemy or none (the shared
   ``_quest_light_key``: a Scroll of Light, or class 16's absorbed Light as on Q2);
 * ``last_targets``: what is left until every stand has been walked, each with its
   ``race``, ``cell``, closed ``door`` and the ``stand`` that opens the door and shoots;
 * ``line_races``: never-moving casters whose direct line every walk crosses as little
   as it can, and on which nobody rests or waits by choice (Q18's first fights, 2026-11-04:
   n1-a died standing on a cell under fire);
 * ``enemy_wait_turns``: the far bound on a coming enemy that stays in view without a
   shot or a blow; ``rest_below_ratio``: rest below this on a quiet floor;
 * ``max_rounds``: full walks with the quest still open before the plan stops by name;
 * ``exit_when_out_of_healing``: see below.

Q25 owner 2026-11-04.  「手のドルジは最後に回して戻って撃つ」: everything else first, then the
door and the shot; teleported away, the same stand is walked back to with no limit on
attempts (a stand ends only when reached).  「テレポートで立て直すだけ」: below the line
(``abort_conditions.hp_ratio``) Recall is not read: Teleportation, then a potion after a
teleport that still left an enemy on the player.  ``abort_conditions.recall_below_teleports``:
below that many scrolls, with an enemy about, Recall is read and the fight goes on
(once_quest_recall.below_scroll_floor, which keeps every other recall rung held too).  Cure
Critical Wounds is no HP recovery (owner 2026-11-03).  A quiet floor is rested on at any HP
(owner 2026-11-03).

The stair leaves and fails the quest (quest.cpp leave_quest_check).  Owner 2026-11-04
「薬を使い切っていたら踏んで良い」: taken only at PANIC_HP_RATIO or below (the ladder's own
life-threat line) with an enemy about, no Healing left, and a walk of at most
ITEM_DESTROYING_BREEDER_STAIR_DISTANCE steps (the ladder's distance for a stair under threat).

Owner 2026-11-04 「光の巻物を読む」: the floor is dark, so the hall is lit from its mouth to
be shot from afar.

Game facts this rests on (C:/hengband/src).  TELE_AWAY and TELE_TO need the caster's direct
line to the player's own cell (mspell-attack.cpp check_thrown_mspell lists both as aimed-off
refusals; decide_lite_projection): quest_exposure's ``pull`` map is that line.  The player's
shot needs the player's line and a monster he sees (target_able).  ``quest_exposure`` shows
no cell on Q25 that has the player's line to a quylthulg without its line back, so the quyls
are shot from in their line and first of all, walking in by the cells with the fewest lines.

A cell the weapon warning refused (warning.cpp process_warning; the latch is the policy's) is
no step while a movement scroll remains (owner: 物資が全て尽きている場合のみ徒歩強行を許す).
Every walk here goes round it, and a stop reached only over it is passed for this round.

``key`` runs before the shared survival ladders while an enemy is about: they walk away and
read Recall, which is what this plan refuses.  A quiet board stays with them (food, light,
the unseen) and reaches ``walk_key`` through the navigator.  A leave already decided (a
breeder stalemate, starvation) leaves the board to them.
"""

from __future__ import annotations

from hengbot import combat_answer, me_ranged_first, once_quest_recall, quest_exposure, quest_find_exit
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, TVAL_POTION
from hengbot.policy_constants import (
    ITEM_DESTROYING_BREEDER_STAIR_DISTANCE,
    PANIC_HP_RATIO,
    QUEST_POTION_SVALS,
    UP_STAIRS_KEY,
    WAIT_KEY,
)
from hengbot.quest_find_exit import HOLD_REASON, MELEE_REASON, RECALL_REASON
from hengbot.quest_navigator import QuestFloorNavigator

WALK_REASON = "quest-strategy:sweep-walk"
OPEN_REASON = "quest-strategy:sweep-open-door"
APPROACH_REASON = "quest-strategy:sweep-approach"
TELEPORT_REASON = "quest-strategy:sweep-teleport"
RESTORE_REASON = "quest-strategy:sweep-restore"
NOTHING_LEFT_REASON = "quest:blocked:sweep-nothing-left"
LIGHT_REASON = "quest-strategy:sweep-light"
EXIT_WALK_REASON = "quest-strategy:sweep-exit-walk"
EXIT_REASON = "quest-strategy:sweep-exit"


def _plan(policy, snapshot) -> dict | None:
    """The plan of the TAKEN quest on this floor; a completed one has left it."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    return None if profile is None else profile.engagement_plan.get("room_sweep")


def holds(policy, snapshot) -> bool:
    """This board's wait is the plan's own hold: under fire it still holds."""
    return policy.last_reason == HOLD_REASON and _plan(policy, snapshot) is not None


def planned_step(policy, snapshot) -> bool:
    """This board's step is the plan's own: the low-HP walk gate does not rewrite it."""
    return policy.last_reason in {WALK_REASON, EXIT_WALK_REASON} and _plan(policy, snapshot) is not None


def _navigator(policy, snapshot, quest_id: int) -> QuestFloorNavigator:
    navigator = policy._quest_navigators.setdefault(
        quest_id, QuestFloorNavigator(quest_id, policy._quest_knowledge[quest_id].battlefield))
    navigator.allow_diagonal = True
    navigator.reset_for_floor(snapshot.floor_key)
    return navigator


def _cell(position: Position) -> tuple[int, int]:
    return position.y, position.x


def _door_is_closed(snapshot, cell: tuple[int, int]) -> bool:
    grid = snapshot.grid_at(Position(*cell))
    return grid is None or not grid.known or grid.is_closed_door


class _Board:
    """The enemies of one board, as this plan weighs them."""

    def __init__(self, policy, snapshot, profile):
        position = snapshot.player.position
        known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                 if monster.hostile]
        self.in_view = sorted(
            (monster for monster in known if monster.perception != "detected"),
            key=lambda monster: quest_find_exit._rank(profile, monster))
        self.beside = [monster for monster in self.in_view
                       if monster.position.distance_to(position) <= 1]
        # What acts on the player now.  The name is quest_find_exit._speed's.
        self.coming_in_view = [monster for monster in self.in_view if not monster.asleep]
        self.mobile = [monster for monster in self.coming_in_view
                       if not quest_find_exit._never_moves(policy, monster)]
        self.pulling = ()
        self.hit_by_unseen = once_quest_recall._hit_by_unseen(policy, snapshot)

    @property
    def enemy(self) -> bool:
        return bool(self.in_view or self.hit_by_unseen)


# -- the way: terrain, lines, walks --------------------------------------------------


def _terrain_of(navigator, snapshot, *, water: bool) -> dict:
    """The map to walk: every door passes (_step_toward opens it); deep water only when
    asked, since hp-mp-processor.cpp drowns the overweight and nothing else needs it."""
    kinds = {"door": "passage"}
    if not water:
        kinds["deep_water"] = "wall"
    return {cell: kinds.get(kind, kind) for cell, kind in navigator.battlefield.terrain.items()}


_EXPOSURES: dict[tuple, quest_exposure.Exposure] = {}


def _lines(navigator, plan, snapshot) -> quest_exposure.Exposure:
    """Where the living ``line_races`` reach, through the doors as the board shows them."""
    battlefield = navigator.battlefield
    races = frozenset(plan.get("line_races", ()))
    casters = tuple(sorted(cell for cell, race in battlefield.monster_placements
                           if race in races and cell not in navigator.sweep_gone))
    opened = frozenset(cell for cell, kind in battlefield.terrain.items()
                       if kind == "door" and not _door_is_closed(snapshot, cell))
    key = (navigator.quest_id, casters, opened)
    if key not in _EXPOSURES:
        terrain = {**battlefield.terrain, **{cell: "floor" for cell in opened}}
        _EXPOSURES[key] = quest_exposure.exposure_map(terrain, casters)
    return _EXPOSURES[key]


def _note_gone(policy, snapshot, navigator, plan) -> None:
    """A placed caster's cell in the player's light and line with nothing on it."""
    battlefield = navigator.battlefield
    here = _cell(snapshot.player.position)
    reach = max(1, snapshot.light_radius or 1)
    occupied = {_cell(monster.position) for monster in snapshot.visible_monsters}
    for cell, race in battlefield.monster_placements:
        if (race in plan.get("line_races", ()) and cell not in navigator.sweep_gone
                and cell not in occupied and quest_exposure.game_distance(here, cell) <= reach
                and quest_exposure.projectable(battlefield.terrain, here, cell)):
            navigator.sweep_gone = navigator.sweep_gone | {cell}


def _refused_cells(policy, snapshot) -> list[Position]:
    """The cells the weapon warning refused that may not be stepped on now (the gate's own
    predicate: the all-supplies-exhausted forced walk may take them)."""
    return [cell for cell in policy._warning_refused_cells if policy._warning_step_refused(snapshot, cell)]


def _path(policy, navigator, plan, snapshot, goals, blocked=()) -> list[Position]:
    """The walk with the fewest cells in a caster's line, then the fewest steps; through
    deep water only from where no dry walk leads (a teleport can land on a shore); never
    over a cell the warning refused."""
    start = _cell(snapshot.player.position)
    goals = {_cell(goal) for goal in goals}
    taken = frozenset(_cell(cell) for cell in (*blocked, *_refused_cells(policy, snapshot)))
    lines = _lines(navigator, plan, snapshot)
    for water in (False, True):
        terrain = _terrain_of(navigator, snapshot, water=water)
        terrain[start] = "floor"
        path = quest_exposure.least_exposed_path(terrain, lines, start, goals, taken)
        if path:
            return [Position(*cell) for cell in path]
    return []


def _in_line(navigator, plan, snapshot) -> bool:
    return _cell(snapshot.player.position) in _lines(navigator, plan, snapshot).pull


def _out_of_line(policy, snapshot, navigator, plan) -> str | None:
    """Hurt on a quiet board in a living caster's line: to the nearest cell out of them."""
    if (snapshot.player.hp_ratio >= float(plan["rest_below_ratio"])
            or not _in_line(navigator, plan, snapshot)):
        return None
    lines = _lines(navigator, plan, snapshot).pull
    walkable = _terrain_of(navigator, snapshot, water=False)
    free = {Position(*cell) for cell, kind in walkable.items()
            if kind in {"floor", "passage"} and cell not in lines}
    return _step(policy, snapshot, _path(policy, navigator, plan, snapshot, free), WALK_REASON)


def _step(policy, snapshot, path: list[Position], reason: str) -> str | None:
    if len(path) < 2:
        return None
    policy.last_reason = reason
    policy._declare_reach(path[-1])
    return policy._step_toward(snapshot, path[1])


# -- the walk ------------------------------------------------------------------------


def _stops(plan) -> list[dict]:
    return [*plan["stands"], *plan["last_targets"]]


def _next_stop(navigator, plan) -> None:
    navigator.sweep_stage += 1
    navigator.sweep_meet_turns = 0
    if navigator.sweep_stage >= len(_stops(plan)):
        navigator.sweep_stage = 0
        navigator.sweep_round += 1


def _light_key(policy, snapshot, navigator, plan) -> str | None:
    """On a ``read_light`` stand, once a round, when the light can be read by."""
    here = [snapshot.player.position.y, snapshot.player.position.x]
    if (navigator.sweep_round in navigator.sweep_lit_rounds or not policy._can_read_scrolls(snapshot)
            or not any(stop["cell"] == here and stop.get("read_light") for stop in plan["stands"])):
        return None
    key = policy._quest_light_key(snapshot, LIGHT_REASON)
    if key is not None:
        navigator.sweep_lit_rounds = navigator.sweep_lit_rounds | {navigator.sweep_round}
    return key


def _last_target_key(policy, snapshot, navigator, plan, stop) -> str | None:
    """On its stand: open the door; with the door open and nothing on the cell, it is done."""
    door = tuple(stop["door"])
    if _door_is_closed(snapshot, door):
        policy.last_reason = OPEN_REASON
        return policy._step_toward(snapshot, Position(*door))
    _next_stop(navigator, plan)
    return None


def _advance(policy, snapshot, navigator, plan, blocked=()) -> str | None:
    """The next step of the walk; at a stop, what that stop asks, then the next."""
    here = snapshot.player.position
    for _ in range(len(_stops(plan)) + 1):
        if navigator.sweep_round >= int(plan["max_rounds"]):
            policy.last_reason = NOTHING_LEFT_REASON
            return WAIT_KEY
        stop = _stops(plan)[navigator.sweep_stage]
        goal = Position(*stop.get("stand", stop.get("cell")))
        if here != goal:
            stepped = _step(policy, snapshot, _path(policy, navigator, plan, snapshot, {goal}, blocked), WALK_REASON)
            if stepped is not None or not _refused_cells(policy, snapshot):
                return stepped
            # Only over a refused cell: this stop waits for the next round.
            _next_stop(navigator, plan)
            continue
        if (light := _light_key(policy, snapshot, navigator, plan)) is not None:
            return light
        if "door" in stop:
            opened = _last_target_key(policy, snapshot, navigator, plan, stop)
            if opened is not None:
                return opened
            continue
        if navigator.sweep_meet_turns < int(stop.get("meet_turns", 0)):
            navigator.sweep_meet_turns += 1
            policy.last_reason = HOLD_REASON
            return WAIT_KEY
        _next_stop(navigator, plan)
    return None


def walk_key(policy, snapshot) -> str | None:
    """A quiet board on such a floor, through the navigator: walk on."""
    plan = _plan(policy, snapshot)
    if plan is None:
        return None
    navigator = _navigator(policy, snapshot, snapshot.floor_key[2])
    _note_gone(policy, snapshot, navigator, plan)
    return _advance(policy, snapshot, navigator, plan)


# -- the fight -----------------------------------------------------------------------


def _aligned(snapshot, target) -> bool:
    here = snapshot.player.position
    dy, dx = abs(target.position.y - here.y), abs(target.position.x - here.x)
    return dy == 0 or dx == 0 or dy == dx


def _shot(policy, snapshot, target) -> str | None:
    """An absorbed power along a clear ray, else the launcher; both as everywhere else."""
    device = me_ranged_first.attack_key(policy, snapshot, target) if _aligned(snapshot, target) else None
    return device or policy._ranged_attack_key(snapshot, [target], [])


def _fight(policy, snapshot, profile, navigator, plan, board) -> str | None:
    """Beside the player, the blow; else a shot in the plan's order; else wait for what
    comes; else on, by way of what stands immobile in view and has no shot."""
    if board.beside:
        answer = combat_answer.adjacent_attack(policy, snapshot, board.beside[:1], MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
    for target in board.in_view:
        if target not in board.beside and (shot := _shot(policy, snapshot, target)) is not None:
            navigator.sweep_enemy_turns = 0
            return shot
    if (board.mobile and not _in_line(navigator, plan, snapshot)
            and navigator.sweep_enemy_turns < int(plan["enemy_wait_turns"])):
        navigator.sweep_enemy_turns += 1
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    if not board.in_view:
        return None  # hit by the unseen: unseen_strike and the shared ladders answer it
    occupied = {monster.position for monster in board.in_view}
    still = next((monster for monster in board.in_view
                  if quest_find_exit._never_moves(policy, monster)), None)
    if still is not None:
        around = {Position(still.position.y + dy, still.position.x + dx)
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1)} - occupied
        approached = _step(policy, snapshot, _path(policy, navigator, plan, snapshot, around, occupied), APPROACH_REASON)
        if approached is not None:
            return approached
    return _advance(policy, snapshot, navigator, plan, occupied)


# -- survival ------------------------------------------------------------------------


def _quaff_recovery(policy, snapshot) -> str | None:
    potion = quest_find_exit._healing_potion(policy, snapshot)
    if potion is None:
        return None
    policy.last_reason = quest_find_exit.HEAL_REASON
    return reserved_item_command(policy, snapshot, "quaff", potion)


def _below_line(policy, snapshot, profile, navigator) -> str | None:
    """Teleportation; after one that left an enemy on the player, a potion."""
    if snapshot.player.hp_ratio > float(profile.abort_conditions["hp_ratio"]):
        navigator.sweep_heal_next = False
        return None
    scroll = policy._find_teleport_scroll(snapshot) if policy._can_read_scrolls(snapshot) else None
    if navigator.sweep_heal_next or scroll is None:
        navigator.sweep_heal_next = False
        if (key := _quaff_recovery(policy, snapshot)) is not None:
            return key
    if scroll is None:
        return None
    navigator.sweep_heal_next = True
    policy.last_reason = TELEPORT_REASON
    return policy._read_key(snapshot, scroll)


def _leave_by_exit(policy, snapshot, navigator, plan, board) -> str | None:
    """Life-threatened with the Healing used up and the stair a few steps off."""
    if (not plan.get("exit_when_out_of_healing")
            or snapshot.player.hp_ratio > PANIC_HP_RATIO
            or quest_find_exit._healing_potion(policy, snapshot) is not None):
        return None
    goal = Position(*navigator.battlefield.exit)
    if snapshot.player.position == goal:
        policy.last_reason = EXIT_REASON
        return UP_STAIRS_KEY
    occupied = {monster.position for monster in board.in_view}
    path = _path(policy, navigator, plan, snapshot, {goal}, occupied)
    if len(path) - 1 > ITEM_DESTROYING_BREEDER_STAIR_DISTANCE:
        return None
    return _step(policy, snapshot, path, EXIT_WALK_REASON)


def _give_up(policy, snapshot, profile) -> str | None:
    if not once_quest_recall.below_scroll_floor(policy, snapshot, profile):
        return None
    return once_quest_recall.read_key(policy, snapshot, RECALL_REASON)


_RESTORES = (("restore_exp", lambda player: player.exp_drained),
             ("restore_str", lambda player: "str" in player.drained_stats))


def _restore(policy, snapshot) -> str | None:
    """A quiet board: what the drains took, by the potions the plan carries for them."""
    for name, drained in _RESTORES:
        if drained(snapshot.player):
            potion = policy._first_item(snapshot, lambda item: item.tval == TVAL_POTION and item.aware
                                        and item.sval == QUEST_POTION_SVALS[name])
            if potion is not None:
                policy.last_reason = RESTORE_REASON
                return reserved_item_command(policy, snapshot, "quaff", potion)
    return None


def key(policy, snapshot) -> str | None:
    """The board with an enemy about, or to recover on; None leaves it shared."""
    plan = _plan(policy, snapshot)
    if (plan is None or snapshot.player.food_state in quest_find_exit.STARVING
            or once_quest_recall._deliberate_leave(policy, snapshot)):
        return None
    quest_id = snapshot.floor_key[2]
    profile = policy.approved_quest_strategy(quest_id)
    navigator = _navigator(policy, snapshot, quest_id)
    _note_gone(policy, snapshot, navigator, plan)
    board = _Board(policy, snapshot, profile)
    if not board.enemy:
        navigator.sweep_enemy_turns = 0
        return (
            _restore(policy, snapshot)
            or _out_of_line(policy, snapshot, navigator, plan)
            or quest_find_exit._rest(policy, snapshot, plan, board)
        )
    return (
        quest_find_exit._cure(policy, snapshot)
        or _leave_by_exit(policy, snapshot, navigator, plan, board)
        or _give_up(policy, snapshot, profile)
        or _below_line(policy, snapshot, profile, navigator)
        or quest_find_exit._heal(policy, snapshot, profile)
        or quest_find_exit._speed(policy, snapshot, profile, board)
        or _light_key(policy, snapshot, navigator, plan)
        or _fight(policy, snapshot, profile, navigator, plan, board)
    )
