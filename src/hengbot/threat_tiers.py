"""Threat tiers, plan step 1 (docs/threat-tiers-design.md): observe only.

Owner 2026-11-07: 「敵の脅威度の判断をもう少し作り込む。『即死の危険がある』『物資を全て使っても
倒しきれない』『物資を使えば勝てる』『物資を使わなくても勝てる』この段階に分ける。」  The answers
(design section 0, 7 and 7.1) are implemented here as a pure classifier, ``assess``; its reader is
the decision-row telemetry (cli ``_capture_decision_facts``, next to ``threat_prediction``), which
runs inside the observer scope.  Plan step 4 acts on 3.1 alone (``instant_death``, the same code
``assess`` runs): ``instant_death_key`` is the quest plans' 即死 rung (answer 11).

What ``assess`` computes (the design's section numbers):

- 3.1 即死: the one-player-action operational (per-monster p95) projection of the engagement, with
  each monster at ``speed + 10*fast - 10*slow`` (a hasted monster after a SHRIEK counts its haste;
  ``threat_prediction`` alone reads the race speed), plus the observed unseen loss (the gating of
  ``_emergency_item``'s ``observed_loss_lethal``, x1 instead of x3), at least the current HP; also
  an awake unresisted paralyser in contact (``paralyzer_contact``) and the hallucination rule
  (``hidden_threat_lethal``), which the HP model cannot see.
- 3.2-3.4 T1/T2/T3: T3 when the free attacks clear the engagement before the projection over the
  turns to clear reaches the HP (today's ``_engagement_is_winnable`` criterion, no reserve); else
  T2 when a supply plan wins, the owner's order taken as prefixes (D7: Speed, good ammo,
  wand/staff charges, attack scrolls, resistance, healing; the shortest winning prefix), against
  the reserve max(10% max HP, the next-action p95); else T1 (not even every supply wins).
- 4.1-4.4 the four flags, per monster; the engagement's ``cannot_escape``.
- 3.4 the selection (answer 4): the active quest's target or the hunted guardian, a monster the
  player cannot escape (and cannot restore an escape from), the reward races (answer 5).

Fair play: the snapshot (visible and detected monsters, health-band HP estimate, the player's own
status, abilities and pack) plus the static race data (``policy._monrace_knowledge``, from
lib/edit/MonraceDefinitions.jsonc).  ``assess`` writes nothing; the one memory is the decided
side of the engagement (``decided``, owner 2026-11-08 「境に余裕を持たせる」).

The code is split by concern (maintainability review 2026-11-09, step 4); this module is the
façade that re-exports every name, so callers, tests and their ``patch.object(threat_tiers, ...)``
are unchanged.  Functions that call a name tests patch here (``tiered``, ``assess``, ``acts_here``,
``instant_death``, ...) stay in this module, so the patch still reaches them:

- ``threat_projection``: the results, the engagement, the attacks, ``Projection``, ``_plan``,
  ``_tier``.
- here: ``assess``, the selection (3.4) and acting on the tiers (steps 6-8).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hengbot import (
    attack_expectation,
    destruction_use,
    disenchant_avoid,
    hunt_target,
    me_absorbed_substitutes,
    me_capability,
    me_device_attacks,
    paralyzer_contact,
    quest_no_teleport,
    retreat_veto_life,
    return_yield,
    speed_dose,
    survival_preemption,  # noqa: F401 -- re-exported (tests patch threat_tiers.survival_preemption)
)
from hengbot.item_reservation import decision_memo, reserved_item_command
from hengbot.model import (
    SV_POTION_HEALING,
    SV_POTION_LIFE,
    SV_POTION_RESIST_COLD,
    SV_POTION_RESISTANCE,
    SV_POTION_STAR_HEALING,
    SV_STAFF_TELEPORTATION,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_WAND,
)
from hengbot.policy_constants import (
    MONSTER_SPELL_MAX_RANGE,
    OPPOSITION_ABILITY,
)
# The façade (maintainability review 2026-11-09, step 4): every name of the split modules is
# re-exported here, so ``threat_tiers.X`` keeps working for callers, tests and their patches.
from hengbot.threat_projection import (  # noqa: F401
    T1,
    T2,
    T3,
    HEAL_AMOUNTS,
    SV_POTION_RESIST_HEAT,
    SPEED_BONUS,
    SPEED_DOSE_TURNS,
    RESERVE_HP_RATIO,
    SCROLL_BALL_RADIUS,
    PROJECTION_COST_BUDGET,
    AttackScroll,
    ATTACK_SCROLLS,
    MonsterAssessment,
    SupplyPlan,
    Assessment,
    adjusted_speed,
    _with_adjusted_speed,
    engagement,
    unseen_correction,
    _ranged_ready,
    _launcher_stacks,
    _race_flags,
    _missile_ready,
    _free_devices,
    _charge_supplies,
    free_damage,
    _scroll_reads,
    scroll_damage_at,
    _self_damage,
    PLAN_ORDER,
    _attack_schedule,
    _hasted,
    _resistance_after,
    CostExceeded,
    Projection,
    _plan,
    _supplies_held,
    _path_memo,
    _tier,
)


SV_SCROLL_TELEPORT_LEVEL = 10
# The reason suffix of a carried Staff of Teleportation used blind (blind_teleport_key).
STAFF_REASON_SUFFIX = "-staff"

# monster-death.cpp:226-251 decide_drop_numbers; the owner's counts (OQ-8).
DROP_COUNTS = {"DROP_60": 0.6, "DROP_90": 0.9, "DROP_1D2": 1.5, "DROP_2D2": 3.0,
               "DROP_3D2": 4.5, "DROP_4D2": 6.0}
MANY_DROPS = 3.0
REWARD_EXP_SHARE = 0.10             # answer 5: 10% of the exp still needed
REWARD_EXP_KILL_FACTOR = 1.5        # OQ-11: 1.5 x level x mexp / (max_plv + 2)
SURFACE_EXP_DIVISOR = 5             # monster-damage.cpp:155

# 4.1: what each damage needs to be prevented (snapshot abilities).
STAT_DRAIN_BLOWS = {
    "LOSE_STR": ("sustain_str",), "LOSE_INT": ("sustain_int",), "LOSE_WIS": ("sustain_wis",),
    "LOSE_DEX": ("sustain_dex",), "LOSE_CON": ("sustain_con",), "LOSE_CHR": ("sustain_chr",),
    "LOSE_ALL": ("sustain_str", "sustain_int", "sustain_wis", "sustain_dex", "sustain_con",
                 "sustain_chr"),
}
# player-damage.cpp: acid drains CHR, elec DEX, fire and cold STR (1 in 16 per unresisted hit).
ELEMENTS = {
    "acid": ("ACID", frozenset({"BR_ACID", "BA_ACID", "BO_ACID"}), "sustain_chr"),
    "elec": ("ELEC", frozenset({"BR_ELEC", "BA_ELEC", "BO_ELEC"}), "sustain_dex"),
    "fire": ("FIRE", frozenset({"BR_FIRE", "BA_FIRE", "BO_FIRE"}), "sustain_str"),
    "cold": ("COLD", frozenset({"BR_COLD", "BA_COLD", "BO_COLD", "BO_ICEE"}), "sustain_str"),
}


# ---------------------------------------------------------------- flags

def irreversible_kinds(policy, snapshot, monster) -> tuple:
    """4.1: the irreversible damage ``monster``'s race can deal the unprotected player.

    Exp drain never counts (D5); disenchant is listed (its action stays with 11-05)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None:
        return ()
    player = snapshot.player
    abilities = set(player.abilities)
    sources = player.ability_sources
    effects = {blow.effect for blow in knowledge.blows}
    spells = set(knowledge.abilities)
    kinds = []
    for effect, sustains in STAT_DRAIN_BLOWS.items():
        if effect in effects and not set(sustains) <= abilities:
            kinds.append("stat-drain")
            break
    if "DISEASE" in effects and "sustain_con" not in abilities:
        kinds.append("stat-drain")
    if ("TIME" in effects or "BR_TIME" in spells) and "resist_time" not in abilities:
        kinds.append("stat-drain")
    for name, (blow, element_spells, sustain) in ELEMENTS.items():
        if blow not in effects and not element_spells & spells:
            continue
        immune = name in player.immunities
        resist = f"resist_{name}" in abilities
        if not (immune or resist or sustain in abilities):
            kinds.append("stat-drain")
        # Item destruction stops only with resistance AND opposition (player-damage.cpp).
        source = sources.get(f"resist_{name}", frozenset()) if sources else frozenset()
        lasting = bool(source & {"equipment", "permanent"}) or (resist and not source)
        opposed = "temporary" in source or OPPOSITION_ABILITY in abilities
        if not (immune or (lasting and opposed)):
            kinds.append("item-destruction")
    if effects & {"EAT_ITEM", "UN_POWER"}:
        kinds.append("item-destruction")
    if ("UN_BONUS" in effects or "BR_DISE" in spells) and "resist_disen" not in abilities:
        kinds.append("disenchant")
    return tuple(dict.fromkeys(kinds))


