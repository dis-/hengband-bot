"""A KILL_ALL floor walked room by room: ``engagement_plan.room_sweep``.

The data (QUEST_25 gives the reasons of its cells):

 * ``stands``: the cells walked in order; ``meet_turns`` waits there for what comes;
   ``read_light`` lights the room from there, once a round, enemy or none, unless the board
   shows it lit already (quest_room_light);
 * ``last_targets``: what is left until every stand has been walked, each with its
   ``race``, ``cell``, the ``stand`` it is shot from and the closed ``door``, if any, that
   the stand opens first;
 * ``left_alone_races``: last targets that are no target at all until the walk reaches their
   first stop: seen, they get no shot, no walk, no wait, and rest goes on.  From that stop on,
   one seen before and out of sight now is walked to where it was last seen (owner 2026-11-05
   「プレイヤーを移動させられた場合は最後に見えた場所へ移動。モンスターが移動した場合は歩いて探す」):
   the walk's own stops wait until that cell is in the light and in line.  Standing there with
   nothing on it, the monster has moved (or died), and the stops are walked one by one;
 * ``line_races``: never-moving casters whose direct line every walk crosses as little
   as it can, and on which nobody rests or waits by choice (Q18's first fights, 2026-11-04:
   n1-a died standing on a cell under fire);
 * ``enemy_wait_turns``: the far bound on a coming enemy that stays in view without a
   shot or a blow; ``rest_below_ratio``: rest below this on a quiet floor;
 * ``max_rounds``: full walks with the quest still open before the plan stops by name;
 * ``unseen_attacker``: "cover_or_close", see below;
 * ``light_dark_room``, ``opening_quaff``: quest_room_light;
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
are shot from in their line, and every walk crosses the fewest lines.  Owner 2026-11-05
「クイルスルグは放置しても問題ないし、簡単には倒せないので最後ドルジの前に処理する」.

A cell a monster's weapon warning refused (warning.cpp process_warning; the latch is the
policy's) is no step while a movement scroll remains (owner: 物資が全て尽きている場合のみ徒歩強行を
許す).  Every walk here goes round it, and a stop reached only over it is passed for this round.
A trap's warning is no refusal (trap_warning, owner 2026-11-05 「罠があるので対応する」): the walk
keeps its way and ``_step_toward`` searches, disarms and crosses.  No walk here weighs traps.

``unseen_attacker``, owner 2026-11-05 「まず暗くて照らせるなら照らす。遮蔽が近ければ遮蔽をとって待ち伏せ。
遮蔽がないか遠ければ想定方向に距離を詰める」: hit by what cannot be seen, with nothing in view to answer,
and after the survival rungs and the light (quest_room_light).  "Near" is one step, by the owner's
earlier 「一歩で遮蔽が取れないなら距離を詰めたほうが良い」.  No message says where the attacker is (何か,
monster-describer.cpp); what is read is today's reading of the retreat (``_recent_reverse_direction``):
it stands ahead of the player's last step.  It needs the player's own line and no light on it, so it
is on a cell ahead with a line to the player, out of the player's light.  One step to a cell none of
those cells has a line to, and out of every ``line_races`` line, is cover.  Else the walk closes on the
nearest of them.  No last step (a teleport's landing), or no such cell, is an unknown direction: the
owner's words do not settle it, and the plan's walk goes on.  A blow is struck back and a blind player
answers by the shared rungs, as before.

On the cover the player holds in ambush: it has answered that hit, so the floor is quiet again and its
own rungs (the potions, the rest) still go first; the shared ladders do not walk him off it.  The hold
ends when an enemy comes into view (the fight rungs answer it, and it is the one expected), when he is
hit again or moved, in a ``line_races`` line, or after ``enemy_wait_turns`` holds.  Blind or confused
he does not hold (the shared rungs cure it) and the hold goes on afterwards.  A cell stepped out of
once for cover is not left the same way again, or the hold, the walk back and the hit would go on for
ever: the next hit there closes.

``key`` runs before the shared survival ladders while an enemy is about: they walk away and
read Recall, which is what this plan refuses.  A quiet board stays with them (food, light,
the unseen) and reaches ``walk_key`` through the navigator.  A leave already decided (a
breeder stalemate, starvation) leaves the board to them.
"""

