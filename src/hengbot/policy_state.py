"""One idempotent policy upgrade shared by restore, unpickle and decisions."""
from __future__ import annotations
from collections import Counter
from dataclasses import replace
from copy import deepcopy
from hengbot.policy_types import OwnerProgressCore
from hengbot.retired_values import is_retired

# Strip-calibration attributes retained by the equipped C-sheet observation.
_RETAINED_CALIBRATION_NAMES = frozenset({
    "_calibration_dump_prepared", "_calibration_dump_pending",
    "_calibration_dump_response", "_calibration_unavailable_reason",
    "_calibration_rejection", "_calibration_session_id",
})


def retire_strip_calibration_state(restored) -> None:
    """Drop every retired strip-calibration fact from an old checkpoint.

    The strip phases (deposit, takeoff, naked capture, re-equip, supply
    restore, redress) no longer exist.  Their attributes, their batch Home
    withdrawal, their Home visit kind and their claim family are removed, so
    the restored policy is an ordinary session with no calibration phase.
    """
    state = restored.__dict__
    # Before the markers go: a strip or restore session still open in the
    # checkpoint must never continue (its takeoffs would strip again).
    _cancel_calibration_transaction(state)
    for name in tuple(state):
        if name.startswith("_calibration_") and name not in _RETAINED_CALIBRATION_NAMES:
            del state[name]
    pending = state.get("_home_atomic_withdraw_pending")
    if pending is not None and len(pending) == 5:
        # Only the calibration restore composed a same-page batch take.
        state["_home_atomic_withdraw_pending"] = None
        state["_home_atomic_withdraw_procurement_class"] = None
        state["_home_atomic_withdraw_move_identity"] = None
        state["_home_atomic_withdraw_posted_turn"] = None
        state["_home_atomic_withdraw_index"] = None
        state["_home_entry_operation_posted"] = False
    visit = state.get("_home_visit")
    if visit is not None:
        _retire_home_visit_kind(visit)
    register = state.get("_claim_register")
    if register is not None:
        _retire_claim_family(register)
    claim = state.get("decision_claim")
    if claim is not None and is_retired(getattr(claim, "owner", None)):
        state["decision_claim"] = None
    registry = state.get("_owner_expectations")
    if registry is not None:
        pending_owners = registry.__dict__.get("_pending")
        if isinstance(pending_owners, dict):
            pending_owners.pop("calibration", None)
        pops = registry.__dict__.get("_pops")
        if isinstance(pops, list):
            pops[:] = [pop for pop in pops if pop[0] != "calibration"]


_CALIBRATION_ACTION_PREFIXES = ("calibration:", "calibration-restore:")


def _cancel_calibration_transaction(state) -> None:
    """Cancel an equipment session owned by the retired strip calibration.

    Identified as the base code did (``_calibration_session_owned``: the
    session's target loadout is the calibration session target) or by the
    strip/restore action ids it planned.  Gear it already took off stays in
    the pack (or Home), where the ordinary optimizer re-equips it.
    """
    session = state.get("_equipment_transaction_session")
    if session is None:
        return
    target = state.get("_calibration_session_target")
    actions = getattr(getattr(session, "plan", None), "actions", ()) or ()
    owned = (
        (target is not None
         and getattr(session, "target_loadout_id", None) == target)
        or any(str(getattr(action, "item_id", "")).startswith(
            _CALIBRATION_ACTION_PREFIXES) for action in actions)
    )
    if not owned:
        return
    state["_equipment_transaction_session"] = None
    state["_equipment_transaction_prepared_key"] = None
    state["_equipment_transaction_prepared_catalog_update"] = None
    state["_equipment_transaction_restoring"] = False
    state["_equipment_transaction_restore_remainder"] = ()
    delegations = state.get("_execution_delegations")
    if isinstance(delegations, list):
        delegations[:] = [
            record for record in delegations
            if getattr(record, "parent_family", None) != "calibration"
        ]


def _invalidate_foreign_calibration(state) -> None:
    """Drop constants that this process did not observe (schema/session).

    The disk loader accepts only this session's equipped (schema 2) record;
    a restored or upgraded policy obeys the same boundary, and the optimizer
    and confirmed-loadout caches derived from dropped constants go with it.
    Tests that replay a recorded process inject its record explicitly
    (tests/extraction_calibration.py).
    """
    calibration = state.get("_character_calibration")
    if calibration is None:
        return
    if (getattr(calibration, "schema_version", 1) == 2
            and getattr(calibration, "session_id", "")
            == state.get("_calibration_session_id")):
        return
    state["_character_calibration"] = None
    state["_character_calibration_loaded"] = False
    state["_equipment_optimization_signature"] = None
    state["_equipment_optimizer_input_key"] = None
    state["_confirmed_loadout"] = None
    state["_confirmed_loadout_loaded"] = False