def worsens_kinds(policy, monster) -> tuple:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    kinds = []
    if monster.can_summon:
        kinds.append("summon")
    if monster.can_multiply:
        kinds.append("multiply")
    if knowledge is not None and "SHRIEK" in knowledge.abilities:
        kinds.append("shriek")
    return tuple(kinds)


def _stair_distance(snapshot) -> int | None:
    here = snapshot.player.position
    distances = [here.distance_to(grid.position) for grid in snapshot.grids.values()
                 if grid.has_up_stairs or grid.has_down_stairs]
    return min(distances, default=None)


def escape_means(policy, snapshot, hostiles) -> tuple:
    """4.2: the escape means usable now; empty is 逃げられない."""
    player = snapshot.player
    means = []
    readable = not (player.blind or player.confused) and policy._can_read_scrolls(snapshot)
    teleport_blocked = policy._teleport_blocked_by_equipment(snapshot)
    forbidden = quest_no_teleport.forbids(policy, snapshot)
    scrolls = {item.sval for item in snapshot.inventory
               if item.tval == TVAL_SCROLL and item.aware and item.count > 0}
    if readable and not teleport_blocked and not forbidden:
        if scrolls & {8, 9}:
            means.append("teleport-scroll")
        if SV_SCROLL_TELEPORT_LEVEL in scrolls:
            means.append("teleport-level")
    if readable and any(item.is_recall_scroll for item in snapshot.inventory):
        means.append("recall")
    if not teleport_blocked and not forbidden:
        if not player.confused and any(
                item.tval == TVAL_STAFF and item.sval == SV_STAFF_TELEPORTATION
                and item.aware and item.charges > 0 for item in snapshot.inventory):
            means.append("teleport-staff")
        if (not player.confused and not quest_no_teleport.forbids_absorbed(policy, snapshot)
                and me_capability.has(policy, snapshot, "staff", SV_STAFF_TELEPORTATION)
                and me_capability.charges(policy, snapshot, "staff", SV_STAFF_TELEPORTATION) > 0):
            means.append("absorbed-teleport")
    if destruction_use.holds_means(policy, snapshot) and destruction_use._scene_holds(
            policy, snapshot):
        means.append("destruction")
    stair = _stair_distance(snapshot)
    chasers = [monster for monster in hostiles
               if not monster.asleep and policy._monster_can_approach(snapshot, monster)
               and monster.speed > player.speed]
    if not chasers or (stair is not None
                       and all(stair < monster.distance for monster in chasers)):
        means.append("walk")
    return tuple(means)


def blind_teleport_key(policy, snapshot, reason: str) -> str | None:
    """Blind and not confused: the absorbed Teleportation, else a carried Staff of
    Teleportation, the means ``escape_means`` counts; None otherwise.

    The scroll a rung reads cannot be read blind (cmd-read.cpp:37 cmd_limit_blind), but the
    ``m`` command refuses only confusion (cmd-magiceat.cpp:463 cmd_limit_confused) and the
    staff refuses neither (cmd-usestaff.cpp do_cmd_use_staff, use-execution.cpp
    ObjectUseEntity::execute: confusion halves the skill, stun may refuse it), and
    SV_STAFF_TELEPORTATION is teleport_player 100 (cmd-usestaff.cpp:101-105).  n1-c life-171
    (2026-11-08 20:08, 城65階): blind at HP 259/993 in the one-shot tier beside ハスター with
    the absorbed staff at 24/24, 98%, the ladder found no readable escape and fired a rocket.
    The rungs that read a relocation scroll ask this in the scroll's place when blind: design
    3.1 即死→逃げる, owner 2026-11-06 「低HPで召喚・引き寄せ・速い敵が見えたら…テレポート/帰還」,
    owner 2026-11-08 「その敵の感知範囲内なら早急に離脱する」.  ``last_reason`` is ``reason``
    (with the cast suffix for the absorbed power, which admits the device key)."""
    means = blind_teleport_means(policy, snapshot)
    if means is None:
        return None
    if means == ABSORBED:
        policy.last_reason = reason + me_absorbed_substitutes.CAST_SUFFIX
        return me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION].key
    key = reserved_item_command(policy, snapshot, "staff", means)
    if key is not None:
        policy.last_reason = reason + STAFF_REASON_SUFFIX
    return key


