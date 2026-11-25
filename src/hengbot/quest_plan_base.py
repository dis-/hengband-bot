"""The scaffolding the fixed-quest floor plans share.

quest_find_exit (FIND_EXIT, Q18), quest_room_sweep (the room-by-room KILL_ALL walk) and
quest25_battle (Q25's phase battle) each answer their own floor, and each needs the same pieces
around its own order: the navigator of the floor, the board's enemies, the map to walk and a
step along a walk, the shot, and the survival rungs (cure, Healing, haste, rest, the below-line
Teleportation and the Recall below the scroll floor, the drained stats).  They live here once
(maintainability review 2026-11-09, problem 9); the modules that had them re-export the names,
and each rule keeps the owner's words in the module that decided it (quest_find_exit's and
quest_room_sweep's docstrings).

Nothing here is persisted: the floor's state is the QuestFloorNavigator's (quest_navigator).
"""

from __future__ import annotations

from typing import NamedTuple

from hengbot import (
    ability_sources,
    line_of_fire,
    me_ranged_first,
    once_quest_recall,
    quest_exposure,
    quest_no_teleport,
    quest_room_light,
    speed_dose,
    status_cure,
    walk_vetoes,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, RESTORE_POTION_SVAL_BY_STAT, SV_POTION_HEALING, TVAL_POTION
from hengbot.policy_constants import CLOSE_KEY, DIRECTION_KEYS, HEAL_POTION_SVALS, PACK_CAPACITY, REST_MACRO
from hengbot.quest_navigator import PICKUP_KEY, QuestFloorNavigator

MELEE_REASON = "quest-strategy:melee"
HOLD_REASON = "quest-strategy:hold"
RECALL_REASON = "emergency:recall-quest-fail"
HEAL_REASON = "quest-strategy:heal"
CURE_REASON = "quest-strategy:cure"
SPEED_REASON = "quest-strategy:quaff-speed"
TELEPORT_REASON = "quest-strategy:sweep-teleport"
RESTORE_REASON = "quest-strategy:sweep-restore"
FLOOR_RESTORE_WALK_REASON = "quest-strategy:floor-restore-walk"
FLOOR_RESTORE_PICKUP_REASON = "quest-strategy:floor-restore-pickup"
# Owner 2026-11-23 「数マス以内なら拾って飲む」: the walking steps to a floor restore potion
# (quest_summon_answer's DISENGAGE_WALK_STEPS 3 is a step aside; 5 is a few cells, not the map).
FLOOR_RESTORE_MAX_STEPS = 5
STARVING = frozenset({"weak", "fainting"})
PERMANENT_HASTE_SPEED = 120
DEFAULT_SPEED_RATIO = 0.5


def steps_aside_for_food(policy, snapshot) -> bool:
    """A floor plan leaves the board to the survival rungs: starving, or a meal is due.

    Weak-or-worse leaves by the exit stairs when nothing is edible (_survival_gate_key).
    Merely hungry, the plan keeps the floor only when nothing is edible
    (_starvation_lets_quest_finish); with something edible and no hostile near, the gate's
    rule 「Hungry with something edible: eat now」 holds on a plan floor too.  n1-c life-178
    (2026-11-09, Q25 ambush hold): hungry with a charged wand, the hold answered '5' until
    weak, twice.
    """
    return snapshot.player.food_state in STARVING or policy._hunger_meal_due(snapshot)


# -- the floor ----------------------------------------------------------------------


def _navigator(policy, snapshot, quest_id: int) -> QuestFloorNavigator:
    navigator = policy._quest_navigators.setdefault(
        quest_id, QuestFloorNavigator(quest_id, policy._quest_knowledge[quest_id].battlefield))
    navigator.allow_diagonal = True
    navigator.reset_for_floor(snapshot.floor_key)
    return navigator


def _cell(position: Position) -> tuple[int, int]:
    return position.y, position.x


def race_flags(policy, race) -> frozenset:
    """The race's flags as the monster knowledge reads them (empty for an unknown race)."""
    return frozenset(getattr(policy._monrace_knowledge.get(race), "flags", frozenset()) or ())


def flags_never_move(flags, *, in_water: bool = False) -> bool:
    """The one reading of "it never steps toward the player" from race flags (``never_moves``)."""
    flags = frozenset(flags or ())
    return "NEVER_MOVE" in flags or (in_water and "AQUATIC" in flags)


def never_moves(policy, race, *, in_water: bool = False) -> bool:
    """The one "never moves" predicate of the quest plans (contradiction audit 2026-11-25 (a)-1).

    NEVER_MOVE never steps (monster-move.cpp process_monster_movement).  ``in_water``: an AQUATIC
    one steps only on water (monster-info.cpp monster_can_cross_terrain), so it never comes to the
    dry cells the plans stand on either; the callers that ask of dry ground pass it (QUEST_33's
    lure and its closing on, quest_summon_answer), the others ask of NEVER_MOVE alone."""
    return flags_never_move(race_flags(policy, race), in_water=in_water)


def _never_moves(policy, monster) -> bool:
    """``never_moves`` of a board monster (NEVER_MOVE alone)."""
    return never_moves(policy, monster.race_id)


def _rank(profile, monster) -> tuple[int, int]:
    targets = profile.priority_targets
    index = targets.index(monster.race_id) if monster.race_id in targets else len(targets)
    return index, monster.hp


def _door_is_closed(snapshot, cell: tuple[int, int]) -> bool:
    grid = snapshot.grid_at(Position(*cell))
    return grid is None or not grid.known or grid.is_closed_door


def fires_at_player(policy, snapshot, monster) -> bool:
    """An awake hostile that hurts the player from where it stands: a line of fire to him (the
    ``danger`` reading, what may hurt the player, owner 2026-11-17 Q5 「危険の判定は危険用に揃える」)
    and a predicted damage above zero on the next turn.

    n1-c life-220 (Quest 33, 2026-11-22 19:35:52-19:36:01): two 船幽霊 in the deep water at [4,41]
    and [5,41], known by telepathy only (the board's ``detected_monsters``; its ``visible_monsters`` is
    the player's view, bot-json-output.cpp make_visible_monsters_json), cast water bolts at the player
    on [1,27] for 70 boards; the board read no enemy, and the plan held '5' 23 times from HP 811 to
    death."""
    return (not monster.asleep and line_of_fire.danger(policy, snapshot, monster)
            and policy._predicted_damage(snapshot, [monster], turns=1) > 0)


class Contract(NamedTuple):
    """What a floor plan says of its floor, once, for every walk and rung of it (whole-bot
    maintainability review 2026-11-23 K1, (a)-4): the plans had each kept these to themselves, and
    only quest25_battle's ``_path`` knew the cells no walk may pass.

    ``stand_cells``: the (y, x) cells the plan stands and fights on (its chokes, its stands).
    ``no_pass``: the (y, x) cells no step of the plan enters (``plan_walk`` refuses one); the cells
    a walk merely keeps off while a way off them leads on (left_cells for quest_find_exit and
    quest_room_sweep) are not these.  ``recovery_line``: the HP ratio below which the plan rests on
    a quiet board (its ``rest_below_ratio``), None where it names none."""
    stand_cells: frozenset = frozenset()
    no_pass: frozenset = frozenset()
    recovery_line: float | None = None


NO_CONTRACT = Contract()


def recovery_line_of(plan) -> float | None:
    """The plan's ``rest_below_ratio`` as the contract's recovery line."""
    value = (plan or {}).get("rest_below_ratio")
    return None if value is None else float(value)


class Board:
    """The enemies of one board, as a room plan weighs them (quest_room_sweep; quest25_battle
    leaves nothing alone).  ``left_alone``: the races seen but no target yet.

    ``firing``: the hostiles known by detection or telepathy only (not in the player's view) that
    hurt him from where they stand (``fires_at_player``).  They act on the player as one in view
    does, so the board has an enemy (``enemy``) and the plan's survival rungs answer it: its 即死
    escape, the withdrawal line, the heal line, the haste (QUEST_33, owner 2026-11-19; the haste in
    a Magic-Eater's fights, owner 2026-11-04).  A telepathy-shown monster with a line from the
    player can be aimed at (monster-update.cpp update_telepathy_sight sets ``ml``;
    target-preparation.cpp target_able needs ``ml`` and projectable), so the plans' shots may take
    them (quest_room_sweep ``_fight``, quest_summon_answer ``_strike_around``)."""

    def __init__(self, policy, snapshot, profile, left_alone):
        position = snapshot.player.position
        known = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                 if monster.hostile]
        seen = [monster for monster in known if monster.perception != "detected"]
        self.left_alone = [monster for monster in seen if monster.race_id in left_alone]
        self.occupied = {monster.position for monster in seen}
        self.in_view = sorted(
            (monster for monster in seen if monster.race_id not in left_alone),
            key=lambda monster: _rank(profile, monster))
        self.beside = [monster for monster in self.in_view
                       if monster.position.distance_to(position) <= 1]
        # What acts on the player now.  The name is _speed's.
        self.coming_in_view = [monster for monster in self.in_view if not monster.asleep]
        self.mobile = [monster for monster in self.coming_in_view
                       if not _never_moves(policy, monster)]
        self.pulling = ()
        self.hit_by_unseen = once_quest_recall._hit_by_unseen(policy, snapshot)
        self.firing = [monster for monster in known
                       if monster.perception == "detected" and monster.race_id not in left_alone
                       and fires_at_player(policy, snapshot, monster)]
        # The plan's contract (``Contract``): the plan that builds the board sets its own.
        self.contract = NO_CONTRACT

    @property
    def enemy(self) -> bool:
        return bool(self.in_view or self.hit_by_unseen or self.firing)

    @property
    def acting(self) -> list:
        """What acts on the player now: the awake hostiles in view and those firing at him."""
        return [*self.coming_in_view, *self.firing]


