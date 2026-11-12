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
- ``instant_death``: 3.1 即死 (``instant_death``; the plans' rung ``instant_death_key`` stays
  here: it calls ``instant_death``, which tests patch here).
- ``threat_escape``: the flags (4.1-4.4) and the escape means, ``blind_teleport_key``.
- ``supply_fight``: the selected supply fight's reasons and per-supply keys (the rung
  ``supply_fight_key`` and its gates stay here: they call ``tiered`` and ``acts_here``).
- ``threat_tier_memory``: the decided side's memory (``TierMemory``, ``held_tier``, owner
  2026-11-08); the hold ``decided`` and the worsening leave stay here (``leave_decided_here``).
- here: ``assess``, the selection (3.4) and acting on the tiers (steps 6-8).
"""

from __future__ import annotations

from hengbot import (
    destruction_use,
    disenchant_avoid,
    hunt_target,
    retreat_veto_life,
    speed_dose,
    survival_preemption,  # noqa: F401 -- re-exported (tests patch threat_tiers.survival_preemption)
)
from hengbot.item_reservation import decision_memo
from hengbot.model import game_distance
# The façade (maintainability review 2026-11-09, step 4): every name of the split modules is
# re-exported here, so ``threat_tiers.X`` keeps working for callers, tests and their patches.
from hengbot.instant_death import (  # noqa: F401
    InstantDeath,
    NEXT_ACTION_P95,
    _instant_death,
    instant_death,
)
from hengbot.supply_fight import (  # noqa: F401
    SUPPLY_SPEED_REASON,
    SUPPLY_HEAL_REASON,
    SUPPLY_RESIST_REASON,
    SUPPLY_AMMO_REASON,
    SUPPLY_WAND_REASON,
    SUPPLY_STAFF_REASON,
    SUPPLY_SCROLL_REASON,
    HEAL_ORDER,
    _fight_target,
    supply_fight_stopped,
    ranged_plan,
    _aim,
    _spend,
    _heal_key,
    _resistance_key,
    _good_ammo_key,
    _charge_key,
    _scroll_key,
)
from hengbot.threat_escape import (  # noqa: F401
    SV_SCROLL_TELEPORT_LEVEL,
    STAFF_REASON_SUFFIX,
    STAT_DRAIN_BLOWS,
    ELEMENTS,
    irreversible_kinds,
    worsens_kinds,
    _stair_distance,
    escape_means,
    blind_teleport_key,
    ABSORBED,
    blind_teleport_means,
    escape_restorable,
    need_not_fight,
)
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
from hengbot.threat_tier_memory import (  # noqa: F401
    TIER_MEMORY,
    TIER_ORDER,
    TIER_RANK,
    Decided,
    TierMemory,
    _tier_memory,
    observe,
    forget_floor_visit,
    engagement_reading,
    _past,
    held_tier,
    _as_held,
    worsens_left,
    decided_sides,
)

# monster-death.cpp:226-251 decide_drop_numbers; the owner's counts (OQ-8).
DROP_COUNTS = {"DROP_60": 0.6, "DROP_90": 0.9, "DROP_1D2": 1.5, "DROP_2D2": 3.0,
               "DROP_3D2": 4.5, "DROP_4D2": 6.0}
MANY_DROPS = 3.0
REWARD_EXP_SHARE = 0.10             # answer 5: 10% of the exp still needed
REWARD_EXP_KILL_FACTOR = 1.5        # OQ-11: 1.5 x level x mexp / (max_plv + 2)
SURFACE_EXP_DIVISOR = 5             # monster-damage.cpp:155


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
    # Owner 2026-11-09 「倒しきれない敵と同じに離れる」 (design 4.4): a summoner or shrieker left
    # as a T1 is (``_worsens_leave``, held by the decided side).
    # Owner 2026-11-09 「前からの2つを先に」: where the summoner cover step or the choke wait
    # answers, they do; the leave only where neither does.
    if (result.tier is not None and worsens_left(policy, snapshot, hostiles)
            and not policy._summoner_shelter_applies(snapshot, hostiles)):
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
    # Owner 2026-11-10 (the n1-b life-367 report's P2, verbatim 「積極的に*破壊*で消しにいく」):
    # a T1 known only by detection is gone to and destroyed, not left (``approach_key``).
    if approach_owns(policy, snapshot, strong):
        # None: no known way toward them yet (the circle just destroyed, say); the rungs
        # below map and explore, and the next board asks again.
        return approach_key(policy, snapshot, strong)
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


APPROACH_REASON = SENSED_LEAVE_PREFIX + "approach-destruction"


def _in_view(policy, snapshot, monster) -> bool:
    """Seen, not only detected, and on a line it can project along to the player (the
    board's test of an attacker, return_yield.awake_hostile_in_view): a monster the
    telepathy shows behind rock is known only by detection."""
    return (monster.perception != "detected"
            and policy._may_project(snapshot, monster.position, snapshot.player.position))


def _approach_targets(policy, snapshot, strong) -> list:
    """The T1s ``approach_key`` goes to, else [] (its docstring's conditions)."""
    if any(_in_view(policy, snapshot, monster) for monster in strong):
        return []
    if not destruction_use.holds_means(policy, snapshot):
        return []
    if (not destruction_use._clear_headed(snapshot.player)
            or not destruction_use._floor_destroyed(policy, snapshot)):
        return []
    spared = {destruction_use._guardian_race(policy, snapshot),
              destruction_use._target_race(policy, snapshot)}
    return [monster for monster in strong if monster.race_id not in spared]


def approach_owns(policy, snapshot, strong) -> bool:
    """The sensed T1 leave gives way to ``approach_key``: every T1 is known only by detection,
    the means are held, and none of them is already in reach of a use the gates refuse."""
    targets = _approach_targets(policy, snapshot, strong)
    if not targets:
        return False
    here = snapshot.player.position
    in_reach = any(game_distance(here, monster.position) <= destruction_use.GUARANTEED_RADIUS
                   for monster in targets)
    return not in_reach or destruction_use.usable(policy, snapshot, leaving=targets)


def approach_key(policy, snapshot, strong) -> str | None:
    """While ``approach_owns``: the use of *Destruction* once a T1 is within its sure radius,
    else a step toward the nearest; else None (no known way yet: the rungs below map and
    explore, and the leave does not read).

    Owner 2026-11-10 (the n1-b life-367 report's P2, verbatim 「積極的に*破壊*で消しにいく」;
    the question named ハヤブサ (Ki-43, vision 100) and 大鷲王『ソロンドール』, whose sensing radius
    covers the floor: 29 leaves on 46F+ boards whose engagement was T3, each a Teleportation
    counted toward the two-escape return).

    Game (C:/hengband/src): spell-kind/spells-floor.cpp destroy_area deletes every monster
    in the circle but a QUESTOR (healed and teleported away), uniques too, and does nothing
    on a fixed quest floor or the surface; the radius is 13 + randint0(5) (staff,
    cmd-usestaff.cpp:282; scroll, scroll-read-executor.cpp:342), 18 + randint0(5) for the
    Powerful Activation, never cast here.  The walk aims at the sure radius
    (destruction_use.GUARANTEED_RADIUS, 13).

    The means are destruction_use's (owner 2026-11-04 「杖と取り込んだ力だけ」, at 80%+ with a
    charge, ``holds_means``); the use is destruction_use's ``key`` with the T1s as the
    ``leaving`` hostiles, its gates unchanged.  Not here: a T1 in view (the in-view rules
    answer, as before), a floor *Destruction* does not touch, a confused, hallucinating or
    stunned player, the floor's own guardian (destruction_use spares it: the 11-04 words do
    not cover it), the active quest's target.  The step is a walk, never an escape
    (reasons.WALK)."""
    targets = _approach_targets(policy, snapshot, strong)
    if not targets:
        return None
    used = destruction_use.key(policy, snapshot, leaving=targets)
    if used is not None:
        return used
    radius = destruction_use.GUARANTEED_RADIUS
    step = policy._nearest_goal_step(snapshot, lambda grid: any(
        game_distance(grid.position, monster.position) <= radius for monster in targets))
    if step is None:
        return None
    policy.last_reason = APPROACH_REASON
    return policy._step_toward(snapshot, step)


# ---------------------------------------------------------------- the decided side (step 6)
# The hold itself (owner 2026-11-08 「境に余裕を持たせる」; the memory and its design note are in
# threat_tier_memory).  ``decided`` and ``_worsens_leave`` stay here: the worsening leave
# reads ``leave_decided_here`` (``acts_here``, which tests patch here).

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
    engagement_leave = tier == T1 or (tier == T2 and not raw.selected)
    worsening = _worsens_leave(policy, snapshot, hostiles, raw, entries)
    group, fought = frozenset(keys), []
    for monster, key, entry in zip(hostiles, keys, entries):
        leave = engagement_leave or key in worsening
        if entry is not None and entry.leave and not leave:
            fought.append(key)
        if entry is not None and entry.tier == tier and not overridden:
            entry.leave = leave  # the tier holds; the selection is read as it is
            entry.worsens = key in worsening
            continue
        memory.decided[key] = Decided(
            tier, leave, raw.free_margin, raw.supply_margin, raw.reserve,
            adjusted_speed(monster), group, retreat_veto_life.Threat(monster.name, snapshot.turn),
            key in worsening)
    if fought:
        retreat_veto_life.release(policy, snapshot, fought)
    return raw if tier == raw.tier else _as_held(raw, tier)


# A selection that makes the kill required (4.4 step 4: 「倒す必要があれば物資を使って早く倒す」);
# the reward selection does not (a T1 is left whatever it would drop).
KILL_REQUIRED = frozenset({"quest-target", "hunted-guardian", "cannot-escape"})


def _worsens_leave(policy, snapshot, hostiles, raw, entries) -> set:
    """Owner 2026-11-09 (Q1 of the n1-a life-500 report, verbatim 「倒しきれない敵と同じに離れる」:
    「脅威度の「離れる」と同じに扱い、一度離れると決めたら境に余裕を持って保つ。」), design 4.4
    「逃げて良いなら逃げる」: outside quests, an awake summoner or shrieker that is not killed
    被害無く (worsens_kill.harmless, OQ-1 option A) and whose kill is not required is left as a T1
    is.  Once left it stays left for the floor visit while it is remembered (the decided side;
    a reading that turns 被害無く does not bring it back).  Breeders keep their owner rules.
    The (index, race) keys left so."""
    player = snapshot.player
    if (snapshot.floor_key[2] != 0 or not leave_decided_here(policy, snapshot)
            # Below the low-HP line the 11-06 escape answers (OQ-10).
            or player.hp < policy._low_hp_walk_threshold(player.max_hp)):
        return set()
    from hengbot import worsens_kill

    # The more specific owner rules keep their monsters (4.4 step 1): a paralyser is left by
    # the 09-18 / 11-09 E rules, a summoner that never approaches (NEVER_MOVE, or its choke wait
    # expired) by the immobile-summoner rules (owner 2026-10-27 「動かない召喚の敵は近づかずに避ける」).
    paralysers = {monster.index for monster in policy._paralyzing_monsters(snapshot, hostiles)}
    left = set()
    for monster, entry in zip(hostiles, entries):
        key = (monster.index, monster.race_id)
        if entry is not None and getattr(entry, "worsens", False):
            left.add(key)  # held: 「一度離れると決めたら境に余裕を持って保つ」
            continue
        row = raw.per_monster.get(monster.index)
        if (monster.asleep or row is None or monster.index in paralysers
                or policy._summoner_never_approaches(snapshot, monster)
                or not set(row.worsens_with_time) - {"multiply"}
                or set(row.selected) & KILL_REQUIRED):
            continue
        if not worsens_kill.harmless(policy, snapshot, monster):
            left.add(key)
    return left


def tier_of(policy, snapshot, hostiles) -> str | None:
    """The engagement's tier where the tiers act, else None."""
    if not hostiles or not acts_here(policy, snapshot):
        return None
    return tiered(policy, snapshot, hostiles).tier


# ---------------------------------------------------------------- the supply fight (step 7)

def supply_fight_applies(policy, snapshot) -> bool:
    """Where the selected supply fight replaces today's supplied unique fight (step 7): the
    tiers' floors (``acts_here``); elsewhere the unique fight stays as it is."""
    return acts_here(policy, snapshot)


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