ABSORBED = "absorbed"


def blind_teleport_means(policy, snapshot):
    """``blind_teleport_key``'s means: ``ABSORBED``, the carried staff, else None."""
    player = snapshot.player
    if (not player.blind or player.confused or snapshot.store is not None
            or policy._teleport_blocked_by_equipment(snapshot)
            or quest_no_teleport.forbids(policy, snapshot)):
        return None
    power = me_absorbed_substitutes.TELEPORTATION
    # The menu walk of the blind cast is the one status_cure.absorbed_cure_key uses.
    if (me_absorbed_substitutes.blind_castable(snapshot)
            and not quest_no_teleport.forbids_absorbed(policy, snapshot)
            and me_capability.has(policy, snapshot, *power)
            and me_capability.charges(policy, snapshot, *power) > 0):
        return ABSORBED
    return next((item for item in snapshot.inventory
                 if item.tval == TVAL_STAFF and item.sval == SV_STAFF_TELEPORTATION
                 and item.aware and item.charges > 0), None)


def escape_restorable(policy, snapshot) -> bool:
    """4.2 restore: a cure for blindness / confusion, or a removable anti-teleport item."""
    player = snapshot.player
    if (player.blind or player.confused) and policy._find_status_cure_potion(snapshot) is not None:
        return True
    return any(policy._blocks_teleport(item) and not item.is_cursed
               for item in snapshot.equipment)


def need_not_fight(policy, snapshot, monster, row, protected: bool) -> str | None:
    """4.3: ``fearful``, or a monster that cannot reach the player at all.

    The 3-board distance history ("not approaching") is a later step's new policy attribute."""
    if protected:
        return None
    if monster.fearful and not monster.asleep:
        return "fearful"
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if policy._monster_can_approach(snapshot, monster):
        return None
    if row is None or row.get("operational_ranged_prediction", 0) > 0:
        return None
    if row.get("can_teleport_player_to"):
        return None
    if knowledge is not None and "SHRIEK" in knowledge.abilities and policy._has_line_of_fire(
            snapshot, monster.position, snapshot.player.position) and policy._monster_cast_distance(
            monster.position, snapshot.player.position) <= MONSTER_SPELL_MAX_RANGE:
        return None
    if monster.can_summon and policy._summoner_may_summon_next_turn(snapshot, monster):
        return None
    return "cannot-reach"


# ---------------------------------------------------------------- selection

def _quest_races(policy, snapshot) -> set:
    races = set()
    quest_id = policy._active_kill_quest_id(snapshot)
    quest = snapshot.quests.get(quest_id) if quest_id is not None else None
    if quest is not None and (race := policy._quest_target_race_id(quest)) is not None and race > 0:
        races.add(race)
    profile = policy.approved_quest_strategy(snapshot.floor_key[2])
    if profile is not None:
        races.update(int(race) for race in profile.engagement_plan.get(
            "immediate_priority_targets", ()))
    return races


