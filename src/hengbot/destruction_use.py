"""*Destruction* before the scroll a rung reads away from a threat.

Owner 2026-11-04: 「成功率80%以上の*破壊*を使えるとき、強敵からのテレポートによる逃走に
代わり*破壊*を使用する。」  Answers: 「杖と取り込んだ力だけ」; 「脅威が範囲内に見える時に
使用。また、ランダムクエストの階ではターゲット以外の脅威を排除するのに使う。傷を負った
ターゲットは巻き込まない場面に限定する。」; 「治して階の探索を続ける。破壊の回数だけでは
帰還しない。」; 「巻物が無くても使う」 (with no Teleportation, before Phase Door and Recall).
50F+ 「使える手段がある時だけ解く」: ``holds_means`` is the one predicate of
policy_constants.destruction_dive_permitted, for arrivals and descents only.  With the
means gone on such a floor (rate below 80%, charges spent) no further descent or new
arrival is allowed and the existing return rules decide when to leave: the floor itself
is no gap (``gap_here``), and a charged list after the inn permits it again.

Game (C:/hengband/src):
 * spell-kind/spells-floor.cpp destroy_area: refused on a fixed quest floor and on
   the surface.  Radius 13 + randint0(5) (cmd-usestaff.cpp:282; the Powerful
   Activation's 18 is never cast here).  Every monster is deleted (no experience)
   but a QUESTOR, which is healed fully and teleported away.  A dungeon guardian
   is not a QUESTOR (only the bounty of the floor's quest is set so,
   dungeon-processor.cpp:102).  Items and non-permanent terrain go, the map
   knowledge of the circle goes, and 「燃えるような閃光が発生した！」 is printed, with
   blindness 10+1d10 unless the player resists blindness or light.
 * A staff (object-use/use-execution.cpp): no blind or confused refusal, but
   confusion halves the skill, stun may refuse it, a Berserker always fails, a
   failure spends the turn and keeps the charge.  The absorbed power
   (cmd-magiceat.cpp) refuses a confused player; a failure spends the turn and
   keeps the charge.

Gates (``key``, asked by each rung before its read): the character is clear-headed (blindness
allowed, owner 2026-11-08 「盲目でも使う」); a means is reliable (``me_capability.RELIABLE_MIN_SUCCESS``, the
absorbed power first as in speed_dose); the floor is one the game destroys; the
most dangerous awake visible hostile other than the quest target is in
``GUARANTEED_RADIUS``; and no damaged target or guardian is in ``WORST_RADIUS``.  Anything
else leaves the rung's read as it was.

Owner 2026-11-05 (``sight_trigger_key``, SIGHT_TRIGGERS): some races are used on as soon
as one is awake in view in GUARANTEED_RADIUS, with no emergency, asked after the survival
rungs.  The same gates hold but for the most-dangerous test; a fixed quest floor is
refused by the game, and on a random quest floor only the target itself is no such race
(「ランダムクエストの階であってもターゲットでなければ*破壊*してよい」).

A use that printed no flash (a failure, the empty staff) or a key the game did
not take leaves the next ask to what the rung reads today: speed_dose's rule for
a failed cast on the survival rungs, with no retry number of its own.

The flash on a board (``observe``) ends the emergency without a town return:
``emergency:destruction`` is deliberately no member of EMERGENCY_ESCAPE_REASONS,
and the ladder's own return latch of that decision is undone.  What the player
knew of the circle is forgotten (``forget_circle``) before the board is merged
into the map memory, so a cell the game still shows comes back from the board.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from hengbot import (
    area_mapping, attack_expectation, disenchant_avoid, hunt_target, immobile_threat_memory, me_capability, summoner_wait,
)
from hengbot import me_absorbed_substitutes as substitutes
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_STAFF, Position, game_distance
from hengbot.town_hold import LOOT_OWNERS
from hengbot.policy_constants import (
    DESTRUCTION_GATE_DEPTH, DESTRUCTION_GATE_LABEL, EMERGENCY_RETURN_COUNT, PLAYER_CLASS_BERSERKER, ExplorationPathOutcome,
)


REASON = "emergency:destruction"
POWER = ("staff", SV_STAFF_DESTRUCTION)
STAFF = (TVAL_STAFF, SV_STAFF_DESTRUCTION)
STAFF_LEVEL = 50             # BaseitemDefinitions.jsonc id 307
GUARANTEED_RADIUS = 13       # cmd-usestaff.cpp:282 13 + randint0(5)
WORST_RADIUS = 17
FLASH = ("燃えるような閃光が発生した！", "There is a searing blast of light!")
MEMORY = "_destruction_use_memory"
# The races used on at first sight: (the reason's suffix, the test of a monster).
SIGHT_TRIGGERS = ((":disenchanter", disenchant_avoid.exposes_gear),)
# The triggers _emergency_item latches for the escape it is about to take.
LADDER_RETURN_TRIGGERS = frozenset({
    "emergency-summoner", "emergency-ranged-status-lock", "emergency-lethal-swarm",
})
# Floor memory the destroyed circle invalidates.  Sets of Position:
POSITION_SETS = (
    "_remembered_downstairs", "_remembered_upstairs", "_remembered_entrances",
    "_known_treasure", "_known_loot", "_deferred_loot", "_unseen_deferred_loot",
    "_safety_deferred_loot", "_nav_ledger_deferred_loot", "_loot_ledger_rearmed",
    "_loot_safety_rearmed", "_engagement_avoid_cells", "_engagement_owned_avoid_cells",
    "_paralyzer_avoid_cells", "_warning_refused_cells", "_probed_frontiers",
    "_processed_chest_positions", "_window_edge_goals",
)
# Sets and counters of (y, x):
YX_COLLECTIONS = (
    "_remembered_floor_t", "_remembered_door_t", "_remembered_rubble_t", "_remembered_wall_t",
    "_remembered_known_t", "_remembered_marked_t", "_blocked_doors", "_blocked_rubble",
    "_blocked_unknown", "_search_counts", "_wall_search_counts",
)
# Dicts keyed by Position:
POSITION_DICTS = (
    "_remembered_grids", "_remembered_grid_signatures", "_remembered_grid_sources",
    "_look_floor_items", "_look_floor_object_counts", "_remembered_paralyzers",
    "_one_step_explore_failures", "_hazard_cache", "_trap_warning_cells",
)
# Collections of (kind, Position):
KIND_POSITION_COLLECTIONS = ("_unverified_stairs", "_stair_rejection_strikes")
# Module memories of monsters and holds that may stand in the circle.
FORGET_VISIT = (summoner_wait, immobile_threat_memory, hunt_target)


@dataclass
class Memory:
    pending: tuple | None = None   # (floor, turn, position) of the last use
    fallback: tuple | None = None  # the floor whose next ask is the rung's own read
    entitled_floor: tuple | None = None  # the 50F+ floor where the means was last held


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


# -- the means ------------------------------------------------------------------

def _absorbed_key(policy, snapshot) -> str | None:
    """The reliable power (me_capability's counting row) with a charge here."""
    if me_capability.replacing_charges(policy, snapshot, STAFF) <= 0:
        return None
    return substitutes.cast_key(policy, snapshot, substitutes.POWERS[POWER], blind_ok=True)


def _reliable_staff(snapshot) -> bool:
    """use-execution.cpp's chance (attack_expectation) at the table's number."""
    if snapshot.player.class_id == PLAYER_CLASS_BERSERKER:
        return False
    success = attack_expectation.device_use_success(snapshot.player.device_skill, STAFF_LEVEL)
    return success * 100 >= me_capability.RELIABLE_MIN_SUCCESS


def _reliable_carried_staff(policy, snapshot):
    if not _reliable_staff(snapshot):
        return None
    return next((item for item in snapshot.inventory
                 if policy._is_destruction_staff(item) and item.known and item.charges > 0), None)


def _carried_key(policy, snapshot) -> str | None:
    staff = _reliable_carried_staff(policy, snapshot)
    return None if staff is None else reserved_item_command(policy, snapshot, "staff", staff)


def holds_means(policy, snapshot) -> bool:
    """A staff or absorbed power at 80%+ with a charge; the character's status now
    does not matter and a scroll is no means (owner 2026-11-04)."""
    return (me_capability.replacing_charges(policy, snapshot, STAFF) > 0
            or _reliable_carried_staff(policy, snapshot) is not None)


def gap_here(policy, snapshot, missing) -> frozenset:
    """``missing`` of the floor the player stands on: the *Destruction* label is no
    gap on a floor where the means was held; a floor reached without it (a warrior's
    trapdoor to 50F) keeps the label and returns."""
    memory = getattr(policy, MEMORY, None)
    if memory is not None and memory.entitled_floor == snapshot.floor_key:
        return frozenset(missing) - {DESTRUCTION_GATE_LABEL}
    return frozenset(missing)


# -- the scene ------------------------------------------------------------------

def _clear_headed(player) -> bool:
    """Owner 2026-11-08 「盲目でも使う」: blindness does not stop the use (neither the
    staff nor the ``m`` command refuses it, above); confusion still does."""
    return not (player.confused or player.hallucinated or player.stunned)


def _floor_destroyed(policy, snapshot) -> bool:
    """destroy_area refuses a fixed quest floor and the surface."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        return False
    return snapshot.floor_key[2] == 0 or policy._on_random_quest_floor(snapshot)


def _target_race(policy, snapshot) -> int | None:
    quest_id = policy._active_kill_quest_id(snapshot)
    quest = snapshot.quests.get(quest_id) if quest_id is not None else None
    return policy._quest_target_race_id(quest) if quest is not None else None


def _guardian_race(policy, snapshot) -> int | None:
    info = policy._dungeon_knowledge.get(snapshot.floor_key[0])
    if info is None or snapshot.dungeon_level != info.max_depth or info.guardian_id <= 0:
        return None
    return info.guardian_id


def _spared_in_circle(policy, snapshot, target) -> bool:
    """A damaged quest target (healed by the use) or the floor's guardian (deleted;
    the owner's words do not cover it, so the rung reads as today)."""
    guardian = _guardian_race(policy, snapshot)
    return any(
        game_distance(snapshot.player.position, monster.position) <= WORST_RADIUS
        and (monster.race_id == guardian
             or (monster.race_id == target and monster.hp < monster.max_hp))
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))


