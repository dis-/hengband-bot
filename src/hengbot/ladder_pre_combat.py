"""The pre-combat layer of the dungeon ladder (dungeon_ladder.LADDER, layer "pre-combat").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the approved quest floor
(ladder_plan_approved_quest), above the flee, melee and ranged rungs of the combat layer.  The
mining loadout's rollback, the one-shot quest's Speed dose, the open wilderness, the town's
mob, confusion, the breeder breakthrough and choke, the fruitless and unprofitable disengages,
the mining exits and the swarm's melee.  The rungs are asked top-down and the first key
returned wins, as in ``_decide``; ``PASS`` hands the decision on to the layers below.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.

The hostile views are ``_decide``'s, passed in unchanged, by name.  The mining views this layer
chooses (the physical views while mining or scavenging, the strategic ones otherwise) are read
again by the combat layer's fundraising equipment rung: ``MiningViews`` carries the value
chosen here, at this point of the decision, back to ``_decide``.
"""
from __future__ import annotations

from hengbot import disenchant_avoid, speed_dose, zul_trip
from hengbot.dungeon_ladder import PASS
from hengbot.policy_constants import WAIT_KEY


class MiningViews:
    """The mining hostiles this layer chose, for the combat layer (set before the swarm rung)."""

    __slots__ = ("hostiles",)

    def __init__(self):
        self.hostiles = None