# -- the way --------------------------------------------------------------------------


def _terrain_of(navigator, snapshot, *, water: bool) -> dict:
    """The map to walk: every door passes (_step_toward opens it); deep water only when
    asked, since hp-mp-processor.cpp drowns the overweight and nothing else needs it."""
    kinds = {"door": "passage"}
    if not water:
        kinds["deep_water"] = "wall"
    return {cell: kinds.get(kind, kind) for cell, kind in navigator.battlefield.terrain.items()}


def _open_doors(navigator, snapshot) -> frozenset:
    return frozenset(cell for cell, kind in navigator.battlefield.terrain.items()
                     if kind == "door" and not _door_is_closed(snapshot, cell))


def _open_terrain(navigator, snapshot) -> dict:
    """The map as lines cross it: through the doors as the board shows them."""
    return {**navigator.battlefield.terrain, **{cell: "floor" for cell in _open_doors(navigator, snapshot)}}


def _least_exposed_walk(navigator, snapshot, exposure, start, goals, taken) -> list:
    """quest_exposure.least_exposed_path over the map from ``start``: dry first, through deep
    water only from where no dry walk leads (a teleport can land on a shore).  A player standing
    in the trees or over a dark pit (a landing there, levitating) walks out over them only when no
    other walk leads (``_pocket_ground``)."""
    for water in (False, True):
        terrain = _terrain_of(navigator, snapshot, water=water)
        terrain[start] = "floor"
        path = quest_exposure.least_exposed_path(terrain, exposure, start, goals, taken)
        if path:
            return path
    ground = _pocket_ground(navigator, snapshot, start)
    if ground:
        terrain = {**_terrain_of(navigator, snapshot, water=False), **{cell: "floor" for cell in ground}}
        terrain[start] = "floor"
        return quest_exposure.least_exposed_path(terrain, exposure, start, goals, taken)
    return []


