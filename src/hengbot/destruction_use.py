"""*Destruction* before the scroll a rung reads away from a threat.

Owner 2026-11-04: 「成功率80%以上の*破壊*を使えるとき、強敵からのテレポートによる逃走に
代わり*破壊*を使用する。」  Answers: 「杖と取り込んだ力だけ」; 「脅威が範囲内に見える時に
使用。また、ランダムクエストの階ではターゲット以外の脅威を排除するのに使う。傷を負った
ターゲットは巻き込まない場面に限定する。」; 「治して階の探索を続ける。破壊の回数だけでは
帰還しない。」; 「巻物が無くても使う」 (with no Teleportation, before Phase Door and Recall).
50F+ 「使える手段がある時だけ解く」: ``holds_means`` is the one predicate of
policy_constants.destruction_dive_permitted, for arrivals and descents.  Owner 2026-11-14
(verbatim): 「50F以降で破壊手段なしの探索は許可しない。敵への対処以前に手段が尽きた時点で帰還
させる。」  With the means gone on such a floor (rate below 80%, charges spent) the floor is a
gap too (``gap_here``) and the return starts at once (``means_spent_recall_key``, above the
emergency ladder); a charged list after the inn permits 50F+ again.

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
   confusion halves the skill, stun may refuse it (check_stun, the stun's
   get_item_chance_penalty: 5% at a hard stun, 10% unconscious), a Berserker always
   fails, a failure spends the turn and keeps the charge.  The absorbed power
   (cmd-magiceat.cpp) refuses a confused player; a stun adds its
   get_magic_chance_penalty to the failure (:485, 10-50%); a failure spends the turn
   and keeps the charge.  Neither refuses hallucination (only cmd_limit_image's two
   class powers do; owner 2026-11-13 「幻覚でも使う」).

Gates (``key``, asked by each rung before its read): the character is clear-headed (blindness
allowed, owner 2026-11-08 「盲目でも使う」; a stun allowed, owner 2026-11-13, judged by the
stun-adjusted success); a means is reliable (``me_capability.RELIABLE_MIN_SUCCESS``, the
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
from types import SimpleNamespace

from hengbot import (
    area_mapping, disenchant_avoid, escape_count, hunt_target, immobile_threat_memory, left_cells, me_capability, me_powers, monster_memory,
    pingpong_guard, summoner_wait,
)
from hengbot import cross_rules
from hengbot import me_absorbed_substitutes as substitutes
from hengbot.item_reservation import reserved_item_command
from hengbot import destruction_means
from hengbot.destruction_means import (  # noqa: F401  -- the readers' names stay here
    HOME_STAFF, POWER, STAFF, STAFF_LEVEL, reliable_skill, staff_home_items, staff_success,
)
from hengbot.model import Position, game_distance
from hengbot.town_hold import LOOT_OWNERS
from hengbot.policy_constants import (
    DESTRUCTION_GATE_DEPTH, DESTRUCTION_GATE_LABEL, EMERGENCY_RETURN_COUNT,
    PLAYER_CLASS_BERSERKER, ExplorationPathOutcome,
)


REASON = "emergency:destruction"
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
# The returns the escape count latches: the ladder's and the second escape's (emergency-repeat).
COUNT_RETURN_TRIGGERS = LADDER_RETURN_TRIGGERS | {"emergency-repeat"}
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
# The memories of monsters and holds a flash forgets: monster_memory.DESTRUCTION_FORGETS (the one
# registry, owner 2026-11-15 Q6).


@dataclass
class Memory:
    pending: tuple | None = None   # (floor, turn, position) of the last use
    # The hostiles known on the board of the last use: ((index, race, y, x, name), ...).  A class
    # default: restored checkpoints predate it.
    pending_monsters: tuple = ()
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
    """The reliable power (me_capability's counting row) with a charge here; stunned, the
    displayed failure with the stun's penalty (me_powers.stunned_success) is reliable too."""
    if destruction_means.Means(policy, snapshot).absorbed_charges <= 0:
        return None
    if snapshot.player.stunned and (
            me_powers.stunned_success(policy, snapshot, POWER) or 0) < me_capability.RELIABLE_MIN_SUCCESS:
        return None
    return substitutes.cast_key(policy, snapshot, substitutes.POWERS[POWER], blind_ok=True,
                                hallucination_ok=True)


def absorbed_success(policy, snapshot, ident) -> int | None:
    """An absorbed power's success percent now: the displayed failure with the stun's
    penalty (me_powers.stunned_success), else the displayed success; None without a row."""
    success = me_powers.stunned_success(policy, snapshot, ident)
    if success is not None:
        return success
    row = me_capability.observed_row(policy, *ident)
    return None if row is None else int(row.get("success") or 0)


def _reliable_carried_staff(policy, snapshot):
    """A known charged staff carried, when the worn loadout makes it reliable (stun included)."""
    means = destruction_means.Means(policy, snapshot)
    return means.carried_charged_staff if means.staff_reliable else None


def _carried_key(policy, snapshot) -> str | None:
    staff = _reliable_carried_staff(policy, snapshot)
    return None if staff is None else reserved_item_command(policy, snapshot, "staff", staff)


def owns_charged_staff(policy, snapshot) -> bool:
    """A known staff with a charge, carried or (in town) in the Home, that the worn loadout
    makes reliable (destruction_means ``owns_staff``: the depth condition's staff part, owner
    2026-11-16 「深さの条件の定義に揃える」; a staff below 80% is no means).  The gear search
    reads the staff without its success (destruction_means ``Means.staff_owned``).

    A Home staff is counted in town only: the departure withdraws it (the Home-first take of
    ``_missing_destruction_uses``) once the intended depth is 50F+, or short of it once the worn
    loadout makes it reliable (``staff_carry_uses``), and the departure requirement then asks it
    carried.  A Home mutation drops the page knowledge until the next scan
    (policy_home._invalidate_home_observation) though the staves stay on the shelf; the staves of
    the last complete catalogue (``HOME_STAFF``, ``observe``) stand in then, so the optimizer's
    StaffGate does not come and go within a visit (n1-a life-525's 21:05 visit: 121 of its 155
    asks found no Home staff) and swap the gear back and forth."""
    return destruction_means.Means(policy, snapshot).owns_staff()


def staff_carry_uses(policy, snapshot) -> int:
    """The *Destruction* uses the departure carries short of the 50F gate.

    Owner 2026-11-15 (n1-a life-525 died on 49F with twelve staves in the Home and the gear
    that made them reliable left there), verbatim 「深さに関係なく持っていく」: once the worn
    loadout makes the staff reliable (the optimizer weighs that gear by its comparison,
    equipment_utility.destruction_means_bonus), a charged staff owned (carried, or in the
    Home in town) is carried at every depth, as many charges as the 50F row asks
    (``DESTRUCTION_USES_PER_STEP``) and no more than are owned, so the shortage is the
    Home-first take's and never a purchase.  0 for a Berserker (his staff always fails)."""
    return destruction_means.Means(policy, snapshot).carry_uses()


def holds_means(policy, snapshot) -> bool:
    """A staff or absorbed power at 80%+ with a charge; the character's status now
    does not matter and a scroll is no means (owner 2026-11-04).

    The staff's success is the worn loadout's (the board's device skill): owner
    2026-11-15 「装備で魔法道具使用能力を向上させて杖の成功率を上げることで先に進む
    ことができる」.  In town a Home staff counts too, so the gear that makes it
    reliable unlocks the 50F+ intent and the departure takes the staff."""
    return destruction_means.Means(policy, snapshot).depth_gate()


MEANS_SPENT_TRIGGER = "emergency-destruction-means-spent"
MEANS_SPENT_REASON = "return:recall"
# Owner 2026-11-16 「普通は破壊手段が尽きる=最後の破壊を使用する=周囲13マスに危険はないので安全に
# 帰還できる見込みである。そうでない場面が出たら記憶」: the decision record's field
# (``unsafe_report``, ``{"branch": UNSAFE_BRANCH, "causes": [...]}``) of a means-spent board that
# is not that safe one.  Record only: no decision reads it.
UNSAFE_BRANCH = "means-spent-unsafe"
UNSAFE_NOTE = "_means_spent_unsafe"   # (turn, causes) of this decision; cleared by ``observe``
UNSAFE_AWAKE_NEAR = "awake-near"         # an awake hostile within GUARANTEED_RADIUS
UNSAFE_INSTANT_DEATH = "instant-death"   # deep_teleport.allows: the teleport went first
UNSAFE_HEAL_FIRST = "heal-first"         # policy_combat._flee_sustain_key's heal went first


def _quest_floor(policy, snapshot) -> bool:
    """A fixed or random quest floor: its own rules (the plans, the random quest's give-up and
    exit lock) decide leaving it."""
    return snapshot.floor_key[2] != 0 or policy._on_random_quest_floor(snapshot)


def gap_here(policy, snapshot, missing) -> frozenset:
    """``missing`` of the floor the player stands on.  Owner 2026-11-14 「50F以降で破壊手段なし
    の探索は許可しない。」: the *Destruction* label is a gap on every 50F+ floor without the
    means, the floor where it was held and spent included (before, that floor was no gap:
    owner 2026-11-04's 「使える手段がある時だけ解く」 governed arrivals and descents only).
    A quest floor keeps the 11-04 reading (the floor where the means was held is no gap): its
    own rules decide leaving it (a random quest's exit lock refuses the Recall)."""
    memory = getattr(policy, MEMORY, None)
    if (_quest_floor(policy, snapshot) and memory is not None
            and memory.entitled_floor == snapshot.floor_key):
        return frozenset(missing) - {DESTRUCTION_GATE_LABEL}
    return frozenset(missing)


def means_spent(policy, snapshot) -> bool:
    """A 50F+ floor where the tiers act and *Destruction* touches, no quest floor (``gap_here``),
    without the means."""
    from hengbot import threat_tiers  # import cycle

    return (snapshot.dungeon_level >= DESTRUCTION_GATE_DEPTH
            and threat_tiers.acts_here(policy, snapshot)
            and _floor_destroyed(policy, snapshot)
            and not _quest_floor(policy, snapshot)
            and not holds_means(policy, snapshot))


def means_spent_recall_key(policy, snapshot) -> str | None:
    """Owner 2026-11-14 「敵への対処以前に手段が尽きた時点で帰還させる。」: on a ``means_spent``
    floor the town return starts (``MEANS_SPENT_TRIGGER``, a survival return: no loot sweep
    delays it) and Word of Recall is read before any enemy is answered, when this floor lets
    one be read (once_quest_recall.read_key: not while recalling, blind or confused, on a
    locked quest floor or without a scroll).  Without a read the return stays latched and its
    own rungs leave the floor; the rungs below answer the enemies meanwhile."""
    from hengbot import deep_teleport, once_quest_recall  # import cycle

    if not means_spent(policy, snapshot):
        return None
    if not policy._returning_to_town or policy._last_return_trigger != MEANS_SPENT_TRIGGER:
        if not policy._returning_to_town:
            policy._note_return_start(MEANS_SPENT_TRIGGER)
        policy._returning_to_town = True
        policy._last_return_trigger = MEANS_SPENT_TRIGGER
    here = snapshot.player.position
    if any(not monster.asleep and game_distance(here, monster.position) <= GUARANTEED_RADIUS
           for monster in policy._physical_hostiles(snapshot)):
        note_unsafe(policy, snapshot, UNSAFE_AWAKE_NEAR)
    # Owner 2026-11-16 「即死ならテレポートを先」: on the 50F+ 即死 board (deep_teleport.allows:
    # the line-of-fire p95 reaches the HP, owner 2026-11-14) the emergency ladder's Teleportation
    # comes first; the return stays latched and the Recall is read on the board after the landing.
    if deep_teleport.allows(policy, snapshot):
        note_unsafe(policy, snapshot, UNSAFE_INSTANT_DEATH)
        return None
    return once_quest_recall.read_key(policy, snapshot, MEANS_SPENT_REASON)


def note_unsafe(policy, snapshot, cause) -> None:
    """Remember ``cause`` for this decision's record (``UNSAFE_NOTE``)."""
    note = getattr(policy, UNSAFE_NOTE, None)
    causes = note[1] if note is not None and note[0] == snapshot.turn else ()
    if cause not in causes:
        setattr(policy, UNSAFE_NOTE, (snapshot.turn, causes + (cause,)))


def unsafe_report(policy) -> dict | None:
    """The decision record's field, on a means-spent board that is not safe."""
    note = getattr(policy, UNSAFE_NOTE, None)
    return None if note is None else {"branch": UNSAFE_BRANCH, "causes": list(note[1]),
                                      "turn": note[0]}


def means_spent_read_selected(policy) -> bool:
    """The decision's key is the Recall read of the return ``means_spent_recall_key`` latched
    (its reason under ``MEANS_SPENT_TRIGGER``).  Owner 2026-11-14 「敵への対処以前に手段が尽きた
    時点で帰還させる。」: the after-ladder filters do not put an answer to the enemies (the escape's
    Speed dose, policy_combat ``_flee_sustain_key``) in its place; owner 2026-11-16 「回復だけは
    帰還より先に」: that filter's heal alone still comes first.  n1-c life-216's 64F
    board with the charges emptied (tests/test_deep_means_spent_recall_first_1116_recorded.py)
    drank the absorbed Speed for two sleeping monsters instead."""
    return (policy.last_reason == MEANS_SPENT_REASON
            and policy._returning_to_town
            and policy._last_return_trigger == MEANS_SPENT_TRIGGER)


# -- the scene ------------------------------------------------------------------

def _clear_headed(player) -> bool:
    """Owner 2026-11-08 「盲目でも使う」: blindness does not stop the use (neither the
    staff nor the ``m`` command refuses it, above); confusion still does.  A stun does not
    either (owner 2026-11-13; n1-b life-377 died stunned without it): the game only adds
    its penalty, which ``_absorbed_key`` and destruction_means' ``staff_reliable`` count.  Nor hallucination
    (owner 2026-11-13 「幻覚でも使う」, no refusal of the game's): the board then redacts
    every monster's identity (bot-json-output.cpp make_visible_monster_json; model.py keeps
    the position and treats it as an awake hostile of unknown strength), and the same gates
    judge from what it still gives."""
    return not player.confused


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
    worst = reach_subject(policy, snapshot, hostiles, target)
    return worst is not None and game_distance(snapshot.player.position, worst.position) <= GUARANTEED_RADIUS


def reach_subject(policy, snapshot, hostiles, target):
    """The monster of ``hostiles`` whose place ``_threat_in_reach`` asks: the most dangerous
    from contact (``threat_prediction(contact=True)``), the nearer on a tie, the ``target``
    race (``_target_race``) left out; None with none.  The walk toward the use (deep_teleport)
    walks until this one is in the sure radius."""
    candidates = [m for m in hostiles if m.hostile and m.race_id != target]
    if not candidates:
        return None
    here = snapshot.player.position
    rows = policy.threat_prediction(snapshot, candidates, 1, contact=True)["monsters"]
    worst, _ = max(zip(candidates, rows), key=lambda pair: (
        pair[1].get("operational_contribution", 0), -game_distance(here, pair[0].position)))
    return worst


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
    the cornered flee of a leave the tiers decided.  On the 即死 board the ladder reads a
    Teleportation scroll first (owner 2026-11-08, policy_combat ``scroll_first``); with none to
    read (none carried, or blind) it leaves the engagement here too (owner 2026-11-13).  The
    summoner hold's teleport, the immobile summoner's and the item-destroying breeders' floor
    exits ask it before their scrolls (owner 2026-11-13)."""
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
    memory = _memory(policy)
    memory.pending = (snapshot.floor_key, snapshot.turn, snapshot.player.position)
    memory.pending_monsters = tuple(
        (monster.index, monster.race_id, monster.position.y, monster.position.x, monster.name)
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters) if monster.hostile)
    return used


def success(policy, snapshot) -> float | None:
    """The success percent of the means ``key`` would use (the absorbed power first), else
    None; the scene's gates are not asked."""
    if _absorbed_key(policy, snapshot) is not None:
        return absorbed_success(policy, snapshot, POWER)
    if _carried_key(policy, snapshot) is not None:
        return staff_success(snapshot.player, STAFF_LEVEL)
    return None


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
    setattr(policy, UNSAFE_NOTE, None)
    if snapshot.in_town and getattr(policy, "_home_knowledge_current", False):
        setattr(policy, HOME_STAFF, destruction_means.charged_staves(getattr(policy, "_home_knowledge_items", ())))
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
        escape_count.destroyed(policy, snapshot, position, GUARANTEED_RADIUS)
        _end_emergency(policy, snapshot)
        forget_circle(policy, position)
        keys, names = _deleted(policy, snapshot, memory, position)
        monster_memory.forget_destroyed(policy, snapshot, position, GUARANTEED_RADIUS,
                                        lambda monster: _survives(policy, snapshot, monster),
                                        keys, names)
        area_mapping.note_destruction(policy, snapshot, position, WORST_RADIUS, GUARANTEED_RADIUS)
        # Record only (cross_rules): what the flash forgot, and the memories it does not.
        cross_rules.destruction_flash(policy, ("monster_memory.DESTRUCTION_FORGETS",))
    elif snapshot.turn != turn:
        memory.pending = None
        memory.fallback = floor


def _deleted(policy, snapshot, memory, centre) -> tuple[frozenset, frozenset]:
    """The hostiles known on the board of the use that the circle deleted: within the radius it
    always destroys, not spared (``_survives``: the quest's target, a QUESTOR), and not shown
    on the flash board.  (keys (index, race), names)."""
    shown = {monster.index for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)}
    keys, names = set(), set()
    for index, race, y, x, name in getattr(memory, "pending_monsters", ()):
        known = SimpleNamespace(index=index, race_id=race, position=Position(y, x), name=name)
        if (game_distance(centre, known.position) <= GUARANTEED_RADIUS and index not in shown
                and not _survives(policy, snapshot, known)):
            keys.add((index, race))
            names.add(name)
    return frozenset(keys), frozenset(names)