def _awake_in_view(policy, snapshot, target) -> list:
    """The awake visible hostiles but the target; none with an attacker the board
    does not show (the use would not reach it)."""
    if getattr(policy, "_unseen_attack_evidence", None) is not None:
        return []
    return [m for m in snapshot.visible_monsters
            if m.hostile and not m.asleep and m.race_id != target]


def _threat_in_range(policy, snapshot, target) -> bool:
    """The most dangerous awake visible hostile but the target is in the guaranteed
    radius."""
    awake = _awake_in_view(policy, snapshot, target)
    if not awake:
        return False
    here = snapshot.player.position
    worst = max(awake, key=lambda m: (policy._predicted_damage(snapshot, [m], turns=1),
                                      -game_distance(here, m.position)))
    return game_distance(here, worst.position) <= GUARANTEED_RADIUS


def _threat_in_reach(policy, snapshot, target, *, hostiles) -> bool:
    """Owner 2026-11-09 (question B, life-355): 「即死はテレポートで逃げる。射線が通っていないなど
    即死ではない場合は破壊による排除を優先する。」  Where a rung leaves ``hostiles`` and the board
    is not 即死, the threat need not be awake in view: the most dangerous of them but the target,
    seen or detected, awake or asleep, judged from contact (``threat_prediction(contact=True)``,
    as the tiers judge a far monster), is in the guaranteed radius; or the 11-04 test holds.  An
    attacker the board does not show still refuses the use (``_awake_in_view``'s rule)."""
    if _threat_in_range(policy, snapshot, target):
        return True
    if getattr(policy, "_unseen_attack_evidence", None) is not None:
        return False
    candidates = [m for m in hostiles if m.hostile and m.race_id != target]
    if not candidates:
        return False
    here = snapshot.player.position
    rows = policy.threat_prediction(snapshot, candidates, 1, contact=True)["monsters"]
    worst, _ = max(zip(candidates, rows), key=lambda pair: (
        pair[1].get("operational_contribution", 0), -game_distance(here, pair[0].position)))
    return game_distance(here, worst.position) <= GUARANTEED_RADIUS


