# Ownership S3.3 round 3 validation

Commits: `4ce942a9` (producer wiring), `cd2a06d4` (guard pins and OFF measurement). The S3.3 town claim switch remains OFF by default.

## OFF identity and deferred rows

Each selected recorded harness was run once against this branch and once against the `d3d3f1df` source using the same test window. The SHA-256 is over the ordered `(str(key), last_reason)` values returned by `choose_key`. Counts and hashes match exactly in all six cases.

| Replay | Decisions | OFF `errand_deferred` rows | Key/reason SHA-256 | Main match |
| --- | ---: | ---: | --- | --- |
| tour | 4272 | 101 | `6748757f2920875d1f31366e4c625aec319330906c048308226f451d2983b8da` | yes |
| town-approach | 2055 | 114 | `3031d47d8056764200795a80930ab4ef2014eb7f2cbee9dd46943adf8c683bff` | yes |
| overweight-home | 3782 | 64 | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` | yes |
| home-withdraw | 34 | 6 | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | yes |
| recall-cancel | 18 | 0 | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | yes |
| stuck-prompt | 4 | 0 | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | yes |

## Required module results

Each module ran in its own Python process with `PYTHONPATH=src;tests;scripts`. 115 modules completed; 3,973 tests ran. Three modules have four failing assertions. The same failures reproduce on pre-wiring commit `4e8a7e11`: overweight Home expects 4 visit-owner mismatches and observes 5; `test_policy_town` expects a character dump but receives entrance step-off; the tour expects no retarget at decision 3035 and expects 8 Home-knowledge completions but observes 11. The recorded key/reason streams still match `d3d3f1df` in the six cases above.

| Module | Tests | Result |
| --- | ---: | --- |
| test_000_capture_ledger_hygiene | 1 | pass |
| test_ability_sources_incident | 8 | pass |
| test_alchemist_observed_shop_alternation | 6 | pass |
| test_cal3_visit_budget_recorded | 1 | pass |
| test_calibration_restore_deposits_recorded | 6 | pass |
| test_calibration_visit_blocked_loop_recorded | 10 | pass |
| test_cli | 234 | pass |
| test_cli_empty_key | 1 | pass |
| test_control_client | 33 | pass |
| test_departure_unsatisfiable_weight_recorded | 7 | pass |
| test_e6_prelanding_live_recorded | 1 | pass |
| test_emit_ownership | 11 | pass |
| test_entrance_travel_retired_recorded | 3 | pass |
| test_equipment_encounter_sampling | 5 | pass |
| test_equipment_encounters | 4 | pass |
| test_equipment_in_home_stage1 | 16 | pass |
| test_equipment_mutation | 17 | pass |
| test_equipment_optimizer | 87 | pass |
| test_equipment_swap_loop_incident | 19 | pass |
| test_equipment_transaction_planner | 15 | pass |
| test_equipment_transaction_session | 15 | pass |
| test_esp_threat_rest_recorded | 16 | pass |
| test_experience_potion | 13 | pass |
| test_guardian_recall_pingpong_recorded | 7 | pass |
| test_home_disposal | 15 | pass |
| test_home_entry_capture | 8 | pass |
| test_home_equipment_disposal | 6 | pass |
| test_home_errand | 6 | pass |
| test_home_knowledge_scan | 38 | pass |
| test_home_light_alternation | 37 | pass |
| test_home_light_alternation_cli | 7 | pass |
| test_home_route_stall_recorded | 1 | pass |
| test_home_visit | 21 | pass |
| test_home_withdraw_deposit_alternation_recorded | 2 | pass |
| test_home_withdraw_failed_stock_present_recorded | 6 | pass |
| test_home_withdraw_moved_address | 8 | pass |
| test_idw_block_recorded | 1 | pass |
| test_incident_artifact_fidelity | 5 | pass |
| test_latch_onset_capture | 7 | pass |
| test_latch_ownership | 7 | pass |
| test_loot_before_recall_recorded | 8 | pass |
| test_loot_choke_oscillation_recorded | 4 | pass |
| test_loot_ledger_mass_deferral_recorded | 9 | pass |
| test_loot_triage | 14 | pass |
| test_morivant_return_walks_away_recorded | 7 | pass |
| test_morivant_travel_retired_recorded | 3 | pass |
| test_overweight_home_unreachable_recorded | 12 | baseline failure (1) |
| test_ownership_claims | 22 | pass |
| test_ownership_metrics | 15 | pass |
| test_ownership_s2a_classification | 16 | pass |
| test_ownership_s2a1_closure | 80 | pass |
| test_ownership_s2b1_ladder | 52 | pass |
| test_ownership_s2b1b_close_pairs | 34 | pass |
| test_ownership_s2b2_bar | 30 | pass |
| test_ownership_s3a_record | 87 | pass |
| test_pattern_a_owner_retired_recorded | 3 | pass |
| test_pickup_pile_prompt_recorded | 12 | pass |
| test_policy | 57 | pass |
| test_policy_calibration | 71 | pass |
| test_policy_combat | 294 | pass |
| test_policy_equipment | 192 | pass |
| test_policy_fundraising | 50 | pass |
| test_policy_helpers | 23 | pass |
| test_policy_home | 184 | pass |
| test_policy_identification | 45 | pass |
| test_policy_navigation | 129 | pass |
| test_policy_observation | 57 | pass |
| test_policy_quest | 335 | pass |
| test_policy_shop | 279 | pass |
| test_policy_structure | 7 | pass |
| test_policy_supply | 202 | pass |
| test_policy_town | 598 | baseline failure (1) |
| test_protocol3_client | 29 | pass |
| test_pure_decision_telemetry | 6 | pass |
| test_quest_carry_departure_recorded | 4 | pass |
| test_quest_carry_town_block | 4 | pass |
| test_recall_read_cancel_pingpong | 3 | pass |
| test_recall_read_cancel_pingpong_recorded | 5 | pass |
| test_recall_readiness_contradiction | 4 | pass |
| test_recall_stockout_set_end_recorded | 5 | pass |
| test_recall_stockout_surplus_pins | 8 | pass |
| test_redress_home_page_gap_recorded | 4 | pass |
| test_restore_stall_recorded | 1 | pass |
| test_sale_key_lint | 2 | pass |
| test_shop_one_shot | 51 | pass |
| test_stop_shape_recorded | 8 | pass |
| test_stuck_prompt_staged_tail_recorded | 4 | pass |
| test_test_fakery_lint | 13 | pass |
| test_town_acquire_bypass_recorded | 4 | pass |
| test_town_approach_retired_recorded | 8 | pass |
| test_town_arbiter | 29 | pass |
| test_town_arbiter_suppression | 4 | pass |
| test_town_calibration_owner_retired_recorded | 6 | pass |
| test_town_emit_ownership_recorded | 3 | pass |
| test_town_home_candidate_stall_recorded | 4 | pass |
| test_town_latency_caches | 14 | pass |
| test_town_loot_store_20260926_recorded | 3 | pass |
| test_town_maps | 6 | pass |
| test_town_owner_cluster_incident | 5 | pass |
| test_town_plan_exhausted_wander | 12 | pass |
| test_town_producer_purity | 1 | pass |
| test_town_producer_purity_part1 | 1 | pass |
| test_town_producer_purity_part2 | 1 | pass |
| test_town_producer_purity_part3 | 1 | pass |
| test_town_producer_purity_part4 | 1 | pass |
| test_town_producer_purity_part5 | 1 | pass |
| test_town_producer_purity_part6 | 1 | pass |
| test_town_progress_invariant | 22 | pass |
| test_town_restock_trajectory | 21 | pass |
| test_town_stall | 0 | pass |
| test_town_unaffordable_supplies | 8 | pass |
| test_unaffordable_claim_tour_recorded | 7 | baseline failure (2) |
| test_unsafe_recall_fallback_recorded | 5 | pass |
| test_wait_telemetry | 1 | pass |
| test_warrior_equipment_evaluator | 11 | pass |