from __future__ import annotations

from hengbot import (
    combat_answer,
    me_ranged_first,
    once_quest_recall,
    quest_exposure,
    quest_find_exit,
    quest_room_light,
    resist_potion,
    summon_response,
    threat_tiers,
    unseen_strike,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position
from hengbot.policy_constants import (
    ITEM_DESTROYING_BREEDER_STAIR_DISTANCE,
    PANIC_HP_RATIO,
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
LIGHT_REASON = quest_room_light.LIGHT_REASON
EXIT_WALK_REASON = "quest-strategy:sweep-exit-walk"
EXIT_REASON = "quest-strategy:sweep-exit"
COVER_REASON = "quest-strategy:sweep-cover"
CLOSE_REASON = "quest-strategy:sweep-close"
UNSEEN_ATTACK_SIGHT = 20  # MAX_SIGHT, the reach of a monster's spell


def _plan(policy, snapshot) -> dict | None:
    """The plan of the TAKEN quest on this floor; a completed one has left it.  A floor the
    phase battle runs (quest25_battle, Q25's revised plan) is not walked room by room."""
    from hengbot import quest25_battle  # it reads this module's walk helpers

    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    if profile is None or quest25_battle.applies(policy, snapshot):
        return None
    return profile.engagement_plan.get("room_sweep")


def walks_over_traps(policy, snapshot) -> bool:
    """This floor's walks do not go round a trap: the stops lie behind them (2026-10-23).
    The phase battle answers its traps itself (quest25_battle)."""
    from hengbot import quest25_battle

    return _plan(policy, snapshot) is not None or quest25_battle.walks_over_traps(policy, snapshot)


def holds(policy, snapshot) -> bool:
    """This board's wait is the plan's own hold: under fire it still holds."""
    return policy.last_reason == HOLD_REASON and _plan(policy, snapshot) is not None


def planned_step(policy, snapshot) -> bool:
    """This board's step is the plan's own: the low-HP walk gate does not rewrite it."""
    return (policy.last_reason in {WALK_REASON, EXIT_WALK_REASON, COVER_REASON, CLOSE_REASON}
            and _plan(policy, snapshot) is not None)


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


def _left_alone_races(navigator, plan) -> frozenset:
    """The ``left_alone_races`` whose first stop the walk has not reached yet."""
    reached = {stop.get("race") for stop in _stops(plan)[:navigator.sweep_stage + 1]}
    return frozenset(plan.get("left_alone_races", ())) - reached


class _Board:
    """The enemies of one board, as this plan weighs them."""

    def __init__(self, policy, snapshot, profile, navigator, plan):
        position = snapshot.player.position
        known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                 if monster.hostile]
        seen = [monster for monster in known if monster.perception != "detected"]
        left_alone = _left_alone_races(navigator, plan)
        self.left_alone = [monster for monster in seen if monster.race_id in left_alone]
        self.occupied = {monster.position for monster in seen}
        self.in_view = sorted(
            (monster for monster in seen if monster.race_id not in left_alone),
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


def _open_doors(navigator, snapshot) -> frozenset:
    return frozenset(cell for cell, kind in navigator.battlefield.terrain.items()
                     if kind == "door" and not _door_is_closed(snapshot, cell))


def _open_terrain(navigator, snapshot) -> dict:
    """The map as lines cross it: through the doors as the board shows them."""
    return {**navigator.battlefield.terrain, **{cell: "floor" for cell in _open_doors(navigator, snapshot)}}


def _door_is_closed_on_map(navigator, snapshot, cell: tuple[int, int]) -> bool:
    return navigator.battlefield.terrain.get(cell) == "door" and _door_is_closed(snapshot, cell)


def _lines(navigator, plan, snapshot) -> quest_exposure.Exposure:
    """Where the living ``line_races`` reach, through the doors as the board shows them."""
    battlefield = navigator.battlefield
    races = frozenset(plan.get("line_races", ()))
    casters = tuple(sorted(cell for cell, race in battlefield.monster_placements
                           if race in races and cell not in navigator.sweep_gone))
    key = (navigator.quest_id, casters, _open_doors(navigator, snapshot))
    if key not in _EXPOSURES:
        _EXPOSURES[key] = quest_exposure.exposure_map(_open_terrain(navigator, snapshot), casters)
    return _EXPOSURES[key]


def _in_light_and_line(navigator, snapshot, here: tuple[int, int], cell: tuple[int, int]) -> bool:
    """A monster on ``cell`` would be seen from ``here``."""
    return (quest_exposure.game_distance(here, cell) <= max(1, snapshot.light_radius or 1)
            and quest_exposure.projectable(navigator.battlefield.terrain, here, cell))


def _note_gone(policy, snapshot, navigator, plan) -> None:
    """A placed caster's cell in the player's light and line with nothing on it."""
    here = _cell(snapshot.player.position)
    occupied = {_cell(monster.position) for monster in snapshot.visible_monsters}
    for cell, race in navigator.battlefield.monster_placements:
        if (race in plan.get("line_races", ()) and cell not in navigator.sweep_gone
                and cell not in occupied and _in_light_and_line(navigator, snapshot, here, cell)):
            navigator.sweep_gone = navigator.sweep_gone | {cell}


def _note_last_seen(snapshot, navigator, plan) -> None:
    """Where each ``left_alone_races`` monster was last seen on this floor; a cell looked at
    with nothing on it is forgotten (a blind player looks at nothing)."""
    races = plan.get("left_alone_races", ())
    known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
             if monster.hostile and monster.race_id in races]
    here = _cell(snapshot.player.position)
    now = {index: entry for index, entry in navigator.sweep_last_seen.items()
           if snapshot.player.blind or not _in_light_and_line(navigator, snapshot, here, entry[1])}
    now.update({monster.index: (monster.race_id, _cell(monster.position)) for monster in known})
    navigator.sweep_last_seen = now


def _sought_cells(snapshot, navigator, plan) -> dict[int, tuple[int, int]]:
    """The last-seen cells to go to: out of sight now, and past the walk's leaving them alone."""
    left_alone = _left_alone_races(navigator, plan)
    in_sight = {monster.index for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)}
    return {index: cell for index, (race, cell) in navigator.sweep_last_seen.items()
            if race not in left_alone and index not in in_sight}


