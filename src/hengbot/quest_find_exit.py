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

Owner 2026-11-06 「来ない遠くの敵を理由に隘路へ戻らないようにし」: a far (ESP-detected only)
mover sends the walk to a choke, or stops a dig, only once it is seen to close in
(``approaching``) or stands beside the walk ahead; a walk to a choke, once begun, goes on
while that reason holds instead of turning back to the exit cell by cell.

``find_exit.dig_cells`` are veins the walk opens.  Owner 2026-11-04 「簡単に掘れるので道具が
なくても必ず掘る。」.  Game: exe_tunnel (tunnel-execution.cpp:53) on a vein without CAN_DIG
succeeds when skill_dig > power + randint0(40 * power), power 10 for magma on water, one
player turn a try and the T command repeats itself (always_repeat); a skill of 10 or less never
succeeds, so ``dig_attempt_limit`` bounds the commands and the walk falls back to the undug
route.  No tool, no weapon swap.  An enemy that comes is answered first, at a choke; the
dig resumes after.  Route planning counts the cell as open; what a caster reaches now is
derived from the cells really opened, since a hole opens lines of fire too.

Owner 2026-11-04 「叫ばれる条件とテレポートバックを受ける条件は少し異なる。テレポートバックは
確実に避けるべきなので条件を把握すること。」: a pull cell (quest_exposure ``pull``) is forbidden, not
costed: ``pull_cells`` is every walk's blocked set here and ``pull_step_refused`` the net in
_step_toward for every other walker.  A player already on one takes the walk with the fewest
of them, under PULLED_BACK_REASON.

Owner 2026-11-04, when a vein will not open: 「可能な限り多くのモンスターを事前に倒してから引き寄せの
マスを進む」.  With no pull-free way on, ``_clear_key`` kills first: what comes is fought at the
chokes, and each mapped mover's cell is visited from a cell off the pull lines.
``clearing_finished``: no awake enemy comes and no such cell is left, or ``clear_turn_limit``
is spent, so it cannot freeze.  Only then does ``_pull_walk`` cross, under PULL_WALK_REASON.

``key`` runs before the shared survival ladders while an enemy is about on such a
floor: their answers walk away from the choke, which is what this plan refuses.  A
quiet board stays with them (food, light, the unseen) and reaches ``walk_key`` through
the navigator.
"""

from __future__ import annotations

from hengbot import combat_answer, once_quest_recall, quest_exposure, resist_potion, speed_dose, status_cure, summon_response
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, SV_POTION_HEALING
from hengbot.policy_constants import HEAL_POTION_SVALS, REST_MACRO, TUNNEL_KEY, WAIT_KEY
from hengbot.quest_navigator import QuestFloorNavigator

MELEE_REASON = "quest-strategy:melee"
HOLD_REASON = "quest-strategy:hold"
TO_CHOKE_REASON = "quest-strategy:exit-to-choke"
WALK_REASON = "quest-strategy:exit-walk"
STEP_ON_EXIT_REASON = "quest-strategy:exit-step"
DIG_REASON = "quest-strategy:exit-dig"
PULLED_BACK_REASON = "quest-strategy:exit-pulled-back"
PULL_REFUSED_REASON = "quest-strategy:pull-cell-refused"
CLEAR_REASON = "quest-strategy:exit-clear-first"
PULL_WALK_REASON = "quest-strategy:exit-pull-walk"
RECALL_REASON = "emergency:recall-quest-fail"
HEAL_REASON = "quest-strategy:heal"
CURE_REASON = "quest-strategy:cure"
SPEED_REASON = "quest-strategy:quaff-speed"
_PLANNED_STEPS = frozenset({TO_CHOKE_REASON, WALK_REASON, STEP_ON_EXIT_REASON, DIG_REASON,
                           PULLED_BACK_REASON, CLEAR_REASON, PULL_WALK_REASON})
STARVING = frozenset({"weak", "fainting"})
# Going round a monster on the way costs at most this many steps, else it is fought.
SIDESTEP_LIMIT = 2
VEIN_DIG_POWER = 10  # TerrainDefinitions MAGMA_VEIN_ON_DEEP_WATER tunnel power
PERMANENT_HASTE_SPEED = 120
DEFAULT_SPEED_RATIO = 0.5
# A far (detected only) monster comes when, within this many game turns (20 player turns
# at normal speed), it has closed APPROACH_CELLS on the player; a step back and forth
# never does.
APPROACH_WINDOW = 200
APPROACH_CELLS = 2


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
    plan = _plan(policy, snapshot)
    if plan is not None:
        _observe_digs(snapshot, navigator, plan)
    return navigator


_EXPOSURES: dict[tuple, quest_exposure.Exposure] = {}
_TERRAINS: dict[tuple, dict] = {}


def _opened_terrain(navigator, opened: frozenset) -> dict:
    """The quest map with these vein cells opened: DESTROYED leaves deep water."""
    key = (navigator.quest_id, opened)
    if key not in _TERRAINS:
        _TERRAINS[key] = {**navigator.battlefield.terrain, **{cell: "deep_water" for cell in opened}}
    return _TERRAINS[key]


def _exposure_with(navigator, plan, opened: frozenset) -> quest_exposure.Exposure:
    """The cells the plan's casters reach with these cells open, derived once."""
    races = tuple(plan.get("exposure_races", ()))
    key = (navigator.quest_id, races, opened)
    if key not in _EXPOSURES:
        _EXPOSURES[key] = quest_exposure.exposure_map(
            _opened_terrain(navigator, opened),
            [cell for cell, race in navigator.battlefield.monster_placements if race in races])
    return _EXPOSURES[key]