def _pocket_ground(navigator, snapshot, start) -> frozenset:
    """The trees, and over a levitating player's feet the dark pits, the player stands among:
    the cells of those kinds joined to ``start`` (the game lets him enter them: TREE has MOVE,
    DARK_PIT CAN_FLY for a levitating player, player-move.cpp player_can_enter).  Empty when he
    stands on the walked ground.  n1-b life-418 (Quest 33, 2026-11-25 13:31): a levitating
    Magic-Eater put on [20,42], a dark pit between two tree columns, had no walk out of them; every
    member was left as no walk reaches it and the sweep stopped by name
    (quest:blocked:sweep-nothing-comes) with 巨大火アリ a few steps away."""
    terrain = navigator.battlefield.terrain
    kinds = set(quest_exposure.TREE_KINDS)
    if ability_sources.has_ability(snapshot.player, "levitation"):
        kinds |= quest_exposure.PIT_KINDS
    if terrain.get(start) not in kinds:
        return frozenset()
    found, frontier = {start}, [start]
    while frontier:
        y, x = frontier.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell = (y + dy, x + dx)
                if cell not in found and terrain.get(cell) in kinds:
                    found.add(cell)
                    frontier.append(cell)
    return frozenset(found)


def _path_step(policy, snapshot, path: list[Position], reason: str) -> str | None:
    if len(path) < 2:
        return None
    return plan_walk(policy, snapshot, path[1], reason, reach=path[-1])