def _to_last_seen(policy, snapshot, navigator, plan, blocked=()) -> str | None:
    """The step toward the nearest place a sought cell is looked at from: ground only, where
    there is any.  With no way there the record is dropped and the stops go on."""
    sought = _sought_cells(snapshot, navigator, plan)
    if not sought:
        return None
    terrain = _terrain_of(navigator, snapshot, water=False)
    goals = {Position(*spot) for spot, kind in terrain.items() if kind in {"floor", "passage"}
             and any(_in_light_and_line(navigator, snapshot, spot, cell) for cell in sought.values())}
    stepped = _step(policy, snapshot, _path(policy, navigator, plan, snapshot, goals, blocked), WALK_REASON)
    if stepped is None:
        navigator.sweep_last_seen = {index: entry for index, entry in navigator.sweep_last_seen.items()
                                     if index not in sought}
    return stepped


def _refused_cells(policy, snapshot, navigator) -> list[Position]:
    """The cells of the map the weapon warning refused and that may not be stepped on now (the
    gate's own predicate: the all-supplies-exhausted forced walk may take them)."""
    cells = (Position(*cell) for cell in navigator.battlefield.terrain)
    return [cell for cell in cells if policy._warning_step_refused(snapshot, cell)]


def _path(policy, navigator, plan, snapshot, goals, blocked=()) -> list[Position]:
    """The walk with the fewest cells in a caster's line, then the fewest steps; through
    deep water only from where no dry walk leads (a teleport can land on a shore); never
    over a cell the warning refused."""
    start = _cell(snapshot.player.position)
    goals = {_cell(goal) for goal in goals}
    taken = frozenset(_cell(cell) for cell in (*blocked, *_refused_cells(policy, snapshot, navigator)))
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
    """On a ``read_light`` stand, once a round, when the room is dark."""
    here = [snapshot.player.position.y, snapshot.player.position.x]
    if (navigator.sweep_round in navigator.sweep_lit_rounds
            or not any(stop["cell"] == here and stop.get("read_light") for stop in plan["stands"])):
        return None
    key = quest_room_light.light_room_key(
        policy, snapshot, navigator, _open_terrain(navigator, snapshot), LIGHT_REASON)
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
    if (sought := _to_last_seen(policy, snapshot, navigator, plan, blocked)) is not None:
        return sought
    for _ in range(len(_stops(plan)) + 1):
        if navigator.sweep_round >= int(plan["max_rounds"]):
            policy.last_reason = NOTHING_LEFT_REASON
            return WAIT_KEY
        stop = _stops(plan)[navigator.sweep_stage]
        goal = Position(*stop.get("stand", stop.get("cell")))
        if here != goal:
            stepped = _step(policy, snapshot, _path(policy, navigator, plan, snapshot, {goal}, blocked), WALK_REASON)
            if stepped is not None or not _refused_cells(policy, snapshot, navigator):
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


