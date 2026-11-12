"""The descent layer of the dungeon ladder (dungeon_ladder.LADDER, layer "descent").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the rest layer
(ladder_rest), above the idle layer (ladder_idle).  Descending from a downstairs or dungeon
entrance while healthy, the blocked descents, the avoided engagement, the descent step and its
clearing, the hunt and the entrance travel.  The rungs are asked top-down and the first answer
wins, as in ``_decide``: the direct descent's entry refused ends the decision with None, as it
did.  ``PASS`` hands the decision on to the idle layer.  scripts/dungeon_ladder_lint.py reads
the rows here (dungeon_ladder.LAYER_MODULES), so the table still states this order.

``here`` is ``_decide``'s cell under the player, passed in unchanged, by name.
"""
from __future__ import annotations

from hengbot import immobile_threat_memory
from hengbot.dungeon_ladder import PASS
from hengbot.policy_constants import DESCEND_MIN_HP_RATIO, DOWN_STAIRS_KEY, ENTER_DUNGEON_MACRO
from hengbot.policy_fundraising import FundraisingPurpose
from hengbot.stair_destination import down_destination


def key(policy, snapshot, *, strategic_hostiles, here):
    """The descent layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    # 5. Descend when standing on a downstairs or dungeon entrance — only
    #    while healthy, so we never dive deeper than we can handle.
    static_entrance_here = (
        snapshot.in_town
        and policy._town_map_active(snapshot)
        and policy._town_map_descent_entrance(snapshot) == player.position
        and here is not None
        and policy._is_active_dungeon_entrance(here)
    )
    direct_destination_depth = (
        policy._dungeon_entry_depth(
            snapshot, policy._active_dungeon_target(), via_recall=False
        )
        if static_entrance_here
        or (
            snapshot.dungeon_level == 0
            and here is not None
            and here.has_entrance
            and policy._is_active_dungeon_entrance(here)
        )
        else down_destination(snapshot.dungeon_level, here)
        if snapshot.dungeon_level > 0
        and here is not None
        and here.is_descent
        else None
    )
    if (
        (
            here is not None
            and here.is_descent
            and policy._is_descent_target(snapshot, here)
            or static_entrance_here
        )
        and player.hp_ratio >= DESCEND_MIN_HP_RATIO
        and not policy._descent_is_blocked(snapshot)
        # Routing toward town may yield to another escape owner, but no
        # owner may route us back into the breeder floor we just fled.
        and not policy._breeder_walkout_active(snapshot)
        and (
            direct_destination_depth is None
            or policy._destination_depth_allowed(
                snapshot, direct_destination_depth
            )
        )
        and (
            not (
                static_entrance_here
                or (
                    snapshot.dungeon_level == 0
                    and here is not None
                    and here.has_entrance
                )
            )
            or policy._dungeon_entry_allowed(
                snapshot,
                via_recall=False,
                destination_depth=policy._dungeon_entry_depth(
                    snapshot, policy._active_dungeon_target(), via_recall=False
                ),
            )
        )
    ):
        policy.last_reason = "descend"
        key = policy._town_producer_entry(
            "direct-descent", lambda: (
                ENTER_DUNGEON_MACRO
                if static_entrance_here or (here is not None and here.has_entrance)
                else DOWN_STAIRS_KEY), family="departure")
        if key is None:
            return None
        if (getattr(policy, "_crossarea_fundraising_enforced", False)
                and snapshot.in_town
                and policy._fundraising_mode in {"mine", "scavenge"}):
            facts = policy._fundraising_facts(snapshot)
            prior = policy._fundraising_purpose_record
            policy._fundraising_run_purpose = (
                prior.purpose
                if prior is not None and prior.status == "active"
                else FundraisingPurpose(
                    identity=policy._decision_sequence,
                    mode=policy._fundraising_mode,
                    first_run_food_waiver=(
                        not facts.carried_edible and facts.first_run
                        and facts.procurement_exhausted
                    ),
                )
            )
        return key

    # If every known way forward fails the next-depth resistance gate,
    # invalidate the descent route and keep exploring this (highest safe)
    # floor.  The lack of readiness for depth N+1 is not a reason to abandon
    # useful exploration on safe depth N.
    if policy._all_known_descents_blocked_by_next_depth_requirements(snapshot):
        policy._nav_ledger.clear_descent_route()
        policy._descent_target_goal = None

    # A monster can be just outside the material-threat threshold at its
    # current distance while becoming material after one closing step.
    # Preserve higher-priority concrete work such as safe loot recovery,
    # but retreat before descent, hunting, or generic exploration can
    # close into the engagement and alternate with the threat gate.
    # A sleeping monster is retreated from too when it is this strong
    # (owner 2026-11-07: only a weak one, which is not a material melee
    # engagement, is not); the dead end that retreat walked into (n1-c
    # life-153 Labyrinth 13F) is answered by engagement_avoid_seal.
    if any(
        policy._material_melee_engagement(snapshot, monster)
        and not immobile_threat_memory.ringed(policy, monster)
        for monster in strategic_hostiles
    ):
        avoid_engagement = policy._avoid_engagement_key(snapshot, strategic_hostiles)
        if avoid_engagement is not None:
            return avoid_engagement

    # 6. Head for a known downstairs / dungeon entrance: path straight there
    #    if reachable, otherwise explore toward it (the entrance may be known
    #    but its approach still unmapped — e.g. the town's wilderness gate).
    #    A single BFS covers both, so the huge full-map scan runs only once.
    step = policy._town_producer_entry("_descent_step", lambda: policy._descent_step(snapshot))
    if step is not None:
        # A visible monster can temporarily split the only known route to
        # the stairs. Chasing a fallback frontier makes the monster vanish
        # from sight, after which we turn back toward the stairs forever.
        # Clear an easy blocker instead of bouncing at the visibility edge.
        if policy.last_reason == "approach-descent" and strategic_hostiles:
            clear_step = policy._town_producer_entry("_hunt_step#2", lambda: policy._hunt_step(snapshot, strategic_hostiles))
            if clear_step is not None:
                policy.last_reason = "clear-descent"
                policy._declare_monster(
                    getattr(policy, "_hunt_step_target", None)
                )
                key = policy._town_producer_entry("_step_toward:departure", lambda: policy._step_toward(snapshot, clear_step), family="departure")
                if key is not None:
                    policy._offer_execution(
                        key, producer="departure",
                        work_id="departure:clear-descent",
                        next_step="departure.clear-descent-blocker",
                        expected_effect="descent-route-cleared",
                    )
                else:
                    policy._offer_execution_no_step(
                        producer="departure",
                        work_id="departure:clear-descent",
                        cause="blocker-step-unavailable",
                    )
                return key
        travel = policy._town_producer_entry("_entrance_travel_key", lambda: policy._entrance_travel_key(snapshot, policy._descent_target_goal), family="departure")
        if travel is not None:
            return travel
        key = policy._town_producer_entry("_step_toward:departure", lambda: policy._step_toward(snapshot, step), family="departure")
        if key is not None:
            policy._offer_execution(
                key, producer="departure",
                work_id=f"departure:descent-route:{policy._descent_target_goal}",
                next_step="departure.approach-descent",
                expected_effect="descent-target-reached",
            )
        else:
            policy._offer_execution_no_step(
                producer="departure", work_id="departure:descent-route",
                cause="descent-step-unavailable",
            )
        return key
    return PASS