def _yx(cell) -> tuple[int, int]:
    return (cell.y, cell.x) if isinstance(cell, Position) else (int(cell[0]), int(cell[1]))


def plan_walk(policy, snapshot, target, reason: str | None = None, *, reach=None,
              no_pass=frozenset()) -> str | None:
    """The one step of every floor plan's walk (whole-bot maintainability review 2026-11-23 K1,
    (a)-4; scripts/dungeon_ladder_lint.py fails a plan module that steps by ``_step_toward``
    itself): toward ``target`` (a Position or a (y, x) cell), under ``reason`` (None: the reason the
    caller set), the walk's end ``reach`` declared, as every plan's walk did on its own.

    A ``target`` among the contract's ``no_pass`` cells is not stepped onto: None, and the plan
    answers the board otherwise (quest25_battle holds).  ``_step_toward`` composes the step: a closed
    door beside opens (``o`` + direction), a known trap is searched or disarmed, and the warning's
    refusal stays its own reason (policy_navigation)."""
    if _yx(target) in no_pass:
        return None
    if reason is not None:
        policy.last_reason = reason
    if reach is not None:
        policy._declare_reach(reach if isinstance(reach, Position) else Position(*_yx(reach)))
    return policy._step_toward(snapshot, target if isinstance(target, Position) else Position(*_yx(target)))


def _direction(here: Position, cell: tuple[int, int]) -> str:
    """The direction key from ``here`` toward the adjacent ``cell``."""
    y, x = cell
    return DIRECTION_KEYS[((y > here.y) - (y < here.y), (x > here.x) - (x < here.x))]


def plan_door(policy, snapshot, door, reason: str, *, close: bool = False) -> str | None:
    """The plan's open or close of the door ``door`` beside the player, the one entry for both.

    Open: the step toward it (``_step_toward`` composes ``o`` + direction with the lock and jam
    counts).  Close: ``c`` + direction.  Either way observed_input sends the command letter alone and
    releases the direction only at the observed direction question (EASY_DIRECTION_COMMANDS:
    easy_open takes the one door around without asking, n1-c life-221 2026-11-23 05:00:39)."""
    policy.last_reason = reason
    if close:
        return CLOSE_KEY + _direction(snapshot.player.position, _yx(door))
    return policy._step_toward(snapshot, Position(*_yx(door)))


# -- the shot -------------------------------------------------------------------------


def _aligned(snapshot, target) -> bool:
    here = snapshot.player.position
    dy, dx = abs(target.position.y - here.y), abs(target.position.x - here.x)
    return dy == 0 or dx == 0 or dy == dx


def _shot(policy, snapshot, target) -> str | None:
    """An absorbed power along a clear ray by direction, off the rays at the target's cell,
    else the launcher; each weighed against the launcher as everywhere else.

    Off the rays the direction would fly past the target, so the power is aimed at its cell
    (me_ranged_first.off_ray_key); n1-b life-411 (Quest 33, 2026-11-19) held 1,679 boards
    with a Rock troll in a clear line of fire off the rays while that gate fired nothing."""
    if _aligned(snapshot, target):
        device = me_ranged_first.attack_key(policy, snapshot, target)
    else:
        device = me_ranged_first.off_ray_key(policy, snapshot, target)
    return device or policy._ranged_attack_key(snapshot, [target], [])


# -- survival -------------------------------------------------------------------------


def _stronger_healing(item) -> bool:
    return (item.is_potion and item.aware and item.sval in HEAL_POTION_SVALS
            and item.sval > SV_POTION_HEALING)


def _healing_potion(policy, snapshot):
    """HP recovery on this floor: Healing, or stronger; never Cure Critical."""
    return policy._find_exact_potion(snapshot, SV_POTION_HEALING) or policy._first_item(
        snapshot, _stronger_healing)


