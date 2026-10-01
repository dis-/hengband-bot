"""One idempotent policy upgrade shared by restore, unpickle and decisions."""
from __future__ import annotations
from collections import Counter
from dataclasses import replace
from copy import deepcopy
from hengbot.policy_types import OwnerProgressCore


def normalize_policy_state(restored):
    from hengbot.policy_calibration import refuse_legacy_calibration_debt
    refuse_legacy_calibration_debt(restored.__dict__, restored.__dict__.get("_character_calibration_path"))
    if restored.__dict__.get("_policy_state_version") == 2:
        return restored
    token_was_present = "_home_knowledge_scan_epoch" in restored.__dict__
    # Construct defaults separately; never rerun __init__ on restored physical
    # state. Missing mutable values are independent, not shared across policies.
    defaults = type(restored)(monrace_knowledge={})
    for name, value in defaults.__dict__.items():
        if name not in restored.__dict__:
            restored.__dict__[name] = deepcopy(value)
    restored.__dict__.setdefault("_remembered_grid_sources", {})
    restored.__dict__.setdefault("_remembered_grid_signatures", {})
    restored.__dict__.setdefault("_threat_prediction_memo", {})
    restored.__dict__.setdefault("_map_predicate_snapshot", None)
    restored.__dict__.setdefault("_decision_input_snapshot", None)
    restored.__dict__.setdefault("_town_fact_snapshot", None)
    restored.__dict__.setdefault("_equipment_mutation_counted_board", None)
    # Checkpoints created before recovery pickup observation existed must be
    # upgraded explicitly; trajectory replay is evidence and may not hide a
    # missing attribute behind a broad exception.
    restored.__dict__.setdefault("_quest_strategy_recovery_claims", {})
    restored.__dict__.setdefault("_quest_strategy_recovery_pickup_prepared", None)
    restored.__dict__.setdefault("_quest_strategy_recovery_pickup_posted", None)
    restored.__dict__.setdefault("_q2_blue_recovery_perceived", set())
    restored.__dict__.setdefault("_town_unidentifiable_carried_sigs", set())
    restored.__dict__.setdefault("_town_visit_purchase_quantities", {})
    restored.__dict__.setdefault("_crossarea_fundraising_enforced", False)
    restored.__dict__.setdefault("_fundraising_run_purpose", None)
    restored.__dict__.setdefault("_fundraising_purpose_record", None)
    restored.__dict__.setdefault("_fundraising_runs_started", None)
    restored.__dict__.setdefault("_fundraising_affordable_food_seen", False)
    # Fundraising set-end now runs on every town decision.  Older captures
    # predate the identify-staff mining-plan flag; False preserves their
    # former terminal-transition behavior.
    restored.__dict__.setdefault("_identify_staff_mining_plan", False)
    # Older captures predate the recall-stockout time-pass flag; False keeps
    # their former set-end behavior (no stockout exemption).
    restored.__dict__.setdefault("_recall_stockout_mining_plan", False)
    # Older captures predate the detected-threat rest tiering record; None is
    # the "no assessment yet" value it is rewritten from on every rest check.
    restored.__dict__.setdefault("_esp_threat_assessment", None)
    # Older captures predate the anticipatory retreat's committed goal; None is
    # "no episode in progress", the value a fresh preparation writes.
    restored.__dict__.setdefault("_detected_threat_route", None)
    # No committed detected-threat hunt existed before the owner was added.
    restored.__dict__.setdefault("_esp_threat_hunt", None)
    restored.__dict__.setdefault("_esp_threat_hunt_end", None)
    restored.__dict__.setdefault("_staged_prompt_chain", None)
    # Equipment departure can now consult a calibration deferral even when a
    # legacy checkpoint reaches the calibration-required optimizer return.
    restored.__dict__.setdefault("_calibration_deferral_cause", None)
    restored.__dict__.setdefault("_calibration_deferral_reason", None)
    restored.__dict__.setdefault("_prompt_gated_posting", True)
    restored.__dict__.setdefault("_town_restock_waited_turns", 0)
    restored.__dict__.setdefault("_town_restock_last_wait_turn", None)
    restored.__dict__.setdefault("_home_latch_active", None)
    restored.__dict__.setdefault("_home_latch_history", [])
    restored.__dict__.setdefault("_home_gate_telemetry", {})
    restored.__dict__.setdefault("_town_visit_epoch", None)
    restored.__dict__.setdefault("_town_order_operation", None)
    restored.__dict__.setdefault("_town_order_expected_observation", None)
    restored.__dict__.setdefault("_home_observed_addresses", {})
    # Older captures predate the read/cancel class bound; False is "no recall
    # cancelled as unready this visit", what a fresh visit starts with.
    restored.__dict__.setdefault("_town_visit_unready_recall_cancelled", False)
    restored.__dict__.setdefault("_safety_deferred_loot", set())
    restored.__dict__.setdefault("_loot_safety_rearmed", set())
    restored.__dict__.setdefault("_home_knowledge_scan_epoch", None)
    if not token_was_present:
        restored.__dict__["_home_knowledge_scan_inflight"] = False
    restored.__dict__.setdefault("_equipment_fresh_search_target_ids", frozenset())
    pending_deposit = restored.__dict__.get("_home_atomic_deposit_pending")
    if (
        pending_deposit is not None
        and len(pending_deposit) == 4
        and isinstance(pending_deposit[0], tuple)
        and len(pending_deposit[0]) == 3
        and isinstance(pending_deposit[0][0], str)
    ):
        signature, count_before, posted_turn, unchanged_pages = pending_deposit
        restored._home_atomic_deposit_pending = (
            ((signature, count_before, 1),),
            None,
            posted_turn,
            unchanged_pages,
        )
    latches = restored.__dict__.get("_cross_decision_latches", {})
    town_block = latches.get("_town_blocked_reason")
    # Permanent values added after a checkpoint was pickled (the second is
    # the guardian-bounce terminal, guardian-recall-pingpong-r3).
    for permanent in ("restock-wait-exhausted", "guardian-bounce-no-alternate"):
        if (
            town_block is not None
            and permanent not in town_block.permanent_values
        ):
            town_block = replace(
                town_block,
                permanent_values=(*town_block.permanent_values, permanent),
            )
            latches["_town_blocked_reason"] = town_block
    # Checkpoints pickled before the S1 claim register carry neither the
    # register nor the recorded claim.  A fresh register is the honest value:
    # the restored policy has declared nothing yet, and its first decision
    # opens claim 1 exactly as a fresh process would.
    # ``town_arbiter`` imports this module, and the register imports the
    # arbiter's families, so the import is local to break that cycle.
    from hengbot.claim_register import ClaimRegister

    restored.__dict__.setdefault("_claim_register", ClaimRegister())
    restored.__dict__.setdefault("decision_claim", None)
    # S2a.1: the per-decision goal slots (reset at every ``choose_key`` entry
    # anyway), the register's pending closing, and the expectation
    # registry's record of why it popped an owner.  Absent means "nothing
    # recorded yet", which is exactly what a fresh process holds.
    restored.__dict__.setdefault("_decision_goal", None)
    restored.__dict__.setdefault("_decision_expectation", None)
    # S2b.1 round 2 (rev 10.1 item 9): the per-decision trigger slot, reset
    # at every ``choose_key`` entry like the two above.
    restored.__dict__.setdefault("_decision_triggers", None)
    # S2b.2: the per-decision record of the rungs a bar skipped (reset at
    # every ``choose_key`` entry), and the switch that lets a bar skip one --
    # off, as it is in every checkpoint this change can meet.
    restored.__dict__.setdefault("_decision_bar_skips", None)
    restored.__dict__.setdefault("_claim_bar_enforced", False)
    restored.__dict__.setdefault("_town_claim_bar_enforced", False)
    restored.__dict__.setdefault("_hunt_step_target", None)
    # Rev 9.2 (S): a checkpoint taken before the shadow existed does not know
    # which trigger its running return began with; unknown is not survival.
    restored.__dict__.setdefault("_survival_return_trigger", None)
    # Round 4 (F3): a capture is per call; none is ever restored.
    restored.__dict__.pop("_claim_target_capture", None)
    register = restored.__dict__.get("_claim_register")
    if register is not None:
        register.__dict__.setdefault("_closing", None)
        # S2b.1 (design rev 10.1 item 5): a checkpoint pickled before the
        # suspended stack held no suspended claim; an empty stack is exact.
        register.__dict__.setdefault("_suspended", [])
        register.__dict__.setdefault("_suspended_closings", [])
        # S2b.2: a checkpoint pickled before the bar table held no bar and
        # no pending ending; empty is exact.
        register.__dict__.setdefault("_bars", [])
        register.__dict__.setdefault("_ended", [])
    restored.__dict__.setdefault("_town_turn_arbiter", None)
    restored.__dict__.setdefault("_town_suppression_claim_stores", set())
    ledger = restored.__dict__.get("_town_visit_ledger")
    if ledger is not None:
        ledger.__dict__.setdefault("blocked_store_work_signatures", {})
        ledger.__dict__.setdefault("rearmed_work_signatures", set())
    # Older checkpoints can retain the two pre-ARB restocked-*-unreachable
    # values.  Normalize them at the compatibility boundary so restored work
    # follows the surviving canonical release path without keeping either
    # orphaned name in live clearing sets.
    if restored.__dict__.get("_town_blocked_reason_value") in {
        "restocked-food-store-unreachable",
        "restocked-recall-store-unreachable",
    }:
        restored.__dict__["_town_blocked_reason_value"] = (
            "restock-store-unreachable"
        )
    # Older captures predate the split of the deferred-loot set by cause.  An
    # empty pair reproduces their former behavior exactly: nothing is treated
    # as ledger-expired, so the calm return hands out no second budget.
    restored.__dict__.setdefault("_nav_ledger_deferred_loot", set())
    restored.__dict__.setdefault("_loot_ledger_rearmed", set())
    restored.__dict__.setdefault("_dark_goal_counts", Counter())
    restored.__dict__.setdefault("_dark_route", [])
    restored.__dict__.setdefault("_dark_route_goal", None)
    restored.__dict__.setdefault("_dark_route_expected", None)
    restored.__dict__.setdefault("_equipment_atomic_withdraw_leave_count", 0)
    restored.__dict__.setdefault(
        "_remembered_marked_t",
        set(restored.__dict__.get("_remembered_known_t", set())),
    )
    registry = restored.__dict__.get("_owner_expectations")
    if registry is not None:
        registry.__dict__.setdefault("_pops", [])
        for owner, pending in tuple(registry._pending.items()):
            core = pending.progress_core
            if not hasattr(core, "decision_sequence"):
                upgraded = OwnerProgressCore(
                    floor=core.floor,
                    position=core.position,
                    store_type=getattr(core, "store_type", None),
                    turn=getattr(core, "turn", 0),
                    decision_sequence=0,
                    hp=getattr(core, "hp", 0),
                    recalling=getattr(core, "recalling", False),
                    gold=core.gold,
                    experience=core.experience,
                    inventory=core.inventory,
                    equipment=core.equipment,
                )
                registry._pending[owner] = replace(
                    pending, progress_core=upgraded
                )
    restored._policy_state_version = 2
    return restored