def _exposure(navigator, plan) -> quest_exposure.Exposure:
    """What the casters reach on the floor as it is now."""
    return _exposure_with(navigator, plan, navigator.exit_dug)


def _planned_open(navigator, plan) -> frozenset:
    """The cells the route counts as open: dug, or still to be dug."""
    wanted = frozenset(tuple(cell) for cell in plan.get("dig_cells", ()))
    return (wanted - navigator.exit_abandoned_digs) | navigator.exit_dug


def pull_cells(navigator, plan) -> frozenset:
    """Where a caster's direct line reaches, on the floor as it is or as planned."""
    now = _exposure_with(navigator, plan, navigator.exit_dug).pull
    planned = _exposure_with(navigator, plan, _planned_open(navigator, plan)).pull
    return frozenset(now) | frozenset(planned)


def pull_step_refused(policy, snapshot, step: Position) -> bool:
    """A walker other than the way back is about to step onto a pull cell of this floor."""
    plan = _plan(policy, snapshot)
    if plan is None or policy.last_reason in {PULLED_BACK_REASON, PULL_WALK_REASON}:
        return False
    navigator = policy._quest_navigators.get(snapshot.floor_key[2])
    if navigator is None:
        navigator = _navigator(policy, snapshot, snapshot.floor_key[2])
    return _cell(step) in pull_cells(navigator, plan)


def _observe_digs(snapshot, navigator, plan) -> None:
    """A planned vein the board shows open.  Other digs on the floor are not planned."""
    for raw in plan.get("dig_cells", ()):
        grid = snapshot.grid_at(Position(*raw))
        if grid is not None and grid.known and grid.passable:
            navigator.exit_dug = navigator.exit_dug | {tuple(raw)}


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


def _track(navigator, snapshot, known) -> None:
    """Each known monster's cells over the last APPROACH_WINDOW game turns of this floor."""
    turn = snapshot.turn
    tracks = {}
    for index, (race, history) in navigator.exit_tracks.items():
        history = tuple(row for row in history if turn - APPROACH_WINDOW <= row[0] <= turn)
        if history:
            tracks[index] = (race, history)
    for monster in known:
        race, history = tracks.get(monster.index, (monster.race_id, ()))
        if race != monster.race_id:
            history = ()  # the index went to another monster
        tracks[monster.index] = (monster.race_id, history + ((turn, _cell(monster.position)),))
    navigator.exit_tracks = tracks