# -- the attacker no one sees ----------------------------------------------------------


def _unseen_attacker_cells(policy, snapshot, navigator) -> set[tuple[int, int]]:
    """Where it can stand: ahead of the last step, with a line to the player, out of his light."""
    here = _cell(snapshot.player.position)
    behind = policy._recent_reverse_direction(snapshot.player.position)
    if behind is None:
        return set()
    return {cell for cell, kind in _open_terrain(navigator, snapshot).items()
            if kind in quest_exposure.PROJECTING_KINDS
            and (cell[0] - here[0]) * behind[0] + (cell[1] - here[1]) * behind[1] < 0
            and not _in_light_and_line(navigator, snapshot, here, cell)
            and not quest_room_light.drawn_lit(snapshot, cell)
            and quest_exposure.game_distance(here, cell) <= UNSEEN_ATTACK_SIGHT
            and quest_exposure.projectable(_open_terrain(navigator, snapshot), cell, here)}


def _cover_step(snapshot, navigator, plan, cells, board) -> Position | None:
    """A free neighbour no cell of ``cells`` has a line to, where it may be held."""
    here = snapshot.player.position
    terrain = _open_terrain(navigator, snapshot)
    walkable = _terrain_of(navigator, snapshot, water=False)
    lines = _lines(navigator, plan, snapshot).pull
    around = (Position(here.y + dy, here.x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    for step in around:
        spot = _cell(step)
        if (walkable.get(spot) in {"floor", "passage"} and not _door_is_closed_on_map(navigator, snapshot, spot)
                and step not in board.occupied and spot not in lines
                and not any(quest_exposure.projectable(terrain, cell, spot) for cell in cells)):
            return step
    return None


def _unseen_answer(policy, snapshot, navigator, plan, board) -> str | None:
    """Cover in one step, else closer; None when the direction is unknown."""
    cells = _unseen_attacker_cells(policy, snapshot, navigator)
    if not cells:
        return None
    here = _cell(snapshot.player.position)
    if here not in navigator.sweep_cover_taken:
        step = _cover_step(snapshot, navigator, plan, cells, board)
        if step is not None:
            navigator.sweep_cover_taken = navigator.sweep_cover_taken | {here}
            navigator.sweep_ambush = _cell(step)
            navigator.sweep_ambush_turns = 0
            policy._unseen_hit_pending_floor = None  # answered, as the shared retreat consumes it
            policy.last_reason = COVER_REASON
            policy._declare_reach(step)
            return policy._step_toward(snapshot, step)
    goals = {Position(*cell) for cell in cells}
    return _step(policy, snapshot, _path(policy, navigator, plan, snapshot, goals, board.occupied), CLOSE_REASON)


def _note_ambush(policy, snapshot, navigator, plan, board) -> None:
    """Every board: what ends the hold on the cover (module docstring)."""
    if navigator.sweep_ambush is None:
        return
    hit_now = policy._unseen_attack_evidence is not None or policy._unexplained_damage_streak >= 2
    if (navigator.sweep_ambush != _cell(snapshot.player.position) or board.in_view or hit_now
            or _in_line(navigator, plan, snapshot)
            or navigator.sweep_ambush_turns >= int(plan["enemy_wait_turns"])):
        navigator.sweep_ambush = None


def _ambush_key(policy, snapshot, navigator) -> str | None:
    """On the cover with nothing to answer: wait for what is expected."""
    if navigator.sweep_ambush is None or snapshot.player.blind or snapshot.player.confused:
        return None
    navigator.sweep_ambush_turns += 1
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _unseen_key(policy, snapshot, navigator, plan, board) -> str | None:
    """The plan's own answer, or its walk; the shared rungs keep a blow and blindness."""
    if (plan.get("unseen_attacker") != "cover_or_close" or snapshot.player.blind
            or unseen_strike.hit_in_melee(policy, snapshot)):
        return None
    return (_unseen_answer(policy, snapshot, navigator, plan, board)
            or _advance(policy, snapshot, navigator, plan, board.occupied))


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
        struck = summon_response.named_casters_first(policy, board.beside)[:1]
        answer = combat_answer.adjacent_attack(policy, snapshot, struck, MELEE_REASON)
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
    if not board.in_view and (unseen := _unseen_key(policy, snapshot, navigator, plan, board)) is not None:
        return unseen
    if not board.in_view and not board.left_alone:
        return None  # hit by the unseen: unseen_strike and the shared ladders answer it
    occupied = board.occupied
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
    path = _path(policy, navigator, plan, snapshot, {goal}, board.occupied)
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
            potion = quest_room_light.carried_potion(policy, snapshot, name)
            if potion is not None:
                policy.last_reason = RESTORE_REASON
                return reserved_item_command(policy, snapshot, "quaff", potion)
    return None


def _unseen_light(policy, snapshot, navigator, plan, board) -> str | None:
    return quest_room_light.unseen_light_key(
        policy, snapshot, navigator, plan, _open_terrain(navigator, snapshot), board.hit_by_unseen)


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
    _note_last_seen(snapshot, navigator, plan)
    quest_room_light.note_floor_potion(policy, snapshot, navigator, plan)
    board = _Board(policy, snapshot, profile, navigator, plan)
    _note_ambush(policy, snapshot, navigator, plan, board)
    if not board.enemy:
        navigator.sweep_enemy_turns = 0
        return (
            quest_room_light.floor_potion_key(policy, snapshot, navigator, plan, quiet=True)
            or _unseen_light(policy, snapshot, navigator, plan, board)
            or summon_response.key(policy, snapshot)
            or resist_potion.key(policy, snapshot)
            or _restore(policy, snapshot)
            or _out_of_line(policy, snapshot, navigator, plan)
            or quest_find_exit._rest(policy, snapshot, plan, board)
            or _ambush_key(policy, snapshot, navigator)
            # The shared ladders below would fight what is seen: the walk answers it here.
            or (_advance(policy, snapshot, navigator, plan, board.occupied) if board.left_alone else None)
        )
    return (
        # Owner 2026-11-07 「作戦が先・即死だけ例外」: only the 1-turn 即死 pre-empts the plan.
        threat_tiers.instant_death_key(policy, snapshot)
        or quest_find_exit._cure(policy, snapshot)
        or _leave_by_exit(policy, snapshot, navigator, plan, board)
        or _give_up(policy, snapshot, profile)
        or _below_line(policy, snapshot, profile, navigator)
        or quest_find_exit._heal(policy, snapshot, profile)
        or quest_find_exit._speed(policy, snapshot, profile, board)
        or quest_room_light.floor_potion_key(policy, snapshot, navigator, plan, quiet=False)
        # Before the unseen rule and the summons: the light may show them their caster.
        or _unseen_light(policy, snapshot, navigator, plan, board)
        # Owner 2026-11-04: the answer to the summons, ahead of the plan's own order.
        or summon_response.key(policy, snapshot)
        or resist_potion.key(policy, snapshot)
        or _light_key(policy, snapshot, navigator, plan)
        or _fight(policy, snapshot, profile, navigator, plan, board)
    )