def healing_potion_count(policy, snapshot) -> int:
    """How many potions ``_healing_potion`` draws from: Healing and the stronger ones."""
    return policy._exact_potion_count(snapshot, SV_POTION_HEALING) + sum(
        item.count for item in snapshot.inventory if _stronger_healing(item))


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
    """Haste while it is off, for a row that lives by it, else when the fight is heavy; the fight is
    what acts on the player (``Board.acting``: in view, or firing at him from out of view).

    An ``always_hasted`` row doses whatever the permanent speed (owner 2026-11-19, verbatim
    「+10 以上でも飲んで読む」: the haste's +10 adds to any speed, player-speed.cpp
    time_effect_bonus, and its floors are read at the permanent speed + 10,
    attack_expectation.always_hasted_speed).  The heavy-fight dose of the other rows still
    stops at PERMANENT_HASTE_SPEED."""
    if not board.acting or policy._player_hasted(snapshot):
        return None
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    if not force.get("always_hasted"):
        if snapshot.player.speed >= PERMANENT_HASTE_SPEED:
            return None
        ratio = float(profile.consumable_plan.get("speed_potion_use_when", {}).get(
            "expected_damage_hp_ratio_min", DEFAULT_SPEED_RATIO))
        projected = policy.threat_prediction(snapshot, board.acting, turns=3)
        if projected["operational_total"] < ratio * snapshot.player.hp:
            return None
    return speed_dose.key(policy, snapshot, SPEED_REASON)


def survival_stage(policy, snapshot, profile, board, *, enemy: bool | None = None,
                   restore=None, haste: bool = True) -> str | None:
    """The survival stage every branch of every floor plan enters (dungeon_ladder FLOOR_PLANS;
    whole-bot maintainability review 2026-11-23 K1, (a)-4: the plans had each kept their own
    cure, Healing, haste and restore, and a branch could go without one).

    On a board with an enemy (``enemy``; None reads ``board.enemy``, which counts the hostiles known
    by telepathy or detection that fire at the player, ``Board.firing``): the cure, the Healing at
    the plan's heal line, the haste (``_cure``, ``_heal``, ``_speed``).  On a quiet board: the drained
    abilities' restore (``restore``, the plan's own, else ``_restore``).  The 1-turn 即死 heads each
    enemy branch above it (threat_tiers.instant_death_key), and the quiet board's recovery (the
    rest below the contract's ``recovery_line``) is the plan's own rung (dungeon_ladder
    QUIET_RECOVERY), where its walks out of the fire come before it.

    ``haste`` False: the plan doses its haste by a rule of its own on this board (quest_find_exit on
    the cells the casters reach: owner 2026-11-22 「加速してから入る」, the dose before a step onto
    them, ``_haste_before_shouted``; the walk out of their reach comes before a fight's dose)."""
    if board.enemy if enemy is None else enemy:
        return (_cure(policy, snapshot)
                or _heal(policy, snapshot, profile)
                or (_speed(policy, snapshot, profile, board) if haste else None))
    return (restore or _restore)(policy, snapshot)


def _rest(policy, snapshot, plan, board) -> str | None:
    """Below the plan's ratio on a board with nothing to answer: rest, however low.  The ratio is
    the contract's ``recovery_line`` (the plan's ``rest_below_ratio``)."""
    player = snapshot.player
    line = getattr(board, "contract", NO_CONTRACT).recovery_line
    if line is None:
        line = float(plan["rest_below_ratio"])
    if (player.hp_ratio >= line or player.confused or board.pulling
            or player.food_state not in {"normal", "full", "gorged"}):
        return None
    policy.last_reason = "rest"
    return REST_MACRO


def _quaff_recovery(policy, snapshot) -> str | None:
    potion = _healing_potion(policy, snapshot)
    if potion is None:
        return None
    policy.last_reason = HEAL_REASON
    return reserved_item_command(policy, snapshot, "quaff", potion)