def approaching(navigator, snapshot, monster) -> bool:
    """Seen to close in: over its track of the window, nearer the player by APPROACH_CELLS.

    Owner 2026-11-06 「来ない遠くの敵を理由に隘路へ戻らないようにし」: whether a far
    monster comes is what it did, not a static walk to the player.  Both cells are measured
    to where the player is now, so the player's own walk does not count as its approach;
    a monster stepping back and forth one cell (n1-a life 490, seahorse 443 at (9,6) and
    (10,6) the whole time) never does.  A monster first known on this board has done
    nothing yet.
    """
    _, history = navigator.exit_tracks.get(monster.index, (monster.race_id, ()))
    if not history:
        return False
    player = _cell(snapshot.player.position)
    farthest = max(quest_exposure.game_distance(cell, player) for _, cell in history)
    now = quest_exposure.game_distance(_cell(monster.position), player)
    return farthest - now >= APPROACH_CELLS


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
        _track(navigator, snapshot, known)
        # A monster that cannot come is no reason to hold a choke; one beside the player
        # is left behind by walking on (a siren's pull ends beside it, 840 HP unfought).
        self.reachable_awake = [monster for monster in known
                                if comes_for_player(policy, navigator, snapshot, monster)]
        self.coming_in_view = [monster for monster in self.reachable_awake
                               if monster.perception != "detected"]
        # What sends the walk to a choke or stops a dig: one in view, a far one seen to
        # close in, or one beside the walk ahead (in the way, moving or not).  A far one
        # that does not come is no reason (owner 2026-11-06).
        far = [monster for monster in self.reachable_awake if monster.perception == "detected"]
        leg = (_next_leg(navigator, _plan_of(profile), position)
               if any(not approaching(navigator, snapshot, monster) for monster in far) else [])
        self.mobile_awake = [*self.coming_in_view, *(
            monster for monster in far
            if approaching(navigator, snapshot, monster)
            or any(monster.position.distance_to(cell) <= 1 for cell in leg))]
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
    navigator.exit_choke_goal = None
    chokes = _chokes(navigator, plan)
    if position in chokes:
        held = _hold(policy, snapshot, navigator, plan, position, board)
        if held is not None:
            return held
        chokes = _chokes(navigator, plan)
    path = _least_exposed(navigator, plan, position, chokes, board.occupied, as_it_is=True)
    if len(path) < 2:
        return None
    navigator.exit_choke_goal = path[-1]
    policy.last_reason = TO_CHOKE_REASON
    policy._declare_reach(path[-1])
    return policy._step_toward(snapshot, path[1])


def _choke_walk_under_way(policy, snapshot, navigator, plan, board) -> str | None:
    """The walk to a choke goes on over cells that would otherwise walk to the exit.

    n1-a life 490 (2026-11-06): (1,8) stepped to the choke, the shouted (2,7) stepped to
    the exit, one cell each, until the loop guard stopped it; life 491 did the same between
    (5,23) and the dig at (5,25).  While what sent it there still holds, a shouted cell or a
    board with no enemy to strike goes on to the choke; it stops when that reason is gone.
    """
    goal = navigator.exit_choke_goal
    # A pulled player takes the way back by name (_advance); a floor that needs clearing has
    # its own answer to what comes and its own end (_clear_key, clear_turn_limit).
    if (goal is None or not board.mobile_awake or snapshot.player.position == goal
            or _cell(snapshot.player.position) in pull_cells(navigator, plan)
            or _floor_needs_clearing(navigator, plan)):
        navigator.exit_choke_goal = None
        return None
    return _to_choke(policy, snapshot, navigator, plan, board)


def _least_exposed(navigator, plan, start: Position, goals, blocked=(), *,
                   as_it_is: bool = False) -> list[Position]:
    """The least exposed walk over the planned floor, or (``as_it_is``) the present one."""
    opened = navigator.exit_dug if as_it_is else _planned_open(navigator, plan)
    path = quest_exposure.least_exposed_path(
        _opened_terrain(navigator, opened), _exposure_with(navigator, plan, opened), _cell(start),
        {_cell(goal) for goal in goals}, frozenset(_cell(cell) for cell in blocked),
        forbidden=pull_cells(navigator, plan) - {_cell(start)})
    return [Position(*cell) for cell in path]


