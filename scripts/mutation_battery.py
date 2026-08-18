#!/usr/bin/env python3
"""Run the standing Hengbot mutation experiments without touching the checkout.

The focused regression selection is named in ``DEFAULT_TESTS``. Pass
``--full-suite`` to run normal unittest discovery for every mutation.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

os.environ.setdefault("PYTHONIOENCODING", "utf-8")


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "hengbot"

PUBLIC_TESTS = frozenset(
    {
        "test_policy.HomeOneOperationPerEntryTest.test_public_page_three_withdrawal_posts_one_complete_sender_key",
        "test_policy.HomeOneOperationPerEntryTest.test_derived_withdrawal_uses_uppercase_and_live_page_three_arithmetic",
        "test_policy.HomeOneOperationPerEntryTest.test_descending_withdrawals_share_one_home_knowledge_read",
        "test_policy.HomeOneOperationPerEntryTest.test_derived_withdrawal_waits_when_page_size_was_never_observed",
        "test_policy.ConfirmedLoadoutPublicPathPinTest.test_home_upgrade_invalidates_confirmation_through_choose_key",
        "test_policy.ConfirmedLoadoutPublicPathPinTest.test_fuel_tick_reuses_confirmation_through_choose_key",
        "test_home_entry_capture.HomeEntryCaptureTest.test_gate1_substrate_replays_fixed_digger_arming_and_composed_key",
        "test_policy.TownAndFundraisingPolicyTest.test_recovered_home_entry_charges_an_evaporated_route_claim",
        "test_policy.TownAndFundraisingPolicyTest.test_recovered_home_entry_arms_standing_digger_withdrawal_after_restart",
        "test_policy.TownAndFundraisingPolicyTest.test_queued_digger_withdrawal_blocks_departure_without_home_route",
        "test_policy.TownAndFundraisingPolicyTest.test_failed_digger_withdraw_retries_only_after_fresh_home_observation",
        "test_policy.TownAndFundraisingPolicyTest.test_second_failed_digger_withdrawal_releases_to_visible_fallback",
        "test_policy.TownAndFundraisingPolicyTest.test_second_digger_queue_survives_surface_item_processing_until_post",
        "test_policy.TownAndFundraisingPolicyTest.test_pending_home_digger_is_additional_mining_walk_in_conjunct",
        "test_policy.TownAndFundraisingPolicyTest.test_scavenge_plan_routes_unaddressed_home_digger_latch_and_clears_queue",
        "test_navigation.StairRejectionInvalidationTest.test_interleaved_refusal_probe_releases_older_stair_watch",
        "test_navigation.StairRejectionInvalidationTest.test_quiet_same_turn_stair_watch_has_visible_bounded_probe",
        "test_cli.UniversalPostingContractTest.test_completed_dual_wield_prompt_history_is_not_an_open_owner",
        "test_policy.CombatTest.test_hunt_pack_midpoint_replay_cools_claim_before_cell_guard",
        "test_policy.CombatTest.test_hunt_blink_does_not_restore_the_full_progress_budget",
        "test_policy.PredictiveEscapeTest.test_paralyzer_hunt_closure_is_vetoed_through_choose_key_after_restart",
        "test_policy.PredictiveEscapeTest.test_distant_sleeping_immobile_paralyzer_does_not_preempt_hunt",
        "test_policy.PredictiveEscapeTest.test_paralyzer_ring_invalidates_cached_explore_path_through_choose_key",
        "test_policy.PredictiveEscapeTest.test_awake_mobile_adjacent_paralyzer_walks_away_first",
        "test_policy.PredictiveEscapeTest.test_sleeping_immobile_adjacent_paralyzer_is_never_meleed",
        "test_policy.PredictiveEscapeTest.test_step_composer_refuses_every_owner_entry_into_paralyzer_ring",
        "test_policy.PredictiveEscapeTest.test_adjacent_paralyzer_flee_uses_composer_to_open_closed_door",
        "test_policy.PredictiveEscapeTest.test_paralyzer_flee_scores_against_every_physical_adjacent",
        "test_policy.PredictiveEscapeTest.test_only_paralyzer_retreat_may_cross_a_fully_ringed_veto",
        "test_policy.PredictiveEscapeTest.test_adjacent_orc_fight_is_not_abandoned_for_distant_paralyzer",
        "test_flight_recorder.FlightRecorderTest.test_policy_state_retains_commitment_and_downstairs_and_map_renders",
        "test_policy.HomeOneOperationPerEntryTest.test_captured_restore_prefix_collapse_rerequests_scan_without_discard",
        "test_policy.EquipmentTransactionOwnershipRegressionTest.test_abandoned_deposit_is_preserved_from_every_replanned_transaction",
        "test_home_visit.HomeVisitExecutorTest.test_retention_conflict_is_rejected_at_filing",
        "test_home_visit.HomeVisitExecutorTest.test_semantic_churn_is_a_visible_defect",
        "test_policy.IdleItemDepositTest.test_gate1_sale_retains_the_standing_two_digger_kit",
        "test_policy.IdleItemDepositTest.test_gate1_five_diggers_compose_sales_for_only_the_three_worst",
        "test_policy.HiddenInfoFallbackTest.test_a21_home_device_prevents_affordable_purchase",
        "test_policy.HiddenInfoFallbackTest.test_a21_fresh_home_absence_falls_through_once",
        "test_policy.HiddenInfoFallbackTest.test_shortage_purchase_is_home_first_too",
        "test_policy.HiddenInfoFallbackTest.test_a21_unaffordable_device_composes_surplus_sale_before_stop",
        "test_policy.HiddenInfoFallbackTest.test_a21_unroutable_home_never_rearms_magic_entry_loop",
        "test_policy.HiddenInfoFallbackTest.test_a21_unroutable_home_blocks_before_magic_entry",
        "test_policy.HiddenInfoFallbackTest.test_starving_ration_race_with_home_stock_withdraws_before_buying",
        "test_policy.HiddenInfoFallbackTest.test_unknown_home_device_is_a_mana_food_withdrawal_candidate",
        "test_policy.IdleItemDepositTest.test_five_equal_diggers_are_surplus_for_deposit_but_retained_from_sale",
        "test_policy.TownAndFundraisingPolicyTest.test_two_visible_withdraw_failures_do_not_override_total_stock_target",
        "test_policy.TownAndFundraisingPolicyTest.test_gate1_digger_rebuy_window_stops_after_first_fallback_purchase",
        "test_policy.TownAndFundraisingPolicyTest.test_confirmed_digger_sale_arms_sell_rebuy_churn_defect",
        "test_home_visit.HomeVisitExecutorTest.test_budget_rejection_has_visible_report_and_no_none_crash",
        "test_home_visit.HomeVisitExecutorTest.test_history_is_visit_scoped_and_same_signature_stacks_are_allowed",
        "test_home_visit.HomeVisitExecutorTest.test_calibration_deposit_restore_is_authorized",
        "test_home_visit.HomeVisitCaptureAcceptanceTest.test_ast_ratchet_keeps_optimizer_and_composers_under_executor",
        "test_policy.HomeVisitOwnershipTest.test_new_home_transaction_cannot_reset_completed_home_visit_history",
        "test_policy.HomeVisitOwnershipTest.test_rejected_home_visit_budget_stops_the_real_approach",
        "test_policy.HomeVisitOwnershipTest.test_prepare_operation_budget_exhaustion_is_visible",
        "test_policy.HomeVisitOwnershipTest.test_home_rearm_is_noop_after_visit_budget_exhaustion",
        "test_policy.HomeOneOperationPerEntryTest.test_same_turn_home_leave_does_not_refile_atomic_deposit",
        "test_policy.HomeOneOperationPerEntryTest.test_unobserved_atomic_deposit_is_visibly_abandoned_at_bound",
        "test_home_visit.HomeVisitCaptureAcceptanceTest.test_executor_era_deposit_repost_is_same_turn_unobserved_refile",
    }
)
DEFAULT_TESTS = (
    *sorted(PUBLIC_TESTS),
    "test_warrior_optimization.WarriorOptimizationTest.test_optimizer_input_key_covers_search_and_planner_inputs",
    "test_warrior_optimization.WarriorOptimizationTest.test_optimizer_input_key_ignores_transport_noise_and_catalog_order",
)


@dataclasses.dataclass(frozen=True)
class Replacement:
    relative_path: str
    old: str
    new: str


@dataclasses.dataclass(frozen=True)
class Mutation:
    name: str
    expected_to_bite: bool
    explanation: str
    replacements: tuple[Replacement, ...]


def replacement(path: str, old: str, new: str) -> Replacement:
    return Replacement(path, old, new)


MUTATIONS = (
    Mutation(
        "allow-purchase-without-fresh-home-absence",
        True,
        "Remove the universal fresh-Home evidence gate from purchase composition.",
        (replacement(
            "policy.py",
            "            if not self._purchase_has_fresh_home_absence(snapshot, item):\n",
            "            if False and not self._purchase_has_fresh_home_absence(snapshot, item):\n",
        ),),
    ),
    Mutation(
        "restore-mana-survival-shop-first",
        True,
        "Let the MANA emergency enter the Magic shop before evaluating Home.",
        (replacement(
            "policy.py",
            "        home_needed = not self._home_knowledge_current or home_device is not None\n",
            "        home_needed = home_device is not None and STORE_MAGIC in self._town_store_attempted\n",
        ),),
    ),
    Mutation(
        "disable-mana-emergency-sales",
        True,
        "Remove retention-safe sales as the affordability fallback.",
        (replacement(
            "policy.py",
            "                sale = self._mana_survival_sale_candidate(\n"
            "                    snapshot, store.store_type\n"
            "                )\n",
            "                sale = None\n",
        ),),
    ),
    Mutation(
        "restore-ration-shop-first",
        True,
        "Bypass the universal Home-first check for survival ration purchases.",
        (replacement(
            "policy.py",
            "                    and not self._purchase_has_fresh_home_absence(snapshot, food_item)\n",
            "                    and False and not self._purchase_has_fresh_home_absence(snapshot, food_item)\n",
        ),),
    ),
    Mutation(
        "reject-unknown-home-mana-device",
        True,
        "Restore the false-absence filter for unidentified Home devices.",
        (replacement(
            "policy.py",
            "            if item.is_wand_staff and (not item.known or item.charges > 0)\n",
            "            if item.is_wand_staff and item.known and item.charges > 0\n",
        ),),
    ),
    Mutation(
        "disable-digger-sale-retention",
        True,
        "Allow the standing digger kit into the inscription-bound sale path.",
        (replacement(
            "policy.py",
            "        return better_count < 2\n",
            "        return False\n",
        ),),
    ),
    Mutation(
        "disable-town-sell-rebuy-churn-defect",
        True,
        "Allow a sold item class to be bought back in the same town visit.",
        (replacement(
            "policy.py",
            "            if item.tval in self._town_visit_sale_tvals:\n",
            "            if False and item.tval in self._town_visit_sale_tvals:\n",
        ),),
    ),
    Mutation(
        "omit-inflight-digger-from-common-stock",
        True,
        "Revert the common stock predicate so Gate-1 can post a second fallback buy.",
        (replacement(
            "policy.py",
            "        if (\n"
            "            self._store_buy_inflight is not None\n"
            "            and self._store_buy_inflight[1][1] == TVAL_DIGGING\n"
            "        ):\n"
            "            count += 1\n",
            "",
        ),),
    ),
    Mutation(
        "reset-home-history-on-optimizer-session",
        True,
        "Restore the A6c cooldown reset on every replacement session.",
        (replacement(
            "policy.py",
            "        # _derived_home_visit_request snapshots this session on the next\n",
            "        self._town_store_attempted.pop(STORE_HOME, None)\n"
            "        # _derived_home_visit_request snapshots this session on the next\n",
        ),),
    ),
    Mutation(
        "allow-retained-home-deposit-request",
        True,
        "Permit shelving to override the immutable retention snapshot.",
        (replacement(
            "home_visit.py",
            "            and self.item_identity in self.keep_set\n",
            "            and False and self.item_identity in self.keep_set\n",
        ),),
    ),
    Mutation(
        "disable-home-semantic-churn-defect",
        True,
        "Allow consecutive completed take/put effects to cancel inventory.",
        (replacement(
            "home_visit.py",
            "                and previous[0] + delta == 0\n",
            "                and False and previous[0] + delta == 0\n",
        ),),
    ),
    Mutation(
        "ignore-home-visit-approach-authorization",
        True,
        "Restore the rejected-budget approach fallthrough.",
        (replacement(
            "policy.py",
            "            if not self._ensure_home_visit_request(snapshot):\n",
            "            if False and not self._ensure_home_visit_request(snapshot):\n",
        ),),
    ),
    Mutation(
        "ignore-home-operation-budget-rejection",
        True,
        "Restore the rejected-budget atomic composer fallthrough.",
        (replacement(
            "policy.py",
            "            if visit.request is None or not visit.begin_approach(\n",
            "            if False and (visit.request is None or not visit.begin_approach(\n",
        ), replacement(
            "policy.py",
            "                self._decision_sequence\n            ):\n",
            "                self._decision_sequence\n            )):\n",
        )),
    ),
    Mutation(
        "rearm-home-after-visit-budget-exhaustion",
        True,
        "Permit new Home work to erase the exhausted visit stop.",
        (replacement(
            "policy.py",
            "            and home_visit.attempts_used >= home_visit.attempt_limit\n",
            "            and False\n"
            "            and home_visit.attempts_used >= home_visit.attempt_limit\n",
        ),),
    ),
    Mutation(
        "keep-current-home-observation-after-prefix-collapse",
        True,
        "Restore the captured ESC loop by suppressing the fresh ~9 request.",
        (replacement(
            "policy.py",
            "        if owner_indices and index <= min(owner_indices):\n"
            "            self._invalidate_home_observation()\n",
            "        if False and owner_indices and index <= min(owner_indices):\n"
            "            self._invalidate_home_observation()\n",
        ),),
    ),
    Mutation(
        "close-home-deposit-on-same-turn-page",
        True,
        "Restore the executor-era stale-page report/refile cycle.",
        (replacement(
            "policy.py",
            "            if snapshot.turn > posted_turn:\n",
            "            if snapshot.turn >= posted_turn:\n",
        ),),
    ),
    Mutation(
        "disable-paralyzer-adjacency-veto",
        True,
        "Restore ordinary hunt closure toward paralysis attackers.",
        (replacement(
            "policy.py",
            "        paralyzers = self._refresh_paralyzer_avoidance(\n"
            "            snapshot, physical_hostiles\n"
            "        )\n",
            "        paralyzers = []\n",
        ),),
    ),
    Mutation(
        "trust-flat-free-action-without-source",
        True,
        "Stop failing closed when free-action source state is absent.",
        (replacement(
            "policy.py",
            "        return bool(snapshot.player.ability_sources.get(\"free_action\", ()))\n",
            "        return \"free_action\" in snapshot.player.abilities\n",
        ),),
    ),
    Mutation(
        "retain-stale-paralyzer-ring",
        True,
        "Leave the previous snapshot's paralyzer cells in the shared veto.",
        (replacement(
            "policy.py",
            "        self._engagement_avoid_cells -= (\n"
            "            previous_cells\n"
            "            - self._engagement_owned_avoid_cells\n"
            "            - self._warning_refused_cells\n"
            "        )\n",
            "        self._engagement_avoid_cells -= set()\n",
        ),),
    ),
    Mutation(
        "keep-explore-path-through-paralyzer-ring",
        True,
        "Keep a cached exploration path after its next step enters the ring.",
        (replacement(
            "policy.py",
            "        if any(step in cells for step in self._explore_path):\n"
            "            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)\n",
            "        if False and any(step in cells for step in self._explore_path):\n"
            "            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)\n",
        ),),
    ),
    Mutation(
        "allow-composed-step-into-paralyzer-ring",
        True,
        "Restore owner movement through the no-adjacency ring.",
        (replacement(
            "policy.py",
            "        if step in self._paralyzer_avoid_cells:\n",
            "        if False and step in self._paralyzer_avoid_cells:\n",
        ),),
    ),
    Mutation(
        "exclude-sleeping-paralyzer-from-prevention",
        True,
        "Restore melee against an adjacent sleeping paralysis attacker.",
        (replacement(
            "policy.py",
            "            if (\n"
            "                (knowledge := self._monrace_knowledge.get(monster.race_id))\n",
            "            if (\n"
            "                not monster.asleep\n"
            "                and (knowledge := self._monrace_knowledge.get(monster.race_id))\n",
        ),),
    ),
    Mutation(
        "score-paralyzer-flee-against-paralyzers-only",
        True,
        "Drop other physically adjacent enemies from paralyzer flee scoring.",
        (replacement(
            "policy.py",
            "            step = self._flee_step(snapshot, physical_adjacent)\n",
            "            step = self._flee_step(snapshot, adjacent)\n",
        ),),
    ),
    Mutation(
        "drop-paralyzer-ring-flight-recorder-registration",
        True,
        "Omit the paralyzer ring from recorded policy state.",
        (replacement(
            "flight_recorder.py",
            '        "_paralyzer_avoid_cells",\n',
            "",
        ),),
    ),
    Mutation(
        "disable-fully-ringed-paralyzer-survival-exception",
        True,
        "Prevent paralyzer retreat from crossing a fully ringed veto.",
        (replacement(
            "policy.py",
            "            if not (allow_paralyzer_ring_escape and fully_ringed):\n",
            "            if True:\n",
        ),),
    ),
    Mutation(
        "scan-prompt-shaped-message-history",
        True,
        "Treat a completed dual-wield question in history as an open prompt.",
        (replacement(
            "cli.py",
            "    newest = tuple(messages)[-1] if messages else None\n"
            "    if newest is not None and any(marker in newest for marker in markers):\n"
            "        return newest\n"
            "    return None\n",
            "    for message in reversed(tuple(messages)):\n"
            "        if any(marker in message for marker in markers):\n"
            "            return message\n"
            "    return None\n",
        ),),
    ),
    Mutation(
        "disable-hunt-progress-release",
        True,
        "Restore the unbounded midpoint hunt claim.",
        (replacement(
            "policy.py",
            "                and progress[\"steps\"] >= HUNT_RANGE\n",
            "                and False and progress[\"steps\"] >= HUNT_RANGE\n",
        ),),
    ),
    Mutation(
        "forget-hunt-identity-while-absent",
        True,
        "Restore the blinking-target full-budget reset.",
        (replacement(
            "policy.py",
            "        if player.hp_ratio < HUNT_HP_RATIO or not hostiles:\n",
            "        observed_indexes = {monster.index for monster in snapshot.visible_monsters}\n"
            "        for index in tuple(self._hunt_target_identities):\n"
            "            if index not in observed_indexes:\n"
            "                self._hunt_target_identities.pop(index, None)\n"
            "        if player.hp_ratio < HUNT_HP_RATIO or not hostiles:\n",
        ),),
    ),
    Mutation(
        "rearm-only-in-mine-mode",
        True,
        "Restore the circular mode gate that starved Home digger arming.",
        (replacement(
            "policy.py",
            "            store is None\n"
            "            or store.store_type != STORE_HOME\n"
            "            or self._digging_tool_count(snapshot) >= 2\n"
            "        ):\n",
            "            store is None\n"
            "            or store.store_type != STORE_HOME\n"
            "            or self._digging_tool_count(snapshot) >= 2\n"
            "            or self._fundraising_mode == \"scavenge\"\n"
            "        ):\n",
        ),),
    ),
    Mutation(
        "drop-recovered-home-digger-binding",
        True,
        "Remove the recovered open-Home production binding.",
        (replacement(
            "policy.py",
            "            elif (\n"
            "                not self._calibration_active()\n"
            "                and self._home_atomic_deposit_pending is None\n"
            "                and self._equipment_transaction_session is None\n"
            "                and (\n"
            "                    standing_digger := self._queue_standing_home_digger(snapshot)\n"
            "                ) is not None\n"
            "            ):\n"
            "                # The open page is authoritative Home-stock evidence even when\n"
            "                # entry ownership was recovered after a restart or lagged post.\n"
            "                # Selection is bound here; the outside decision composes it.\n"
            "                key = standing_digger\n",
            "",
        ),),
    ),
    Mutation(
        "drop-evaporated-home-claim-charge",
        True,
        "Stop cooling an unfulfilled recovered Home route for the town visit.",
        (replacement(
            "policy.py",
            "                self._town_store_attempted[STORE_HOME] = snapshot.turn\n"
            "                self.last_reason = \"home:route-claim-unfulfilled\"\n",
            "                self.last_reason = \"home:route-claim-unfulfilled\"\n",
        ),),
    ),
    Mutation(
        "carried-half-only",
        True,
        "Build the optimizer input key from carried items only.",
        (replacement(
            "warrior_optimization.py",
            "(optimizer_item_projection(item) for item in items),",
            "(optimizer_item_projection(item) for item in items if item.origin != \"home\"),",
        ),),
    ),
    Mutation(
        "fuel-in-projection",
        True,
        "Include volatile fuel in the optimizer input projection.",
        (replacement(
            "equipment_optimizer.py",
            "        _catalog_signature(item),\n        item.weight,",
            "        _catalog_signature(item),\n        getattr(item, \"fuel\", None),\n        item.weight,",
        ),),
    ),
    Mutation(
        "guess-home-page-size",
        True,
        "Guess 52 columns when no Home page size was observed.",
        (replacement(
            "policy.py",
            "        if not self._home_page_size:\n            self.last_reason = \"home:await-page-size\"\n            return None\n",
            "        if not self._home_page_size:\n            self._home_page_size = 52  # mutant guesses geometry\n",
        ),),
    ),
    Mutation(
        "lowercase-past-z",
        True,
        "Continue lowercase address arithmetic past z.",
        (replacement(
            "policy.py",
            "            if page_pos < 26\n",
            "            if page_pos < 52\n",
        ),),
    ),
    Mutation(
        "invalidate-descending-frontier",
        True,
        "Invalidate the whole knowledge read after the first withdrawal.",
        (replacement(
            "policy.py",
            "        self._home_knowledge_valid_before = index\n",
            "        self._home_knowledge_current = False  # mutant loses descending batch\n",
        ),),
    ),
    Mutation(
        "withdraw-gate-depends-on-home-route",
        True,
        "Restore the departure race by making the pending take conditional on Home routing.",
        (replacement(
            "policy.py",
            "            \"home_atomic_withdraw_clear\": (\n"
            "                self._home_atomic_withdraw_pending is None\n"
            "            ),\n",
            "            \"home_atomic_withdraw_clear\": (\n"
            "                not home_required or self._home_atomic_withdraw_pending is None\n"
            "            ),\n",
        ),),
    ),
    Mutation(
        "drop-queued-digger-departure-leaf",
        True,
        "Remove the state-based queued digger departure premise.",
        (replacement(
            "policy.py",
            "            \"digger_withdrawal_resolved\": (\n"
            "                not self._home_digger_withdraw_pending\n"
            "                or self._digger_fallback_bought_this_visit\n"
            "            ),\n",
            "",
        ),),
    ),
    Mutation(
        "keep-stair-watch-across-refusal-probe",
        True,
        "Retain the older stair watch across the identity-breaking probe.",
        (replacement(
            "policy.py",
            "                if self._pending_stair_command is not None:\n"
            "                    self._pending_stair_command = None\n"
            "                    self._owner_expectations.release(\"stair-command\")\n",
            "",
        ),),
    ),
    Mutation(
        "defer-first-failed-digger-address",
        True,
        "Consume the first failed take instead of requiring a fresh Home observation.",
        (replacement(
            "policy.py",
            "                retry_digger = (\n"
            "                    withdrawn.is_digging_tool\n"
            "                    and self._digger_home_withdraw_failures < 1\n"
            "                )\n",
            "                retry_digger = False\n",
        ),),
    ),
    Mutation(
        "drop-standing-digger-prepost-attribution",
        True,
        "Clear the queued attribution bit set by standing Home digger selection.",
        (replacement(
            "policy.py",
            "        self._home_withdrawal_queued = True\n"
            "        self.last_reason = \"home:queue-digging-tool-withdraw\"\n",
            "        self._home_withdrawal_queued = False\n"
            "        self.last_reason = \"home:queue-digging-tool-withdraw\"\n",
        ),),
    ),
    Mutation(
        "move-digger-entry-guard-after-mining-exemption",
        True,
        "Restore the mining walk-in early return ahead of the pending withdrawal guard.",
        (replacement(
            "policy.py",
            "        if (\n"
            "            self._home_digger_withdraw_pending\n"
            "            and not self._digger_fallback_bought_this_visit\n"
            "        ):\n"
            "            self._town_blocked_reason = \"home-digger-withdraw-pending\"\n"
            "            return False\n",
            "",
        ),),
    ),
    Mutation(
        "route-only-addressed-digger-withdrawal",
        True,
        "Require the transient Home item address before routing the durable latch.",
        (replacement(
            "policy.py",
            "        if snapshot.in_town and self._home_digger_withdraw_pending:\n",
            "        if (\n"
            "            snapshot.in_town\n"
            "            and self._home_digger_withdraw_pending\n"
            "            and self._home_pending_item is not None\n"
            "        ):\n",
        ),),
    ),
    Mutation(
        "replan-abandoned-pack-deposit",
        True,
        "Restore A13 by allowing a failed deposit back into every fresh plan.",
        (replacement(
            "policy.py",
            "                or item.id in self._equipment_transaction_failed_items\n",
            "",
        ),),
    ),
    Mutation(
        "remove-quiet-stair-observation-bound",
        True,
        "Keep quiet accepted stair observations in the empty-key wait forever.",
        (replacement(
            "policy.py",
            "            if self._stair_observation_waits >= STAIR_OBSERVATION_WAIT_LIMIT:\n",
            "            if False and self._stair_observation_waits >= STAIR_OBSERVATION_WAIT_LIMIT:\n",
        ),),
    ),
)


def repo_fingerprint() -> str:
    """Fingerprint checkout state without writing into it."""
    proc = subprocess.run(
        # The supervisor-owned JSONL recorder rotates untracked files while
        # this read-only battery runs.  Track checkout mutations through Git's
        # tracked index/worktree state; package bytes are hashed separately.
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=no"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    digest = hashlib.sha256(proc.stdout)
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def apply_mutation(package: Path, mutation: Mutation) -> tuple[bool, str | None]:
    for edit in mutation.replacements:
        target = package / edit.relative_path
        text = target.read_text(encoding="utf-8")
        count = text.count(edit.old)
        if count != 1:
            return False, f"anchor in {edit.relative_path} matched {count} times (expected 1)"
        target.write_text(text.replace(edit.old, edit.new, 1), encoding="utf-8")
    return True, None


FAILURE_RE = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)$", re.MULTILINE)
RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
ASSERTION_RE = re.compile(r"^(?:AssertionError|[A-Za-z_.]+Error): (.+)$", re.MULTILINE)


def run_tests(package_parent: Path, full_suite: bool) -> dict:
    if full_suite:
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    else:
        command = [
            sys.executable, "-m", "unittest", "discover", "-s", "tests",
            *sum((["-k", name.rsplit(".", 1)[-1]] for name in DEFAULT_TESTS), []),
        ]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(package_parent), *(old_pythonpath.split(os.pathsep) if old_pythonpath else [])]
    )
    proc = subprocess.run(
        command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
    )
    output = proc.stdout
    failures = []
    for match in FAILURE_RE.finditer(output):
        _method, container = match.groups()
        failures.append(container)
    ran = RAN_RE.search(output)
    assertion = ASSERTION_RE.search(output)
    return {
        "command": command,
        "tests_run": int(ran.group(1)) if ran else None,
        "failures": failures,
        "returncode": proc.returncode,
        "first_assertion": assertion.group(1) if assertion else None,
        "output": output,
    }


def execute(mutation: Mutation, full_suite: bool) -> dict:
    result = {
        "name": mutation.name,
        "expected_to_bite": mutation.expected_to_bite,
        "explanation": mutation.explanation,
        "applied": False,
        "tests_run": 0,
        "failures": [],
        "public_path_failure": False,
        "first_assertion": None,
        "expectation_met": False,
    }
    with tempfile.TemporaryDirectory(prefix="hengbot-mutation-") as directory:
        package_parent = Path(directory)
        copied_package = package_parent / "hengbot"
        shutil.copytree(PACKAGE, copied_package)
        applied, error = apply_mutation(copied_package, mutation)
        result["applied"] = applied
        if not applied:
            result["apply_error"] = error
            return result
        test_result = run_tests(package_parent, full_suite)
        result.update({key: test_result[key] for key in (
            "tests_run", "failures", "returncode", "first_assertion"
        )})
        result["public_path_failure"] = any(
            failure in PUBLIC_TESTS for failure in test_result["failures"]
        )
        bit = result["public_path_failure"]
        result["expectation_met"] = bit == mutation.expected_to_bite
    return result


def compact(value: object, width: int) -> str:
    text = "-" if value in (None, "", []) else str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def print_table(results: list[dict]) -> None:
    headers = ("mutation", "expect", "applied", "tests", "fail", "public", "result", "first assertion")
    rows = []
    for item in results:
        rows.append((
            item["name"], "bite" if item["expected_to_bite"] else "no-bite",
            "yes" if item["applied"] else "no", item["tests_run"],
            len(item["failures"]), "yes" if item["public_path_failure"] else "no",
            "PASS" if item["expectation_met"] else "FAIL",
            item.get("apply_error") or item["first_assertion"],
        ))
    widths = [max(len(headers[i]), *(len(compact(row[i], 72)) for row in rows)) for i in range(len(headers))]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(compact(row[i], 72).ljust(widths[i]) for i in range(len(headers))))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=[item.name for item in MUTATIONS])
    parser.add_argument("--full-suite", action="store_true")
    args = parser.parse_args()
    selected = [item for item in MUTATIONS if args.only in (None, item.name)]
    before = repo_fingerprint()
    results = [execute(item, args.full_suite) for item in selected]
    after = repo_fingerprint()
    tree_untouched = before == after
    if not tree_untouched:
        for item in results:
            item["expectation_met"] = False
            item["repo_tree_error"] = "repository fingerprint changed during the run"
    print_table(results)
    summary = {
        "runtime": sys.executable,
        "selection": "full-suite" if args.full_suite else list(DEFAULT_TESTS),
        "repo_tree_untouched": tree_untouched,
        "results": results,
    }
    print("\nJSON_SUMMARY=" + json.dumps(summary, sort_keys=True))
    return 0 if tree_untouched and all(item["expectation_met"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