def _below_line(policy, snapshot, profile, navigator, *, line=True) -> str | None:
    """Teleportation; after one that left an enemy on the player, a potion.  ``line=False``:
    the plan's escape asked by its 即死 rung, whatever the HP (threat_tiers.instant_death_key)."""
    if line and snapshot.player.hp_ratio > float(profile.abort_conditions["hp_ratio"]):
        navigator.sweep_heal_next = False
        return None
    if quest_no_teleport.q25_hall_forbids(policy, snapshot):
        # Owner 2026-11-12 「回復とテレポートアウェイで対処する」: Teleport Away in Teleportation's
        # place, then the potion, as Teleportation was followed by it.
        if not navigator.sweep_heal_next and (away := hall_away_key(policy, snapshot)) is not None:
            navigator.sweep_heal_next = True
            return away
        navigator.sweep_heal_next = False
        return _quaff_recovery(policy, snapshot)
    from hengbot import quest_summon_answer  # it reads this module's walks

    quaffed = False
    if navigator.sweep_heal_next:
        navigator.sweep_heal_next = False
        quaffed = True
        if (key := _quaff_recovery(policy, snapshot)) is not None:
            return key
    # QUEST_33 (owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」): the absorbed
    # Teleportation in the scroll's place while it has a charge (quest_summon_answer.ABSORBED_FIRST_QUESTS).
    if (absorbed := quest_summon_answer.absorbed_teleport_key(policy, snapshot, TELEPORT_REASON)) is not None:
        navigator.sweep_heal_next = True
        return absorbed
    scroll = policy._find_teleport_scroll(snapshot) if policy._can_read_scrolls(snapshot) else None
    if scroll is None:
        return None if quaffed else _quaff_recovery(policy, snapshot)
    navigator.sweep_heal_next = True
    policy.last_reason = TELEPORT_REASON
    return policy._read_key(snapshot, scroll)


AWAY_REASON = "quest-strategy:teleport-away"


def hall_away_key(policy, snapshot, candidates=None, reason: str = AWAY_REASON) -> str | None:
    """Teleport Away at the most dangerous moving hostile in view on a beam's line, else None.

    The absorbed rod or wand first, then a carried rod or wand (teleport_follower's order).  Not
    at a never-moving one (its place is the plan's), nor at one the game surely keeps
    (effect_monster_away_resist: RES_TELE with UNIQUE or RES_ALL).  The wand's bolt is a beam
    (spells-launcher.cpp fire_beam with TELE_AWAY): aimed by direction along an 8-way line.
    ``candidates``: the monsters to choose from (None: every physical hostile in view);
    ``reason``: the reason the key is recorded under (the absorbed cast adds its suffix)."""
    from hengbot import me_absorbed_substitutes, me_powers, teleport_follower

    if not teleport_follower._aim_ready(snapshot):
        return None
    here = snapshot.player.position
    aimed = []
    for monster in (policy._physical_hostiles(snapshot) if candidates is None else candidates):
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        flags = getattr(knowledge, "flags", frozenset())
        if knowledge is None or flags_never_move(flags) or (
                "RES_TELE" in flags and flags & {"UNIQUE", "RES_ALL"}):
            continue
        direction = me_powers.beam_direction(policy, snapshot, here, monster.position)
        if direction is not None:
            aimed.append((policy._predicted_damage(snapshot, [monster], turns=1),
                          -here.distance_to(monster.position), -monster.index, monster, direction))
    if not aimed:
        return None
    *_order, target, direction = max(aimed, key=lambda row: row[:3])
    absorbed = teleport_follower._absorbed(policy, snapshot)
    if absorbed is not None:
        key = me_absorbed_substitutes.cast_key(
            policy, snapshot, me_absorbed_substitutes.POWERS[absorbed], direction, blind_ok=True)
        if key is not None:
            policy.last_reason = reason + me_absorbed_substitutes.CAST_SUFFIX
            return key
    carried = teleport_follower._carried(snapshot)
    if carried is None:
        return None
    kind, item = carried
    key = reserved_item_command(policy, snapshot, kind, item, suffix=direction)
    if key is not None:
        policy.last_reason = reason
    return key


def _give_up(policy, snapshot, profile) -> str | None:
    if not once_quest_recall.below_scroll_floor(policy, snapshot, profile):
        return None
    return once_quest_recall.read_key(policy, snapshot, RECALL_REASON)


_RESTORES = (("restore_exp", lambda player: player.exp_drained),
             ("restore_str", lambda player: "str" in player.drained_stats))