def _safe_region(navigator, plan) -> set:
    """The cells off every pull line from which the planned floor leads to the exit."""
    terrain = _opened_terrain(navigator, _planned_open(navigator, plan))
    forbidden = pull_cells(navigator, plan)
    start = _cell(_exit_cell(navigator))
    seen, pending = {start}, [start]
    while pending:
        cell = pending.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt = (cell[0] + dy, cell[1] + dx)
                if (nxt not in seen and nxt not in forbidden
                        and terrain.get(nxt) in {"deep_water", "shallow_water", "floor"}):
                    seen.add(nxt)
                    pending.append(nxt)
    return seen


def _way_back(policy, snapshot, navigator, plan, board) -> str | None:
    """Pulled onto a pull cell: over the floor as it is, the walk with the fewest of them
    to a cell the safe route goes on from."""
    position = _cell(snapshot.player.position)
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    exposure = _exposure_with(navigator, plan, navigator.exit_dug)
    goals = _safe_region(navigator, plan)
    occupied = frozenset(_cell(cell) for cell in board.occupied)
    path = (quest_exposure.least_exposed_path(terrain, exposure, position, goals, occupied)
            or quest_exposure.least_exposed_path(terrain, exposure, position, goals))
    if len(path) < 2:
        return None
    step = Position(*path[1])
    if step in board.occupied:
        blocker = next((monster for monster in board.in_view if monster.position == step), None)
        if blocker is not None:
            return combat_answer.strike_key(policy, snapshot, blocker, MELEE_REASON)
    policy.last_reason = PULLED_BACK_REASON
    policy._declare_reach(_exit_cell(navigator))
    return policy._step_toward(snapshot, step)


def _exposed_count(navigator, plan, path: list[Position]) -> int:
    exposure = _exposure_with(navigator, plan, _planned_open(navigator, plan))
    return sum(exposure.exposed(_cell(cell)) for cell in path)


def _dig(policy, snapshot, navigator, plan, board, profile, cell: Position) -> str | None:
    """The T command at a planned vein beside the player; a coming enemy is answered first."""
    skill = snapshot.player.digging_skill
    # exe_tunnel: skill_dig > power + randint0(40 * power); power 10 here, so 10 never opens it.
    hopeless = skill is not None and skill <= VEIN_DIG_POWER
    if not hopeless and (board.mobile_awake or board.adjacent_mobile or board.hit_by_unseen):
        return _fight(policy, snapshot, profile, navigator, plan, board)
    attempts = dict(navigator.exit_dig_attempts)
    attempts[_cell(cell)] = attempts.get(_cell(cell), 0) + 1
    navigator.exit_dig_attempts = attempts
    if hopeless or attempts[_cell(cell)] > int(plan["dig_attempt_limit"]):
        navigator.exit_abandoned_digs = navigator.exit_abandoned_digs | {_cell(cell)}
        return _advance(policy, snapshot, navigator, plan, board)
    policy.last_reason = DIG_REASON
    return TUNNEL_KEY + policy._direction_key(snapshot.player.position, cell)


def _floor_needs_clearing(navigator, plan) -> bool:
    """The entrance has no pull-free way to the exit any more: a vein did not open."""
    start = Position(*navigator.battlefield.player_start)
    return not _least_exposed(navigator, plan, start, {_exit_cell(navigator)})