def _scene_holds(policy, snapshot, in_range=_threat_in_range) -> bool:
    if not _clear_headed(snapshot.player) or not _floor_destroyed(policy, snapshot):
        return False
    target = _target_race(policy, snapshot)
    return (in_range(policy, snapshot, target)
            and not _spared_in_circle(policy, snapshot, target))


def _falls_back(memory, snapshot) -> bool:
    """The last use failed or its key was not taken: this ask is the rung's own."""
    if memory.pending is not None and memory.pending[:2] == (snapshot.floor_key, snapshot.turn):
        memory.pending = None
        return True
    if memory.fallback == snapshot.floor_key:
        memory.fallback = None
        return True
    return False


def key(policy, snapshot, *, in_range=_threat_in_range, suffix="", leaving=None) -> str | None:
    """The use before the rung's read, setting ``last_reason``; else None.

    ``leaving``: the hostiles a rung leaves on a board that is not 即死 (``_threat_in_reach``,
    owner 2026-11-09 B): the sensed T1 leave, the emergency ladder's escape off the 即死 board,
    the cornered flee of a leave the tiers decided.  On the 即死 board the ladder reads
    Teleportation first (owner 2026-11-08, policy_combat ``scroll_first``)."""
    if leaving is not None:
        in_range = partial(_threat_in_reach, hostiles=list(leaving))
    if _falls_back(_memory(policy), snapshot):
        return None
    if not _scene_holds(policy, snapshot, in_range):
        return None
    cast = _absorbed_key(policy, snapshot)
    used = cast or _carried_key(policy, snapshot)
    if used is None:
        return None
    policy.last_reason = REASON + suffix + (substitutes.CAST_SUFFIX if cast else "")
    _memory(policy).pending = (snapshot.floor_key, snapshot.turn, snapshot.player.position)
    return used


