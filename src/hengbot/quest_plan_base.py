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

from hengbot import me_ranged_first, once_quest_recall, quest_exposure, quest_no_teleport, quest_room_light, speed_dose, status_cure
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, SV_POTION_HEALING
from hengbot.policy_constants import HEAL_POTION_SVALS, REST_MACRO
from hengbot.quest_navigator import QuestFloorNavigator

MELEE_REASON = "quest-strategy:melee"
HOLD_REASON = "quest-strategy:hold"
RECALL_REASON = "emergency:recall-quest-fail"
HEAL_REASON = "quest-strategy:heal"
CURE_REASON = "quest-strategy:cure"
SPEED_REASON = "quest-strategy:quaff-speed"
TELEPORT_REASON = "quest-strategy:sweep-teleport"
RESTORE_REASON = "quest-strategy:sweep-restore"
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


def _never_moves(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and "NEVER_MOVE" in knowledge.flags


def _rank(profile, monster) -> tuple[int, int]:
    targets = profile.priority_targets
    index = targets.index(monster.race_id) if monster.race_id in targets else len(targets)
    return index, monster.hp


def _door_is_closed(snapshot, cell: tuple[int, int]) -> bool:
    grid = snapshot.grid_at(Position(*cell))
    return grid is None or not grid.known or grid.is_closed_door


class Board:
    """The enemies of one board, as a room plan weighs them (quest_room_sweep; quest25_battle
    leaves nothing alone).  ``left_alone``: the races seen but no target yet."""

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

    @property
    def enemy(self) -> bool:
        return bool(self.in_view or self.hit_by_unseen)


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
    water only from where no dry walk leads (a teleport can land on a shore)."""
    for water in (False, True):
        terrain = _terrain_of(navigator, snapshot, water=water)
        terrain[start] = "floor"
        path = quest_exposure.least_exposed_path(terrain, exposure, start, goals, taken)
        if path:
            return path
    return []


def _path_step(policy, snapshot, path: list[Position], reason: str) -> str | None:
    if len(path) < 2:
        return None
    policy.last_reason = reason
    policy._declare_reach(path[-1])
    return policy._step_toward(snapshot, path[1])


# -- the shot -------------------------------------------------------------------------


def _aligned(snapshot, target) -> bool:
    here = snapshot.player.position
    dy, dx = abs(target.position.y - here.y), abs(target.position.x - here.x)
    return dy == 0 or dx == 0 or dy == dx


def _shot(policy, snapshot, target) -> str | None:
    """An absorbed power along a clear ray, else the launcher; both as everywhere else."""
    device = me_ranged_first.attack_key(policy, snapshot, target) if _aligned(snapshot, target) else None
    return device or policy._ranged_attack_key(snapshot, [target], [])


# -- survival -------------------------------------------------------------------------


def _healing_potion(policy, snapshot):
    """HP recovery on this floor: Healing, or stronger; never Cure Critical."""
    return policy._find_exact_potion(snapshot, SV_POTION_HEALING) or policy._first_item(
        snapshot, lambda item: item.is_potion and item.aware and item.sval in HEAL_POTION_SVALS
        and item.sval > SV_POTION_HEALING)


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


def _rest(policy, snapshot, plan, board) -> str | None:
    """Below the plan's ratio on a board with nothing to answer: rest, however low."""
    player = snapshot.player
    if (player.hp_ratio >= float(plan["rest_below_ratio"]) or player.confused or board.pulling
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


AWAY_REASON = "quest-strategy:teleport-away"


def hall_away_key(policy, snapshot) -> str | None:
    """Teleport Away at the most dangerous moving hostile in view on a beam's line, else None.

    The absorbed rod or wand first, then a carried rod or wand (teleport_follower's order).  Not
    at a never-moving one (its place is the plan's), nor at one the game surely keeps
    (effect_monster_away_resist: RES_TELE with UNIQUE or RES_ALL).  The wand's bolt is a beam
    (spells-launcher.cpp fire_beam with TELE_AWAY): aimed by direction along an 8-way line."""
    from hengbot import me_absorbed_substitutes, me_powers, teleport_follower

    if not teleport_follower._aim_ready(snapshot):
        return None
    here = snapshot.player.position
    aimed = []
    for monster in policy._physical_hostiles(snapshot):
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        flags = getattr(knowledge, "flags", frozenset())
        if knowledge is None or "NEVER_MOVE" in flags or (
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
            policy.last_reason = AWAY_REASON + me_absorbed_substitutes.CAST_SUFFIX
            return key
    carried = teleport_follower._carried(snapshot)
    if carried is None:
        return None
    kind, item = carried
    key = reserved_item_command(policy, snapshot, kind, item, suffix=direction)
    if key is not None:
        policy.last_reason = AWAY_REASON
    return key


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
