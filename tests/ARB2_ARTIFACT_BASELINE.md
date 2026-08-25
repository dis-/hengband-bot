# ARB-2 artifact-dependent test baseline

The former standing baseline of 13 failing test identities is superseded by a
standing baseline of zero failing identities plus the following skips.  These
tests require incident artifacts that are not part of the repository:

- `HomeErrandExecutorTest.test_all_three_captured_entry_exit_loops_are_bounded_by_executor`: `evidence/evidence-home-target-unobserved-loop.jsonl`, `evidence/evidence-home-yield-loop-20260813.jsonl`, and `evidence/evidence-q34-home-reenter-loop.jsonl`.
- `HomeVisitCaptureAcceptanceTest.test_takeput_capture_becomes_one_owned_operation_and_churn_defect`: `evidence/evidence-takeput-oscillation-20260817-2340.jsonl`.
- `HomeVisitCaptureAcceptanceTest.test_executor_era_deposit_repost_is_same_turn_unobserved_refile`: `evidence/evidence-executor-era-stops-20260818-03.jsonl`.
- `HomeVisitCaptureAcceptanceTest.test_door_bounce_capture_collapses_to_report_and_durable_budget`: `incident-captures/20260818-001502-loop-detected/decision-tail.jsonl`.
- `HomeVisitCaptureAcceptanceTest.test_whole_file_home_approach_ratchet_and_evasion_controls`: its capture path declared at the call site.
- `ShopOneShotTest.test_live_capture_name_only_sale_tag_composes_instead_of_reinscribing`: `evidence/evidence-sale-inflight-lines.jsonl`.
- `WorldMapKeyHygieneTest.test_frozen_capture_characterizes_owner_key_and_refusal_counts`: `evidence/evidence-entertown-decisions.jsonl`.
- `UnenterableExploreGoalTest.test_real_west_pocket_replay_retires_goal_and_plans_elsewhere`: destroyed west-pocket source capture.
- `NavigationInvariantTest.test_real_exploration_giveup_relocates_to_western_window_edge`: destroyed exploration-giveup source capture.
- `NavigationInvariantTest.test_window_edge_replay_reaches_new_coverage_and_resets_stall`: destroyed exploration-giveup source capture.

`HomeKnowledgeScanTest.test_stalled_capture_requests_home_knowledge_and_completes`
retains its executable synthetic assertions when its historical capture is
absent.  Its posted-key confirmation is the complete `~9\x1b\x1b` macro.

## Unreplayable capture coverage mapping

The decision-only captures cannot be replayed through `choose_key`; these
executable pins cover their mechanism families:

- `incident-alchemist-repetition-20260823.jsonl` -> `BlockedPurchaseNamespaceAcceptanceTest.test_pin_vacuity_classifier_families_match_need_families` and `BlockedPurchaseNamespaceAcceptanceTest.test_pin_vacuity_supplier_router_and_repetition_handler_share_gate`.
- `incident-restock-rest-burn-window-20260825.jsonl.gz` -> `TownRestockStallTrajectoryTest.test_incident_window_binds_entry_overwrite_and_rest_burn`, `TownRestockStallTrajectoryTest.test_stall_15_affordable_alchemist_stock_never_arms_wait`, and `TownRestockStallTrajectoryTest.test_productive_gap_charges_only_one_restock_rest` (the D1/D2/D3 trajectory and stall-15 family).
- `incident-equipment-abandon-loop-20260822.jsonl` -> `EquipmentTransactionOwnershipRegressionTest.test_foreign_visit_is_closed_and_home_route_attempt_is_bounded` and `EquipmentTransactionOwnershipRegressionTest.test_abandoned_deposit_is_preserved_from_every_replanned_transaction`.
- `incident-calibration-entry-await-20260823.jsonl` -> `TownErrandPlanTest.test_calibration_home_completed_entries_block_at_fifty_four` and `TownErrandPlanTest.test_calibration_home_approach_bound_is_fifty_four`.
- `incident-launcher-repetition-20260823.jsonl` -> `TownCycleDetectorTest.test_repetition_block_completes_departure_recall_purchase` and `TownTurnArbiterAcceptanceTest.test_pin_vacuity_postlevel_public_choose_key_consumes_retirement_budget` (launcher/postlevel repetition family).
- `incident-magic-abandon-cycle-20260823.jsonl` -> `TownCycleDetectorTest.test_measured_outside_repetition_releases_wrong_store_visit` and `BlockedPurchaseNamespaceAcceptanceTest.test_pin_vacuity_supplier_router_and_repetition_handler_share_gate` (magic/repetition family).
- `incident-darkread-guard-miss-20260824.jsonl.gz` -> `DarkwalkIncidentTest.test_frozen_decisions_pin_the_historical_read_refusal_cadence` and `DarkwalkIncidentTest.test_missing_own_cell_is_dark_and_public_choice_does_not_read`.
- `incident-darkwalk-attractor-20260825.jsonl.gz` -> `DarkwalkIncidentTest.test_frozen_darkwalk_capture_pins_the_live_attractor` and `DarkwalkIncidentTest.test_darkwalk_enters_adjacent_remembered_floor_before_probing`.