def reward_reasons(policy, snapshot, monster) -> tuple:
    """Answer 5: DROP_GOOD / DROP_GREAT, exp >= 10% of the exp still needed, >= 3 drops."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None or monster.can_multiply or "MULTIPLY" in knowledge.flags:
        return ()
    reasons = [flag.lower() for flag in ("DROP_GOOD", "DROP_GREAT") if flag in knowledge.flags]
    player = snapshot.player
    to_advance = player.exp_to_advance
    if to_advance is not None and to_advance > player.exp:
        max_level = player.max_level if player.max_level is not None else player.level
        gain = (REWARD_EXP_KILL_FACTOR * knowledge.level * knowledge.experience
                / (max_level + 2))
        if snapshot.dungeon_level <= 0:
            gain /= SURFACE_EXP_DIVISOR
        if gain >= REWARD_EXP_SHARE * (to_advance - player.exp):
            reasons.append("exp")
    if sum(DROP_COUNTS.get(flag, 0.0) for flag in knowledge.flags) >= MANY_DROPS:
        reasons.append("many-drops")
    return tuple(reasons)


# ---------------------------------------------------------------- assess

@dataclass(frozen=True)
class InstantDeath:
    """3.1 即死 on one board: why it holds, and the next-action damage it read."""
    reasons: tuple = ()
    next_action_p95: int = 0
    unseen_correction: int = 0

    @property
    def holds(self) -> bool:
        return bool(self.reasons)

    @property
    def next_action(self) -> bool:
        """The 1-turn p95 test (answer 2 「次の1手の95%で判定」), the one the ladders act on."""
        return NEXT_ACTION_P95 in self.reasons


NEXT_ACTION_P95 = "next-action-p95"


def _instant_death(policy, snapshot, hostiles, melee_slots=None,
                   contact=False) -> tuple[InstantDeath, dict]:
    """3.1 on hostiles already at their adjusted speed; also the 1-turn prediction it read."""
    player = snapshot.player
    hp = player.hp
    one_turn = policy.threat_prediction(snapshot, hostiles, 1, melee_slots=melee_slots,
                                        contact=contact)
    next_action_p95 = one_turn["operational_total"]
    correction = unseen_correction(policy, snapshot, hostiles)
    reasons = []
    if next_action_p95 + correction >= hp:
        reasons.append(NEXT_ACTION_P95)
    if any(not monster.asleep and paralyzer_contact.in_contact(policy, snapshot, monster)
           for monster in policy._paralyzing_monsters(snapshot, hostiles)):
        reasons.append("paralyzer-contact")
    if (player.hallucinated and hp < policy._low_hp_walk_threshold(player.max_hp)
            and return_yield.awake_hostile_in_view(policy, snapshot)):
        reasons.append("hallucination")
    return InstantDeath(tuple(reasons), next_action_p95, correction), one_turn


def instant_death(policy, snapshot, hostiles=None) -> InstantDeath:
    """3.1 alone, the part of ``assess`` that is never past the cost cap (one action ahead)."""
    if hostiles is None:
        hostiles = engagement(policy, snapshot)
    hostiles = [_with_adjusted_speed(monster) for monster in hostiles]
    if not hostiles:
        return InstantDeath()
    return _instant_death(policy, snapshot, hostiles)[0]


def instant_death_key(policy, snapshot, plan_escape=None) -> str | None:
    """A quest plan's 即死 rung (answer 11 「作戦が先・即死だけ例外」, OQ-2).

    Inside a plan (dungeon_ladder.FLOOR_PLANS) the plan's own order goes first; the one label
    that pre-empts it is 即死 (3.1): the next player action's p95 damage, each monster at its
    adjusted speed, plus the observed unseen loss, reaches the HP; or an awake unresisted
    paralyser in contact; or the hallucination rule.

    The answer (owner 2026-11-07 「即死の危険の時は、その作戦が決めている逃げ方（Q25 なら作戦の HP
    の線のテレポートなど）を先に使う。作戦に逃げ方が無ければ緊急の逃げ方。」): ``plan_escape``, the
    plan's own escape rung asked without its HP line, first; when the plan has none left, the
    escape ``_emergency_item`` runs when ``lethal`` holds (stairs, the blindness/confusion cure
    that owes the escape, the low-HP heal-first rule, *Destruction*, Teleportation, Recall, the
    walk to the stairs, the last stand).
    """
    hostiles = engagement(policy, snapshot)
    if not instant_death(policy, snapshot, hostiles).holds:
        return None
    if plan_escape is not None and (answer := plan_escape()) is not None:
        return answer
    return policy._emergency_item(snapshot, hostiles, instant_death=True)


def assess(policy, snapshot, hostiles=None, *, melee_slots=None, contact=False) -> Assessment:
    """Classify the engagement on ``snapshot`` (design 3 and 4); pure.

    ``melee_slots`` counts the melee slots elsewhere than at the player's cell, as
    ``threat_prediction`` does (the choke's origin, inventory 2.7).  ``contact``: every hostile
    judged as already beside the player (``threat_prediction(contact=True)``, as the detected-threat
    tiers judge a far monster "from contact")."""
    memoised = _path_memo(policy)
    if memoised is not None:
        policy._monster_path_distance = memoised
    try:
        return _assess(policy, snapshot, hostiles, melee_slots, contact)
    finally:
        if memoised is not None:
            del policy._monster_path_distance


def _assess(policy, snapshot, hostiles, melee_slots=None, contact=False) -> Assessment:
    if hostiles is None:
        hostiles = engagement(policy, snapshot)
    hostiles = [_with_adjusted_speed(monster) for monster in hostiles]
    player = snapshot.player
    result = Assessment()
    if not hostiles:
        return result
    hp, max_hp = player.hp, max(1, player.max_hp)

    # 3.1 即死
    death, one_turn = _instant_death(policy, snapshot, hostiles, melee_slots, contact)
    result.next_action_p95 = death.next_action_p95
    result.unseen_correction = death.unseen_correction
    result.instant_death = death.holds
    result.instant_death_reasons = death.reasons

    # 3.2-3.4 the tier
    # The budget read here, at call time: a patched threat_tiers.PROJECTION_COST_BUDGET applies.
    projection = Projection(policy, snapshot, hostiles, one_turn, melee_slots, contact,
                            budget=PROJECTION_COST_BUDGET)
    result.free_damage = {monster.index: free_damage(policy, snapshot, monster)
                          for monster in hostiles}

    try:
        _tier(policy, snapshot, projection, result, hp, max_hp)
    except CostExceeded:
        result.tier, result.supply_plan, result.skipped = None, None, "cost"

    # 4.2 逃げられるか
    result.escape_means = escape_means(policy, snapshot, hostiles)
    result.cannot_escape = not result.escape_means
    result.escape_restorable = result.cannot_escape and escape_restorable(policy, snapshot)

    # per monster: flags and the selection
    quest_races = _quest_races(policy, snapshot)
    hunted = hunt_target.target_race(policy, snapshot)
    rows = {row_monster.index: row for row_monster, row in zip(
        hostiles, policy.threat_prediction(snapshot, hostiles, 3, melee_slots=melee_slots,
                                           contact=contact)["monsters"])}
    for monster in hostiles:
        entry = MonsterAssessment(index=monster.index, race_id=monster.race_id,
                                  name=monster.name, speed=monster.speed,
                                  free_damage=result.free_damage[monster.index])
        entry.irreversible = irreversible_kinds(policy, snapshot, monster)
        entry.worsens_with_time = worsens_kinds(policy, monster)
        selected = []
        if monster.race_id in quest_races:
            selected.append("quest-target")
        if hunted is not None and monster.race_id == hunted:
            selected.append("hunted-guardian")
        if result.cannot_escape and not result.escape_restorable:
            selected.append("cannot-escape")
        entry.reward = reward_reasons(policy, snapshot, monster)
        if entry.reward:
            selected.append("reward")
        entry.selected = tuple(selected)
        entry.need_not_fight = need_not_fight(
            policy, snapshot, monster, rows.get(monster.index),
            protected=bool(monster.race_id in quest_races
                           or (hunted is not None and monster.race_id == hunted)))
        result.per_monster[monster.index] = entry
    return result


# ---------------------------------------------------------------- acting on the tiers (steps 6-8)

def acts_here(policy, snapshot) -> bool:
    """Where the tiers act: a dungeon floor of the shared ladder.

    Not in town, a store, the arena or the wilderness (outside the design, as ``facts``), and not
    on a floor an approved quest strategy runs: inside a quest plan the plan's action goes first and
    only 即死 pre-empts it (answer 11, 2.5), so there every judgement keeps today's meaning (Q2's
    ``_q2_encounter_key`` reads ``_should_flee`` as today, inventory 2.7)."""
    return (snapshot.dungeon_level > 0 and not snapshot.in_town and snapshot.store is None
            and not snapshot.inside_arena
            and policy.approved_quest_strategy(snapshot.floor_key[2]) is None)


def tiered(policy, snapshot, hostiles, melee_slots=None, contact=False) -> Assessment:
    """``assess`` memoised for the decision (one assessment per hostile set and slot count),
    with the decided side held (``decided``) where the reading is the engagement's own."""
    key = (tuple(monster.index for monster in hostiles), melee_slots, contact)
    return decision_memo(policy, "threat_tiers.assess", snapshot, key,
                         lambda: _held_reading(policy, snapshot, hostiles, melee_slots, contact))


def _held_reading(policy, snapshot, hostiles, melee_slots, contact) -> Assessment:
    result = assess(policy, snapshot, hostiles, melee_slots=melee_slots, contact=contact)
    if melee_slots is None and not contact and engagement_reading(policy, snapshot, hostiles):
        return decided(policy, snapshot, hostiles, result)
    return result