def _retire_home_visit_kind(visit) -> None:
    state = visit.__dict__
    request = state.get("request")
    report = state.get("report")
    if (request is not None and is_retired(request.kind)) or (
        report is not None and is_retired(report.request.kind)
    ):
        # The restore visit is abandoned, not completed: no effect is
        # reported to any requester and the executor is idle again.
        state["request"] = None
        state["report"] = None
        state["fresh_evidence"] = None
        state["operation"] = None
        state["operation_generation"] = None
        state["visit_effect_observed"] = False
        state["context_token"] = None
        if isinstance(state.get("operation_history"), list):
            state["operation_history"].clear()
        if isinstance(state.get("operation_reports"), list):
            state["operation_reports"].clear()
        from hengbot.home_visit import HomeVisitState
        state["state"] = HomeVisitState.IDLE
    queued = state.get("queued")
    if isinstance(queued, list):
        queued[:] = [item for item in queued if not is_retired(item.kind)]
    previous = state.get("previous_completed_delta")
    if previous is not None and is_retired(previous[2]):
        # Only a standing-digger withdrawal is read from this record.
        state["previous_completed_delta"] = None


def _retire_claim_family(register) -> None:
    state = register.__dict__
    for name in ("_claim", "_closing"):
        claim = state.get(name)
        if claim is not None and is_retired(claim.owner):
            state[name] = None
    for name in ("_suspended", "_bars", "_ended"):
        values = state.get(name)
        if isinstance(values, list):
            values[:] = [value for value in values if not is_retired(value.owner)]


def normalize_policy_state(restored, *, restart=False):
    """Upgrade ``restored`` in place to the current policy state version.

    Idempotent.  A current-version policy returns at once, so decisions and
    observations may call this every time; a restored checkpoint
    (``restart=True``) or an older pickle runs the full upgrade.  The upgrade
    never raises on retired strip-calibration state: it drops it, so old
    checkpoints and recordings keep deciding as an ordinary session without a
    calibration phase.  Physical strip debt is a startup question answered
    once from the persisted calibration file (``cli``), never here.
    """
    if not restart and restored.__dict__.get("_policy_state_version") == 3:
        return restored
    retire_strip_calibration_state(restored)
    if restart:
        # A posted dump request belongs to the process that posted it; a
        # restored policy waits for its own next periodic request.
        restored._calibration_dump_pending = None
        restored._calibration_dump_prepared = None
        restored._calibration_dump_response = None
    if restart or not restored.__dict__.get("_calibration_session_id"):
        # A restored or upgraded policy belongs to this process's session.
        from hengbot.policy_calibration import process_calibration_session_id
        restored._calibration_session_id = process_calibration_session_id()
    _invalidate_foreign_calibration(restored.__dict__)
    token_was_present = "_home_knowledge_scan_epoch" in restored.__dict__
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
    restored.__dict__.setdefault("_town_visit_sale_identify_charges", None)
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
    # (floor, loss, deadline turn); a carry without its deadline is dropped.
    carry = restored.__dict__.setdefault("_blind_cure_escape_carry", None)
    if carry is not None and len(carry) != 3:
        restored.__dict__["_blind_cure_escape_carry"] = None
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
    # A pre-executor checkpoint: the Home visit executor is rebuilt lazily on
    # its first operation, which reports restart-refile-required instead of
    # inheriting an unknown posted visit (every reader guards None).
    restored.__dict__.setdefault("_home_visit", None)
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
    # Every remaining attribute of a fresh policy, last: the explicit legacy
    # defaults above win (for example ``_town_turn_arbiter=None`` keeps a
    # pre-arbiter checkpoint's ``_store_visit`` on its migration path, where
    # a fresh arbiter would resurrect it after an explicit close).  Construct
    # defaults separately; never rerun __init__ on restored physical state.
    # Missing mutable values are independent, not shared across policies.
    defaults = type(restored)(monrace_knowledge={})
    for name, value in defaults.__dict__.items():
        if name not in restored.__dict__:
            restored.__dict__[name] = deepcopy(value)
    restored._policy_state_version = 3
    return restored