def usable(policy, snapshot, *, leaving=None) -> bool:
    """Whether ``key`` (with the same ``leaving``) would use the means on this board (no state
    is changed)."""
    memory = getattr(policy, MEMORY, None)
    if memory is not None and (
            (memory.pending is not None and memory.pending[:2] == (snapshot.floor_key, snapshot.turn))
            or memory.fallback == snapshot.floor_key):
        return False
    in_range = _threat_in_range if leaving is None else partial(_threat_in_reach, hostiles=list(leaving))
    if not _scene_holds(policy, snapshot, in_range):
        return False
    return _absorbed_key(policy, snapshot) is not None or _carried_key(policy, snapshot) is not None


def sight_trigger_key(policy, snapshot) -> str | None:
    """The use on a SIGHT_TRIGGERS race awake in the guaranteed radius, else None.
    A board with none does not ask ``key``, so it leaves a failed use's fallback alone."""
    for suffix, applies in SIGHT_TRIGGERS:
        in_range = partial(_race_in_range, applies=applies)
        if in_range(policy, snapshot, _target_race(policy, snapshot)):
            return key(policy, snapshot, in_range=in_range, suffix=suffix)
    return None


def _race_in_range(policy, snapshot, target, *, applies) -> bool:
    here = snapshot.player.position
    return any(game_distance(here, m.position) <= GUARANTEED_RADIUS
               and applies(policy, snapshot, m)
               for m in _awake_in_view(policy, snapshot, target))


# -- after the use --------------------------------------------------------------