def _survives(policy, snapshot, monster) -> bool:
    """A monster the circle does not delete: a QUESTOR, healed and teleported away
    (spell-kind/spells-floor.cpp destroy_area): a race whose definition carries the flag, or the
    active quest's target (a random quest's bounty carries it from the start,
    birth/game-play-initializer.cpp:148, dungeon/dungeon-processor.cpp:110).  Uniques are
    deleted like any other."""
    flags = getattr(policy._monrace_knowledge.get(monster.race_id), "flags", ())
    return "QUESTOR" in flags or monster.race_id == _target_race(policy, snapshot)


def _end_emergency(policy, snapshot) -> None:
    """「破壊の回数だけでは帰還しない」: drop the ladder's latch for this escape.

    Owner 2026-11-11 「逃げた原因を後から*破壊*で排除した場合もリセット。」: the flash first
    drops the escapes whose causes it destroyed (escape_count.destroyed); a return the count
    latched -- the ladder's for this escape, or emergency-repeat for the second escape --
    ends when the count is below the return count again.  A Word of Recall already active
    keeps its return.
    """
    policy._emergency_escape_pending = False
    policy._emergency_return_active = False
    if (policy._last_return_trigger in COUNT_RETURN_TRIGGERS
            and policy._dive_emergencies < EMERGENCY_RETURN_COUNT
            and not snapshot.player.recalling):
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