def leave_decided_here(policy, snapshot) -> bool:
    """Where the tiers decide leaving: ``acts_here``, and not a floor that leaving fails the
    quest (a fixed quest, or a taken kill quest whose exit is locked,
    ``_floor_navigation_exit_locked``): there the quest's own rules decide (design 3.2 「On a
    quest floor where leaving fails the quest the plan decides」; the random quest's give-up)."""
    return acts_here(policy, snapshot) and not policy._floor_navigation_exit_locked(snapshot)


def leave_due(policy, snapshot, hostiles, melee_slots=None) -> bool | None:
    """Plan step 6 (answer 6, 3.2, 3.4): whether the tiers say leave this engagement.

    True: T1 (「物資を全て使っても倒しきれない」), or T2 with no selected target (answer 4: only the
    quest target, the hunted guardian, a monster the player cannot escape and the reward races
    are fought with supplies).  False: T2 with a selected target, which is not left.  None: the
    tiers do not decide here (T3, the tier past the cost cap, ``leave_decided_here`` false), and
    the caller keeps today's judgement."""
    if not hostiles or not leave_decided_here(policy, snapshot):
        return None
    if any(disenchant_avoid.exposes_gear(policy, snapshot, monster) for monster in hostiles):
        # OQ-3 「全部 11-05 のとおり」: an engagement with an unresisted disenchanter is the 11-05
        # rule's (it keeps away, and fights one striking from beside the player).
        return None
    result = tiered(policy, snapshot, hostiles, melee_slots)
    if result.tier == T1:
        return True
    if result.tier == T2:
        return not result.selected
    return None


def walk_leaves(policy, snapshot, hostiles) -> bool:
    """Design 3.2's leave: 「walk while the monster is not faster and no ranged contact; else
    stairs / *Destruction* / Teleport / Recall in today's order」.  False when an awake hostile
    that can come to the player is faster (``speed + 10*fast - 10*slow`` against the player's
    speed) or one deals ranged damage before the player's next action."""
    speed = snapshot.player.speed
    awake = [monster for monster in hostiles if not monster.asleep]
    if any(adjusted_speed(monster) > speed and policy._monster_can_approach(snapshot, monster)
           for monster in awake):
        return False
    rows = policy.threat_prediction(
        snapshot, [_with_adjusted_speed(monster) for monster in awake], 1)["monsters"] if awake else []
    return not any(row.get("operational_ranged_prediction", 0) > 0 for row in rows)


SENSED_LEAVE_PREFIX = "sensed-t1:"