def key(
    policy,
    snapshot,
    *,
    strategic_hostiles,
    strategic_adjacent,
    physical_hostiles,
    physical_adjacent,
    mining,
):
    """The pre-combat layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    # D45: a combat hand the digger swap left empty goes back before any
    # fight rung below takes the turn (mining_loadout.py).  An approved
    # quest floor's navigator above owns its own combat.
    rearm = policy._town_producer_entry("_mining_loadout_rollback_key", lambda: policy._mining_loadout_rollback_key(snapshot), family="equipment-txn")
    if rearm is not None:
        return rearm

    # A reviewed one-shot quest is entered on the assumption that its carried
    # Speed dose is part of the action-economy budget.  Spend it on first
    # contact, once for this floor entry (a rejected command is not looped).
    active_quest = policy._active_fixed_quest_id(snapshot) or policy._active_kill_quest_id(snapshot)
    if (
        active_quest is not None
        and policy.approved_quest_strategy(active_quest) is None
        and strategic_hostiles
        and policy._unviable_quest_floor != snapshot.floor_key
        and not policy._fixed_quest_speed_attempted
    ):
        policy._fixed_quest_speed_attempted = True
        speed = speed_dose.key(policy, snapshot, "quest:quaff-speed",
                               rearm=("_fixed_quest_speed_attempted", False))
        if speed is not None:
            return speed

    # 0a. Open wilderness = a non-town surface tile the town routine strayed
    #     onto by crossing a map border. It spawns out-of-depth monsters (a
    #     Cyclops killed a clvl-4 bot here). Survival is the ONLY goal: flee,
    #     recall to safety, never shop/explore/fight for XP.
    if snapshot.on_open_wilderness and zul_trip.trip_active(policy):
        # The Zul trip's ambush (owner 2026-11-07 「ふつうに戦い全体地図へ戻る」):
        # an awake monster in view is fought by the ordinary rules below.
        ambush = zul_trip.ambush_key(policy, snapshot, physical_hostiles)
        if ambush is not None:
            return ambush
    elif snapshot.on_open_wilderness:
        # Owner 2026-11-08 「敵を倒すか離れてから出る」: None with an awake
        # monster in view leaves the board to the ordinary combat rules.
        wilderness = policy._town_producer_entry("_wilderness_survival_key", lambda: policy._wilderness_survival_key(snapshot, physical_hostiles), family="survival")
        if wilderness is not None:
            return wilderness

    # Town is cleared before errands resume.  Unlike dungeon hunting every
    # visible non-pet monster is a target regardless of range or the
    # hostile-count cap; a friendly race the character cannot defeat is
    # the one exception (USER DECISION 2026-10-31, _town_kill_mob_key).
    town_kill = policy._town_producer_entry("_town_kill_mob_key", lambda: policy._town_kill_mob_key(snapshot))
    if town_kill is not None:
        return town_kill

    # 0b. Ride out confusion in a safe spot rather than stumbling randomly.
    if player.confused and not physical_hostiles:
        policy.last_reason = "confused:wait"
        return WAIT_KEY

    if (
        policy._choke_plan_active(snapshot)
        and policy._breeder_breakthrough_floor == snapshot.floor_key
    ):
        policy._release_choke_plan("breeder-breakthrough")
    breakthrough = policy._town_producer_entry("_breeder_breakthrough_key", lambda: policy._breeder_breakthrough_key(
        snapshot, strategic_hostiles
    ))
    if breakthrough is not None:
        if policy._choke_plan_active(snapshot):
            policy._release_choke_plan("breeder-breakthrough")
        policy._declare_triggers(strategic_hostiles)
        return breakthrough

    choke_plan = policy._town_producer_entry("_choke_engagement_key", lambda: policy._choke_engagement_key(
        snapshot, physical_hostiles, physical_adjacent
    ))
    if choke_plan is not None:
        return choke_plan

    breeders = disenchant_avoid.not_avoided(policy, snapshot, [
        monster for monster in strategic_hostiles if monster.can_multiply
    ])
    if (
        breeders
        and policy._breeder_breakthrough_floor != snapshot.floor_key
    ):
        breeder_adjacent = [
            monster for monster in strategic_adjacent if monster.can_multiply
        ]
        ranged = policy._town_producer_entry("_ranged_attack_key#1", lambda: policy._ranged_attack_key(
            snapshot, breeders, breeder_adjacent
        ))
        if ranged is not None:
            return ranged

    # A fruitless breeder engagement latches this floor visit. Keep this
    # ahead of ordinary combat so the same cluster cannot pull us back in.
    disengage = None
    if not policy._productive_choke_hold(snapshot):
        disengage = policy._town_producer_entry("_fruitless_disengage_key", lambda: policy._fruitless_disengage_key(
            snapshot, strategic_hostiles
        ))
    if disengage is not None:
        policy._declare_triggers(strategic_hostiles)
        return disengage
    if policy._escape_state.owner == "disengage":
        policy._escape_state.stable_decisions += 1
        if policy._escape_state.stable_decisions >= 2:
            policy._escape_state.release()

    # Owner 2026-10-31: a mining run that meets the unique the owner
    # rules out ends here, before any mining or ordinary combat rung can
    # attack it.
    mining_abort = policy._town_producer_entry("_mining_unbeatable_unique_abort_key", lambda: policy._mining_unbeatable_unique_abort_key(
        snapshot, strategic_hostiles, strategic_adjacent
    ), family="fundraising")
    if mining_abort is not None:
        return mining_abort

    # A harmless but extremely durable unique can otherwise fall through
    # the consumable projection and into ordinary melee forever.  Arm a
    # floor-level disengage while it is visible; the latch survives BLINK
    # and TELEPORT interruptions that reset the contiguous combat tracker.
    unprofitable_unique = policy._town_producer_entry("_unprofitable_unique_disengage_key", lambda: policy._unprofitable_unique_disengage_key(
        snapshot, strategic_hostiles
    ), family="escape")
    if unprofitable_unique is not None:
        return unprofitable_unique

    if (
        policy._fundraising_mode in {"mine", "scavenge"}
        and policy._breeder_breakthrough_floor == snapshot.floor_key
    ):
        combat_equip = policy._town_producer_entry("_fundraising_combat_equipment_key", lambda: policy._fundraising_combat_equipment_key(
            snapshot, physical_hostiles
        ), family="equipment-txn")
        if combat_equip is not None:
            return combat_equip
        key = policy._town_producer_entry("_finish_mining_floor", lambda: policy._finish_mining_floor(snapshot), family="fundraising")
        if key is not None and (
            key != WAIT_KEY
            or policy.last_reason != "fundraise:upstairs-not-found"
        ):
            return key
        # The fundraising exit ran out of actions: its terminal WAIT is
        # absorbing (no recall to wait on, no reachable stairs, nothing
        # to explore, wander, or dig — nothing external changes it).  The
        # extermination-impossible latch owns leaving, so fall back to
        # the breakthrough's own exits: through-the-swarm routing to a
        # remembered up-stairs, else to the nearest live frontier.  With
        # neither, fall through to the ordinary navigation ladder like
        # the non-mining exhausted floor.
        escape = policy._town_producer_entry("_breeder_breakthrough_escape_key", lambda: policy._breeder_breakthrough_escape_key(snapshot))
        if escape is not None:
            return escape

    # Mining/swarm contact has a deliberately ordered combat transition.
    # Keep the diggers on while a missile can repel the approach; once
    # contact persists, re-arm before any ordinary melee decision.
    mining_hostiles = (
        physical_hostiles
        if policy._fundraising_mode in {"mine", "scavenge"}
        else strategic_hostiles
    )
    mining_adjacent = (
        physical_adjacent
        if policy._fundraising_mode in {"mine", "scavenge"}
        else strategic_adjacent
    )
    # The combat layer's fundraising equipment rung reads this view as chosen here.
    mining.hostiles = mining_hostiles
    swarm_combat = policy._town_producer_entry("_melee_swarm_combat_key", lambda: policy._melee_swarm_combat_key(
        snapshot, mining_hostiles, mining_adjacent
    ))
    if swarm_combat is not None:
        return swarm_combat
    return PASS