def _restore(policy, snapshot) -> str | None:
    """A quiet board: what the drains took, by the potions the plan carries for them, then any other
    drained ability by its own carried restore potion.

    QUEST_25 「経験値復活の薬と腕力復活の薬を2本ずつ持参し、敵がいない時に下がっていれば飲む」 names the
    potions the plan brings; the town's rule (``_stat_restore_quaff_key``: a drained ability, its potion
    carried, no hostile) drinks every one.  n1-c life-221 (2026-11-23 05:00-05:03, Q25): a shadow demon
    drained INT 18→17 (and WIS); the rest of the quest was fought on the raised absorbed-power fail
    rates, and the Restore Intelligence it picked up at the closing sweep was drunk only in town.  A
    carried restore potion of a drained ability is drunk here on the same quiet board."""
    for name, drained in _RESTORES:
        if drained(snapshot.player):
            potion = quest_room_light.carried_potion(policy, snapshot, name)
            if potion is not None:
                policy.last_reason = RESTORE_REASON
                return reserved_item_command(policy, snapshot, "quaff", potion)
    for stat in snapshot.player.drained_stats:
        potion = policy._carried_restore_potion(snapshot, stat)
        if potion is not None:
            policy.last_reason = RESTORE_REASON
            return reserved_item_command(policy, snapshot, "quaff", potion)
    return None


def _floor_restore_cells(policy, snapshot) -> frozenset:
    """The found cells holding an aware restore potion of a drained ability not carried."""
    wanted = {RESTORE_POTION_SVAL_BY_STAT[stat] for stat in snapshot.player.drained_stats
              if stat in RESTORE_POTION_SVAL_BY_STAT
              and policy._carried_restore_potion(snapshot, stat) is None}
    ids_by_cell = getattr(snapshot, "found_item_ids", None) or {}
    if not wanted or not ids_by_cell:
        return frozenset()
    cells = set()
    for row in getattr(snapshot, "found_items", None) or ():
        position = Position(row[0], row[1])
        ids = ids_by_cell.get(position) or ()
        if any(tval == TVAL_POTION and identity is not None and identity.get("sval") in wanted
               for tval, identity in zip(row[3:], ids)):
            cells.add(position)
    return frozenset(cells)


def _floor_restore_first_step(policy, snapshot, cells) -> tuple[Position, Position] | None:
    """The first step and the cell of the nearest ``cells`` within FLOOR_RESTORE_MAX_STEPS."""
    start = snapshot.player.position
    refused = walk_vetoes.retreat_left(policy, snapshot)
    seen = {start}
    frontier = [(start, None)]
    for _depth in range(FLOOR_RESTORE_MAX_STEPS):
        following = []
        for position, first in frontier:
            for neighbor in policy._walkable_neighbors(snapshot, position):
                if neighbor in seen or neighbor in refused:
                    continue
                seen.add(neighbor)
                step = neighbor if first is None else first
                if neighbor in cells:
                    return step, neighbor
                following.append((neighbor, step))
        frontier = following
    return None


def floor_restore_key(policy, snapshot) -> str | None:
    """Owner 2026-11-23 「数マス以内なら拾って飲む」: on the plan's quiet board, a known restore potion
    of a drained ability on the floor within FLOOR_RESTORE_MAX_STEPS walking steps is walked to and
    picked up (``_restore`` then drinks it on the next quiet board) before the plan goes on.

    n1-c life-221 (2026-11-23 05:00:11-05:03:48, Q25): a shadow demon drained INT on [5,1]; the
    Restore Intelligence lay found on [7,1], two steps off, and the plan held and rested beside it
    until its closing sweep picked it up.  Not with a full pack (the pickup could not take it)."""
    if len(snapshot.inventory) >= PACK_CAPACITY:
        return None
    cells = _floor_restore_cells(policy, snapshot)
    if not cells:
        return None
    here = snapshot.player.position
    if here in cells:
        row = next((row for row in snapshot.found_items or ()
                    if (row[0], row[1]) == (here.y, here.x)), None)
        count = row[2] if row is not None else 1
        policy.last_reason = FLOOR_RESTORE_PICKUP_REASON
        return PICKUP_KEY + ("a" * count if count > 1 else "")
    found = _floor_restore_first_step(policy, snapshot, cells)
    if found is None:
        return None
    step, target = found
    return plan_walk(policy, snapshot, step, FLOOR_RESTORE_WALK_REASON, reach=target)