def sensing_distance(snapshot, monster) -> int:
    """The game's ``cdis`` (monster-update.cpp:193-204): max(dy, dx) + min(dy, dx) / 2, at least 1."""
    here, there = snapshot.player.position, monster.position
    dy, dx = abs(here.y - there.y), abs(here.x - there.x)
    return max(1, max(dy, dx) + min(dy, dx) // 2)


def inside_sensing(policy, snapshot, monster) -> bool:
    """The player stands inside the monster's sensing radius (``vision``, monrace.aaf): there it
    acts toward the player whatever the line of sight (monster-processor.cpp:708-710)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and sensing_distance(snapshot, monster) <= knowledge.vision


def cannot_win(assessment, hp: int) -> bool:
    """T1, or a tier the projection's cost cap left undecided (``skipped`` "cost") whose
    no-supply incoming damage is known to reach the HP: its lower bound is at least ``hp``
    (``free_incoming_bounds``), so T3 fails.  Owner 2026-11-08 (question 1 of the n1-c
    life-171 report, verbatim 「勝てないと分かれば離脱」): treated exactly as T1.  皇帝
    『レイザーク』 on 城65階 read None with bounds (1345, 19270) against HP 993."""
    if assessment.tier == T1:
        return True
    bounds = assessment.free_incoming_bounds
    return (assessment.tier is None and assessment.skipped == "cost"
            and bounds is not None and bounds[0] >= hp)


def sensed_t1_leave_key(policy, snapshot) -> str | None:
    """Owner 2026-11-08 (question 「感知で、起きている強い敵（倒しきれない段階の敵）が見えている時に
    休みますか？」, answer 「その敵の感知範囲内なら早急に離脱する」): an awake hostile, in view or
    detected, that is T1 on its own, with the player inside its sensing radius: leave now by step
    6's leave, never rest there.  The order is design 3.2's for a faster monster or one reaching at
    range: stairs underfoot, *Destruction*, a relocation scroll, Word of Recall; a walk only while
    no awake hostile is faster and none reaches at range.  Outside the radius nothing changes.
    Where the tiers do not decide leaving (``leave_decided_here``: quest plans keep their order,
    only 即死 pre-empts it; a floor that leaving fails the quest; town) it does not apply."""
    if not leave_decided_here(policy, snapshot):
        return None
    hostiles = engagement(policy, snapshot)
    sensing = [monster for monster in hostiles
               if not monster.asleep and inside_sensing(policy, snapshot, monster)]
    # 「倒しきれない段階の敵」: T1 on its own, judged from contact (a detected monster far off
    # would otherwise read T3 only because it has not come yet).
    strong = [monster for monster in sensing
              if cannot_win(tiered(policy, snapshot, [monster], contact=True), snapshot.player.hp)]
    if not strong:
        return None
    stairs = policy._escape_by_stairs(snapshot)
    if stairs is not None:
        policy.last_reason = SENSED_LEAVE_PREFIX + "stairs"
        return stairs
    # Owner 2026-11-09 B 「射線が通っていないなど即死ではない場合は破壊による排除を優先する」: the
    # strong monster need not be awake in view for *Destruction* (destruction_use.key leaving).
    used = destruction_use.key(policy, snapshot, leaving=strong)
    if used is not None:
        return used
    # Blind: the teleport no scroll can give (blind_teleport_key), in the scroll's place.
    if (blind := blind_teleport_key(policy, snapshot, SENSED_LEAVE_PREFIX + "teleport")) is not None:
        return blind
    scroll = policy._escape_scroll(snapshot)
    if scroll is not None:
        policy.last_reason = SENSED_LEAVE_PREFIX + (
            "teleport" if scroll.is_teleport_scroll else "phase")
        return policy._read_key(snapshot, scroll)
    if not snapshot.player.recalling and not (snapshot.player.blind or snapshot.player.confused):
        recall = next((item for item in snapshot.inventory if item.is_recall_scroll), None)
        if recall is not None and policy._can_read_scrolls(snapshot):
            policy.last_reason = SENSED_LEAVE_PREFIX + "recall"
            return policy._read_key(snapshot, recall)
    if walk_leaves(policy, snapshot, hostiles):
        step = policy._flee_step(snapshot, hostiles)
        if step is not None:
            policy.last_reason = SENSED_LEAVE_PREFIX + "walk"
            return policy._step_toward(snapshot, step)
    return None


# ---------------------------------------------------------------- the decided side (owner 2026-11-08)
#
# Owner 2026-11-08 (the bear pack: T2 by about 3 HP, left when seen and walked back to when hidden;
# the HP moved the reading across the T3/T2 boundary as well), answer 「境に余裕を持たせる」: once a
# monster's tier is decided, small changes of the HP or of the estimates do not flip it; fight or
# leave stays on the side decided first.
#
# The memory is per floor visit and per monster (the game's list index with its race, as
# retreat_veto_life): the decided tier, the side, the margins of the deciding reading and the
# monster's speed then.  A later reading of the engagement moves the tier only across a boundary
# it passes by the band, the reading's own reserve (D7 「余裕は最大HPの1割と、95%被害のうち大きい
# 方」, the margin the design already keeps between a plan and the HP): T3/T2 at ``free_margin``,
# T2/T1 at ``supply_margin``.  No new number.  Taken as read instead (the hard overrides): the
# 1-turn 即死 (3.1) and the stop conditions of the committed fight (D4); a monster new to the
# engagement, or faster than when decided, lets a worse reading through without the band (a
# stronger engagement, not an estimate's drift); a new floor visit forgets everything.  A better
# reading is taken only while every remembered monster of the deciding engagement is in this one:
# a pack mate out of sight keeps its side, so the visible part of a pack decided "leave" is not
# fought alone.  A monster that died, changed shape or was not shown for
# retreat_veto_life.UNSEEN_GAME_TURNS is forgotten (``observe``), as its retreat's veto is.
#
# The leave side reaches routing through the existing retreat veto: the flee rung claims the cell
# it leaves for the monsters it fled (policy ``_claim_engagement_avoid_cells``), so seek-loot and
# exploration do not walk back while the pack is remembered; a side that turns to fight lifts
# that veto (``retreat_veto_life.release``).

TIER_MEMORY = "_threat_tier_memory"
TIER_ORDER = (T1, T2, T3)            # worst first
TIER_RANK = {tier: rank for rank, tier in enumerate(TIER_ORDER)}


@dataclass
class Decided:
    tier: str
    leave: bool                       # the side: T1, or T2 with no selected target
    free_margin: float | None         # the deciding reading's margins and band (telemetry)
    supply_margin: float | None
    reserve: int
    speed: int                        # adjusted_speed when decided
    group: frozenset                  # the deciding engagement's (index, race) keys
    threat: retreat_veto_life.Threat  # name and the last board that showed it (``observe``)


@dataclass
class TierMemory:
    floor: tuple
    decided: dict = field(default_factory=dict)  # (index, race) -> Decided
    last_turn: int | None = None                 # the previous observed board


def _tier_memory(policy, snapshot) -> TierMemory:
    memory = getattr(policy, TIER_MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = TierMemory(snapshot.floor_key)
        setattr(policy, TIER_MEMORY, memory)
    return memory


def observe(policy, snapshot) -> None:
    """Forget the decided sides of the monsters that are gone (once per board, before the
    routes, as ``retreat_veto_life.observe``)."""
    memory = getattr(policy, TIER_MEMORY, None)
    if memory is None or memory.last_turn == snapshot.turn:
        return
    if memory.floor != snapshot.floor_key:
        setattr(policy, TIER_MEMORY, None)
        return
    shown = retreat_veto_life.shown_by_index(snapshot)
    for key, entry in list(memory.decided.items()):
        if retreat_veto_life.gone(snapshot, key, entry.threat, shown, memory.last_turn):
            del memory.decided[key]
    memory.last_turn = snapshot.turn


def forget_floor_visit(policy) -> None:
    setattr(policy, TIER_MEMORY, None)


def engagement_reading(policy, snapshot, hostiles) -> bool:
    """A reading of the engagement itself: it holds every strategic hostile in view.  A part of
    it (one monster on a beam's line, ``me_powers``) is a question about that part, not the
    decision; it neither reads nor writes the decided side."""
    indices = {monster.index for monster in hostiles}
    return bool(indices) and all(monster.index in indices
                                 for monster in policy._strategic_hostiles(snapshot))


def _past(margin: float | None) -> float:
    return float("-inf") if margin is None else margin


def held_tier(held: str, raw: Assessment, *, worse_as_read: bool, mates_in_view: bool) -> str:
    """The tier after the reading ``raw`` of an engagement decided ``held``: each boundary
    between them is crossed only when the reading is past it by the band (``raw.reserve``)."""
    band = raw.reserve
    if TIER_RANK[raw.tier] < TIER_RANK[held]:
        if worse_as_read:
            return raw.tier
        tier = held
        if tier == T3 and -_past(raw.free_margin) >= band:
            tier = T2
        if tier == T2 and raw.tier == T1 and -_past(raw.supply_margin) >= band:
            tier = T1
        return tier
    if raw.tier == held or not mates_in_view:
        return held
    tier = held
    if tier == T1 and _past(raw.supply_margin) >= band:
        tier = T2
    if tier == T2 and raw.tier == T3 and _past(raw.free_margin) >= band:
        tier = T3
    return tier


def _as_held(raw: Assessment, tier: str) -> Assessment:
    """``raw`` with the held ``tier``.  A T2 held over a T3 reading spends nothing: its plan is
    the free win (no supply is drunk or read for a fight the free attacks win)."""
    plan = raw.supply_plan
    if tier == T2 and raw.tier == T3:
        plan = SupplyPlan(categories=(), turns=raw.free_turns or 0,
                          incoming=raw.free_incoming or 0, capacity=0, reserve=raw.reserve)
    return replace(raw, tier=tier, raw_tier=raw.tier, supply_plan=plan)


def decided(policy, snapshot, hostiles, raw: Assessment) -> Assessment:
    """The engagement's reading with its decided side held (「境に余裕を持たせる」); the memory
    is updated for its monsters."""
    if raw.tier is None:
        return raw  # past the cost cap: no reading to decide, or to hold against
    memory = _tier_memory(policy, snapshot)
    keys = [(monster.index, monster.race_id) for monster in hostiles]
    entries = [memory.decided.get(key) for key in keys]
    known = [entry for entry in entries if entry is not None]
    overridden = raw.instant_death or supply_fight_stopped(snapshot, hostiles)
    tier = raw.tier
    if known and not overridden:
        here = set(keys)
        mates = set().union(*(entry.group for entry in known))
        tier = held_tier(
            next(tier for tier in TIER_ORDER if any(entry.tier == tier for entry in known)), raw,
            worse_as_read=len(known) < len(keys) or any(
                entry is not None and adjusted_speed(monster) > entry.speed
                for monster, entry in zip(hostiles, entries)),
            mates_in_view=all(key in here for key in mates if key in memory.decided))
    leave = tier == T1 or (tier == T2 and not raw.selected)
    group, fought = frozenset(keys), []
    for monster, key, entry in zip(hostiles, keys, entries):
        if entry is not None and entry.leave and not leave:
            fought.append(key)
        if entry is not None and entry.tier == tier and not overridden:
            entry.leave = leave  # the tier holds; the selection is read as it is
            continue
        memory.decided[key] = Decided(
            tier, leave, raw.free_margin, raw.supply_margin, raw.reserve,
            adjusted_speed(monster), group, retreat_veto_life.Threat(monster.name, snapshot.turn))
    if fought:
        retreat_veto_life.release(policy, snapshot, fought)
    return raw if tier == raw.tier else _as_held(raw, tier)


def decided_sides(policy, snapshot, hostiles) -> list:
    """The remembered sides of ``hostiles`` (telemetry: reads, never writes)."""
    memory = getattr(policy, TIER_MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        return []
    return [{"index": monster.index, "tier": entry.tier, "leave": entry.leave}
            for monster in hostiles
            if (entry := memory.decided.get((monster.index, monster.race_id))) is not None]


def tier_of(policy, snapshot, hostiles) -> str | None:
    """The engagement's tier where the tiers act, else None."""
    if not hostiles or not acts_here(policy, snapshot):
        return None
    return tiered(policy, snapshot, hostiles).tier


# The selected supply fight (plan step 7, 3.4, D3, D4, D7): the reasons it answers with.
SUPPLY_SPEED_REASON = "supply-fight:quaff-speed"
SUPPLY_HEAL_REASON = "supply-fight:quaff-healing"
SUPPLY_RESIST_REASON = "supply-fight:quaff-resistance"
SUPPLY_AMMO_REASON = "supply-fight:fire-good-ammo"
SUPPLY_WAND_REASON = "supply-fight:aim-wand"
SUPPLY_STAFF_REASON = "supply-fight:use-staff"
SUPPLY_SCROLL_REASON = "supply-fight:read-attack-scroll"
# The cheapest healing potion first (each credited as in the projection).
HEAL_ORDER = (SV_POTION_HEALING, SV_POTION_STAR_HEALING, SV_POTION_LIFE)


def supply_fight_applies(policy, snapshot) -> bool:
    """Where the selected supply fight replaces today's supplied unique fight (step 7): the
    tiers' floors (``acts_here``); elsewhere the unique fight stays as it is."""
    return acts_here(policy, snapshot)


def _fight_target(policy, hostiles, result):
    """The selected monster the fight is for: the committed race while it is in view, else the
    nearest selected one."""
    selected = [monster for monster in hostiles if monster.index in result.selected]
    committed = policy._unique_combat_committed_race_id
    for monster in selected:
        if monster.race_id == committed:
            return monster
    return min(selected, key=lambda monster: (monster.distance, monster.index), default=None)


def supply_fight_stopped(snapshot, hostiles, target=None) -> bool:
    """D4: today's stop conditions of the committed unique fight: the player afraid, blind,
    confused or paralysed, a breeder in view, or another summoner in view (with no ``target``:
    any summoner, the decided side's hold reading the engagement as a whole)."""
    player = snapshot.player
    return bool(
        player.afraid or player.blind or player.confused or player.paralyzed
        or any(monster.can_multiply for monster in hostiles)
        or any(monster.can_summon and (target is None or monster.index != target.index)
               for monster in hostiles))


def ranged_plan(policy, snapshot, result, target) -> bool:
    """D4 「the adjacency requirement is dropped for ranged plans」: the plan spends an attack
    supply (good ammo, charges, scrolls), or its free attack on the target is not melee."""
    plan = result.supply_plan
    if plan is not None and (plan.good_ammo or plan.charges or plan.scrolls):
        return True
    free = result.free_damage.get(target.index, 0.0)
    return free > 0 and free > attack_expectation.melee(policy, snapshot, target)


def committed_supply_fight_viable(policy, snapshot, hostiles) -> bool:
    """Plan step 7 (3.4, OQ-2, D4): a committed selected fight is not left while the projection
    with the remaining supplies still wins (T2, or T3: it wins with none), its target is still
    selected and in reach of the plan, and none of today's stop conditions holds.  Only the
    1-turn 即死 aborts it otherwise (``_emergency_item``'s ``lethal``)."""
    race = policy._unique_combat_committed_race_id
    if race is None:
        return False
    targets = [monster for monster in hostiles if monster.race_id == race]
    if len(targets) != 1 or supply_fight_stopped(snapshot, hostiles, targets[0]):
        return False
    target = targets[0]
    result = tiered(policy, snapshot, hostiles)
    if result.tier not in (T2, T3) or target.index not in result.selected:
        return False
    return target.distance <= 1 or ranged_plan(policy, snapshot, result, target)


def _aim(policy, snapshot, target) -> str | None:
    """A direction key that reaches ``target``: beside it, or on a clear ray (``_ranged_target``)."""
    if target.distance <= 1 or policy._ranged_target(snapshot, [target]) is target:
        return policy._direction_key(snapshot.player.position, target.position)
    return None


def _spend(policy, snapshot, target, verb, item, reason, suffix=""):
    key = reserved_item_command(policy, snapshot, verb, item, suffix=suffix)
    if key is not None:
        policy.last_reason = reason
        policy._unique_combat_committed_race_id = target.race_id
    return key


def _heal_key(policy, snapshot, result, target):
    """Today's rule of the supplied fight (``_unique_combat_consumable``): drink when HP is
    missing and the next action could breach the reserve, or three quarters of the dose are
    missing; only a dose that out-heals the next action (the projection's credit)."""
    player, plan = snapshot.player, result.supply_plan
    missing = player.max_hp - player.hp
    if missing <= 0:
        return None
    for sval in HEAL_ORDER:
        potion = policy._find_exact_potion(snapshot, sval)
        amount = min(HEAL_AMOUNTS[sval], player.max_hp)
        if potion is None or amount <= result.next_action_p95:
            continue
        if result.next_action_p95 >= player.hp - plan.reserve or missing * 4 >= amount * 3:
            return _spend(policy, snapshot, target, "quaff", potion, SUPPLY_HEAL_REASON)
        return None
    return None


def _resistance_key(policy, snapshot, target):
    if _resistance_after(snapshot) is None:
        return None
    for sval in (SV_POTION_RESISTANCE, SV_POTION_RESIST_HEAT, SV_POTION_RESIST_COLD):
        potion = policy._find_exact_potion(snapshot, sval)
        if potion is not None:
            return _spend(policy, snapshot, target, "quaff", potion, SUPPLY_RESIST_REASON)
    return None


def _good_ammo_key(policy, snapshot, result, target):
    launcher = policy._equipped_launcher(snapshot)
    if launcher is None or not _ranged_ready(snapshot):
        return None
    direction = _aim(policy, snapshot, target)
    if direction is None:
        return None
    free = result.free_damage.get(target.index, 0.0)
    for good, damage, number in (
            (good, damage, number) for number, (good, damage, _rounds)
            in enumerate(_launcher_stacks(policy, snapshot, target))):
        if good and damage > free:
            stacks = [item for item in snapshot.inventory
                      if item.tval == launcher.ammo_tval and item.count > 0]
            return _spend(policy, snapshot, target, "fire", stacks[number], SUPPLY_AMMO_REASON,
                          direction)
    return None


def _charge_key(policy, snapshot, result, target):
    if not _ranged_ready(snapshot) or snapshot.inside_arena:
        return None
    flags, level = _race_flags(policy, target), snapshot.player.level
    free = result.free_damage.get(target.index, 0.0)
    direction = _aim(policy, snapshot, target)
    best = None
    for item in snapshot.inventory:
        kind = "wand" if item.tval == TVAL_WAND else "staff" if item.tval == TVAL_STAFF else None
        if kind is None or not item.known or item.charges <= 0 or item.charging:
            continue
        power = me_device_attacks.POWERS.get((kind, item.sval))
        if power is None or power.group_only or (kind == "wand" and direction is None):
            continue
        damage = (attack_expectation.device_use_success(snapshot.player.device_skill, power.level)
                  * me_device_attacks.expected_damage(power, level, flags))
        if damage > free and (best is None or damage > best[0]):
            best = (damage, kind, item)
    if best is None:
        return None
    _damage, kind, item = best
    if kind == "wand":
        return _spend(policy, snapshot, target, "wand", item, SUPPLY_WAND_REASON, direction)
    return _spend(policy, snapshot, target, "staff", item, SUPPLY_STAFF_REASON)


def _scroll_key(policy, snapshot, result, target):
    reads = _scroll_reads(snapshot)
    free = result.free_damage.get(target.index, 0.0)
    if not reads or scroll_damage_at(reads[0], target.distance) <= free:
        return None
    sval = next(sval for sval, scroll in ATTACK_SCROLLS.items() if scroll == reads[0])
    item = next((item for item in snapshot.inventory
                 if item.tval == TVAL_SCROLL and item.sval == sval and item.aware), None)
    if item is None:
        return None
    key = policy._read_key(snapshot, item)
    if key is not None:
        policy.last_reason = SUPPLY_SCROLL_REASON
        policy._unique_combat_committed_race_id = target.race_id
    return key


def supply_fight_key(policy, snapshot, hostiles) -> str | None:
    """Plan step 7: spend the supplies of a selected T2 fight (answer 4, 3.4, D7).

    The engagement is T2 and holds a selected target (the active quest's target, the hunted
    guardian (D3), a monster the player cannot escape, a reward race; being UNIQUE alone is not
    one, OQ-4).  The cheapest winning plan (the shortest prefix of the owner's order 「加速を
    先に」 against the reserve max(10% max HP, the next-action p95), ``assess``) is spent: Speed
    first; Healing when today's supplied-fight rule says the dose is due; the planned
    resistance while its opposition is not on; then the attack supplies in the owner's order,
    good ammo, wand / staff charges, attack scrolls, each only where it out-damages the free
    attack.  A melee plan needs the target beside the player; a ranged plan does not (D4).  The
    fight is committed on the first supply spent (``_committed_unique_fight_viable``)."""
    if not hostiles:
        return None
    committed = policy._unique_combat_committed_race_id
    if committed is not None and not any(monster.race_id == committed for monster in hostiles):
        policy._unique_combat_committed_race_id = committed = None
    if committed is None and getattr(policy, "_returning_to_town", False):
        # The floor is being left (a latched return: the escape it reads is no fight to stay
        # for).  No new supply fight opens then; the design is silent here, and the acceptance
        # is that no escape becomes a stay (n1-c life-083's return:recall beside an ogre).
        return None
    result = tiered(policy, snapshot, hostiles)
    if result.tier != T2 or result.supply_plan is None:
        return None
    target = _fight_target(policy, hostiles, result)
    if target is None or supply_fight_stopped(snapshot, hostiles, target):
        return None
    if target.distance > 1 and not ranged_plan(policy, snapshot, result, target):
        return None
    plan = result.supply_plan
    if plan.speed_doses > 0 and not _hasted(policy, snapshot):
        key = speed_dose.key(policy, snapshot, SUPPLY_SPEED_REASON)
        if key is not None:
            policy._unique_combat_committed_race_id = target.race_id
            return key
    if plan.heals and (key := _heal_key(policy, snapshot, result, target)) is not None:
        return key
    if plan.resistance and (key := _resistance_key(policy, snapshot, target)) is not None:
        return key
    if plan.good_ammo and (key := _good_ammo_key(policy, snapshot, result, target)) is not None:
        return key
    if plan.charges and (key := _charge_key(policy, snapshot, result, target)) is not None:
        return key
    if plan.scrolls and (key := _scroll_key(policy, snapshot, result, target)) is not None:
        return key
    return None


def outside_design(snapshot) -> bool:
    """Town, a store and the arena: the boards the tiers' telemetry judges nothing on."""
    return snapshot.in_town or snapshot.store is not None or snapshot.inside_arena


def facts(policy, snapshot) -> dict:
    """The decision-row telemetry: the assessment, {} where the design does not apply."""
    if outside_design(snapshot):
        return {}
    try:
        hostiles = engagement(policy, snapshot)
        if not hostiles:
            return {}
        result = assess(policy, snapshot, hostiles).as_dict()
        result["decided"] = decided_sides(policy, snapshot, hostiles)
        return result
    except Exception as exc:  # noqa: BLE001 -- telemetry must never stop the decision writer
        return {"error": f"{type(exc).__name__}: {exc}"}