def _unvisited_movers(policy, navigator, profile) -> dict[tuple[int, int], set]:
    """Each mapped mover's cell not yet seen empty, and the free cells to attack it from."""
    pull = pull_cells(navigator, _plan_of(profile))
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    sealed = sealed_races(profile)
    found: dict[tuple[int, int], set] = {}
    for cell, race in navigator.battlefield.monster_placements:
        knowledge = policy._monrace_knowledge.get(race)
        if (race in sealed or cell in navigator.exit_cleared_placements
                or (knowledge is not None and "NEVER_MOVE" in knowledge.flags)):
            continue
        found[cell] = {(cell[0] + dy, cell[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                       if (dy, dx) != (0, 0)
                       and terrain.get((cell[0] + dy, cell[1] + dx)) in {"deep_water", "shallow_water"}
                       and (cell[0] + dy, cell[1] + dx) not in pull}
    return found


def _plan_of(profile) -> dict:
    return profile.engagement_plan["find_exit"]


def _note_empty_placements(snapshot, navigator, board, movers) -> None:
    position = _cell(snapshot.player.position)
    occupied = {_cell(cell) for cell in board.occupied}
    for cell in movers:
        if quest_exposure.game_distance(cell, position) <= 1 and cell not in occupied:
            navigator.exit_cleared_placements = navigator.exit_cleared_placements | {cell}


def clearing_finished(navigator) -> bool:
    return navigator.exit_clearing_done


def _clear_key(policy, snapshot, navigator, plan, board) -> str | None:
    """Kill what can be fought off the pull lines; None when the clearing has ended."""
    profile = policy.approved_quest_strategy(navigator.quest_id)
    position = snapshot.player.position
    navigator.exit_clear_turns += 1
    if navigator.exit_clear_turns > int(plan["clear_turn_limit"]):
        navigator.exit_clearing_done = True
        return None
    exposed = _exposure(navigator, plan).exposed(_cell(position))
    if board.mobile_awake:
        moved = _to_choke(policy, snapshot, navigator, plan, board) if exposed else None
        answer = moved or _fight(policy, snapshot, profile, navigator, plan, board)
        if answer is not None:
            return answer
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    if exposed and snapshot.player.hp_ratio < float(plan["rest_below_ratio"]):
        # The rest comes off the shouted cells, before the next sleeper.
        path = _least_exposed(navigator, plan, position,
                              {Position(*cell) for cell in plan["choke_cells"]}, board.occupied,
                              as_it_is=True)
        if len(path) >= 2:
            policy.last_reason = CLEAR_REASON
            return policy._step_toward(snapshot, path[1])
    movers = _unvisited_movers(policy, navigator, profile)
    _note_empty_placements(snapshot, navigator, board, movers)
    movers = _unvisited_movers(policy, navigator, profile)
    beside = next((monster for monster in board.in_view
                   if _cell(monster.position) in movers
                   and monster.position.distance_to(position) <= 1), None)
    if beside is not None:
        return combat_answer.strike_key(policy, snapshot, beside, MELEE_REASON)
    stands = {Position(*cell) for cells in movers.values() for cell in cells}
    path = _least_exposed(navigator, plan, position, stands, board.occupied, as_it_is=True)
    if len(path) < 2:
        navigator.exit_clearing_done = True
        return None
    policy.last_reason = CLEAR_REASON
    policy._declare_reach(path[-1])
    return policy._step_toward(snapshot, path[1])


def _pull_walk(policy, snapshot, navigator, plan, board) -> str | None:
    """The clearing is over: across the pull cells by the walk with the fewest of them."""
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    exposure = _exposure_with(navigator, plan, navigator.exit_dug)
    position, exit_cell = _cell(snapshot.player.position), {_cell(_exit_cell(navigator))}
    occupied = frozenset(_cell(cell) for cell in board.occupied)
    path = (quest_exposure.least_exposed_path(terrain, exposure, position, exit_cell, occupied)
            or quest_exposure.least_exposed_path(terrain, exposure, position, exit_cell))
    if len(path) < 2:
        return None
    step = Position(*path[1])
    if step in board.occupied:
        blocker = next((monster for monster in board.in_view if monster.position == step), None)
        if blocker is not None:
            return combat_answer.strike_key(policy, snapshot, blocker, MELEE_REASON)
    policy.last_reason = PULL_WALK_REASON
    policy._declare_reach(_exit_cell(navigator))
    return policy._step_toward(snapshot, step)


def _off_the_pull_lines(policy, snapshot, navigator, plan, board) -> str | None:
    """Pulled while the clearing runs: back to the nearest cell off the lines."""
    terrain = _opened_terrain(navigator, navigator.exit_dug)
    exposure = _exposure_with(navigator, plan, navigator.exit_dug)
    pull = pull_cells(navigator, plan)
    goals = {cell for cell, kind in terrain.items()
             if kind in {"deep_water", "shallow_water"} and cell not in pull}
    occupied = frozenset(_cell(cell) for cell in board.occupied)
    path = quest_exposure.least_exposed_path(
        terrain, exposure, _cell(snapshot.player.position), goals, occupied)
    if len(path) < 2:
        return None
    policy.last_reason = PULLED_BACK_REASON
    return policy._step_toward(snapshot, Position(*path[1]))


def _advance(policy, snapshot, navigator, plan, board) -> str | None:
    """A step of the least exposed walk to the exit, round a monster when that exposes no
    more and is a sidestep; else it is struck."""
    position, exit_cell = snapshot.player.position, _exit_cell(navigator)
    clearing = _floor_needs_clearing(navigator, plan)
    if _cell(position) in pull_cells(navigator, plan):
        if not clearing:
            return _way_back(policy, snapshot, navigator, plan, board)
        if clearing_finished(navigator):
            return _pull_walk(policy, snapshot, navigator, plan, board)
        return _off_the_pull_lines(policy, snapshot, navigator, plan, board)
    through = _least_exposed(navigator, plan, position, {exit_cell})
    around = _least_exposed(navigator, plan, position, {exit_cell}, board.occupied)
    path = around if (
        around and len(around) <= len(through) + SIDESTEP_LIMIT
        and _exposed_count(navigator, plan, around) <= _exposed_count(navigator, plan, through)
    ) else through
    if len(path) < 2:
        # Every way on crosses a caster's direct line: kill first, then cross.
        if not clearing_finished(navigator):
            cleared = _clear_key(policy, snapshot, navigator, plan, board)
            if cleared is not None:
                return cleared
        return _pull_walk(policy, snapshot, navigator, plan, board)
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
    if _cell(step) in _planned_open(navigator, plan) - navigator.exit_dug:
        profile = policy.approved_quest_strategy(navigator.quest_id)
        return _dig(policy, snapshot, navigator, plan, board, profile, step)
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
    if not board.mobile_awake:
        navigator.exit_choke_goal = None  # what sent the walk to a choke is gone
    exposed = _exposure(navigator, plan).exposed(_cell(snapshot.player.position))
    stepped = _step_on_exit(policy, snapshot, navigator, board)
    if stepped is not None:
        return stepped
    if exposed:
        # Survival first, then out of their reach: no hold, rest or chosen fight here.
        return (
            (_below_line_recall(policy, snapshot, profile) if board.enemy_for_the_line else None)
            or (_heal(policy, snapshot, profile) if board.engaged else None)
            or summon_response.key(policy, snapshot)
            or resist_potion.key(policy, snapshot)
            or _choke_walk_under_way(policy, snapshot, navigator, plan, board)
            or _advance(policy, snapshot, navigator, plan, board)
        )
    if not board.enemy_for_the_line:
        return (
            summon_response.key(policy, snapshot)
            or resist_potion.key(policy, snapshot)
            or _rest(policy, snapshot, plan, board)
            or (_to_choke(policy, snapshot, navigator, plan, board) if board.mobile_awake else None)
            or _wait_after_fight(policy, snapshot, navigator, plan, board)
            or (_advance(policy, snapshot, navigator, plan, board) if board.in_view else None)
        )
    return (
        _below_line_recall(policy, snapshot, profile)
        or (_engaged_survival(policy, snapshot, profile, board) if board.engaged else None)
        # Owner 2026-11-04: the answer to the summons, ahead of the plan's own order.
        or summon_response.key(policy, snapshot)
        or resist_potion.key(policy, snapshot)
        or (_fight(policy, snapshot, profile, navigator, plan, board) if board.engaged else None)
        or _choke_walk_under_way(policy, snapshot, navigator, plan, board)
        or _advance(policy, snapshot, navigator, plan, board)
    )


def _engaged_survival(policy, snapshot, profile, board) -> str | None:
    return (
        _cure(policy, snapshot)
        or _heal(policy, snapshot, profile)
        or _speed(policy, snapshot, profile, board)
    )


def _fight(policy, snapshot, profile, navigator, plan, board) -> str | None:
    if board.adjacent_mobile:
        _note_contact(navigator, plan, snapshot.player.position)
        ranked = sorted(board.adjacent_mobile, key=lambda monster: _rank(profile, monster))
        target = summon_response.named_casters_first(policy, ranked)[0]
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