def observe(policy, snapshot) -> None:
    """Every decision, before the board joins the map memory: settle the last use."""
    if snapshot.dungeon_level >= DESTRUCTION_GATE_DEPTH and holds_means(policy, snapshot):
        _memory(policy).entitled_floor = snapshot.floor_key
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    if memory.fallback is not None and memory.fallback != snapshot.floor_key:
        memory.fallback = None
    if memory.pending is None:
        return
    floor, turn, position = memory.pending
    if snapshot.floor_key != floor:
        memory.pending = None
    elif any(message in FLASH for message in snapshot.messages):
        memory.pending = None
        _end_emergency(policy)
        forget_circle(policy, position)
        area_mapping.note_destruction(policy, snapshot, position, WORST_RADIUS, GUARANTEED_RADIUS)
    elif snapshot.turn != turn:
        memory.pending = None
        memory.fallback = floor


def _end_emergency(policy) -> None:
    """「破壊の回数だけでは帰還しない」: drop the ladder's latch for this escape."""
    policy._emergency_escape_pending = False
    policy._emergency_return_active = False
    if (policy._last_return_trigger in LADDER_RETURN_TRIGGERS
            and policy._dive_emergencies < EMERGENCY_RETURN_COUNT):
        policy._returning_to_town = False
        policy._note_return_end()
        policy._last_return_trigger = None


def _discard(collection, stale) -> None:
    for each in [each for each in collection if stale(each)]:
        if isinstance(collection, set):
            collection.discard(each)
        else:
            del collection[each]


def forget_circle(policy, centre: Position) -> None:
    """Drop what the bot remembers of the destroyed circle (the worst radius); a
    cell that survived at 14-17 is shown by the next board again."""
    def in_circle(position) -> bool:
        return game_distance(centre, position) <= WORST_RADIUS

    for name in POSITION_SETS + POSITION_DICTS:
        _discard(getattr(policy, name, ()), in_circle)
    for name in YX_COLLECTIONS:
        _discard(getattr(policy, name, ()), lambda yx: in_circle(Position(*yx)))
    for name in KIND_POSITION_COLLECTIONS:
        _discard(getattr(policy, name, ()), lambda each: in_circle(each[1]))
    _discard(policy._exploration_ledger.mapped_areas,
             lambda area: game_distance(centre, Position(area[0], area[1])) <= WORST_RADIUS + area[2])
    _release_goals(policy, in_circle)
    _restart_progress_marks(policy)
    for module in FORGET_VISIT:
        module.forget_floor_visit(policy)


def _release_goals(policy, in_circle) -> None:
    """No route or goal may point into the changed map."""
    policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
    if policy._loot_target is not None and in_circle(policy._loot_target):
        policy._release_claim_goal("loot-destroyed", policy._loot_target,
                                   owners=LOOT_OWNERS)
        policy._loot_target = None
    if policy._treasure_target is not None and in_circle(policy._treasure_target):
        policy._release_claim_goal("treasure-destroyed", policy._treasure_target,
                                   owners=("fundraising",))
        policy._treasure_target = None
    if policy._chest_position is not None and in_circle(policy._chest_position):
        policy._chest_position = None
    if policy._choke_engagement_plan is not None:
        policy._release_choke_plan("destruction")
    policy._clear_unseen_retreat()
    policy._status_threat_latch = None
    policy._pending_stair_command = None


def _restart_progress_marks(policy) -> None:
    """The per-floor navigation accounting (as at a floor change): the known map
    just shrank, so its high marks would read new exploration as no progress."""
    policy._nav_ledger.reset()
    policy._nav_stall_count = 0
    policy._nav_exhausted = False
    policy._nav_escape_steps = 0
    policy._nav_known_high = 0
    policy._nav_progress_marker = None
    policy._oscillation_outcome_marker = None
    marked = len(policy._remembered_marked_t)
    policy._fruitless_disengage_marked_high = marked
    policy._exploration_ledger.marked_high = marked
