# Batch 3 suite verification

Base: `bddf2aab` (`fix-batch3-suite`). The requested module sweep ran each
`tests/test_*.py` module matching the batch prompt in a separate Python process
with `PYTHONPATH=src;tests;scripts`. The count table below includes reruns after
fixing test harness issues.

## Original failures and causes

| Failure | Merged change and causal check | Resolution |
| --- | --- | --- |
| Fakery lint: `_live_loot_prefix` | The loot-ledger replay introduced the loop; scanning a scratch copy of the pre-ledger test produced no finding. Each iteration consumes the next recorded response board. | Declare the specific `frozen-drive-state` finding at the loop and advance the declaration ratchet. |
| Gate-1 Home entry capture | Speed-adjusted survival selected an equipment withdrawal before the captured digger exit. A scratch source copy with the earlier loadout combination restored ESC; the Home-candidate and S3 changes remained present. | Use `recorded_loadout_replay` for this recorded-path test. |
| Experience potion X7 and T1–T4 | Speed-adjusted survival changed the equipment path before the relevant recorded boards. In a scratch source copy with the earlier loadout combination, protocol-2 decisions 242 and 246 matched their recording. The replay-only loadout wrapper restored all potion pins. | Wrap the recorded lifetime in `recorded_loadout_replay`; keep all potion assertions. |
| Pure decision telemetry tour and second arrival | Speed-adjusted survival changed the recorded equipment path. With the replay-only loadout reversion, both telemetry tests passed their original key and state checks. | Wrap only the two affected recorded tour tests. |
| Protocol-3 client lifetime | Speed-adjusted survival produced a takeoff at sequence 4 on boards that later confirm the old loadout. A scratch source copy with the earlier loadout combination matched recorded sequences 1–4. | Wrap the lifetime replay in `recorded_loadout_replay`. |

No production change was needed. The Home-candidate and S3 prerequisites were
still active in the scratch speed-reversion trials. The loot-ledger change
explains the new lint site, while the repaired ledger behavior remains covered
by its own recorded tests.

## Additional sweep repairs

- Corrected the Home door-bounce SHA-256 pin to the committed fixture bytes;
  the behavioral assertions remain intact.
- Used the existing, byte-identical committed quest capture for quest and
  shop tests, instead of a missing local `jsonlog` path.
- Reused the read-only historical capture in the main checkout for policy
  structure, town progress, and producer-purity tests when a linked worktree
  omits local `jsonlog` files.
- Made the Home history isolation test create its own temporary sentinel, so
  it verifies an unchanged SHA-256 in a clean worktree.

## Module counts

`0` means the named module contains no discovered unittest cases. All modules
in this table passed in the final run or rerun.

| Module | Tests |
| --- | ---: |
| test_000_capture_ledger_hygiene | 1 |
| test_ability_sources_incident | 8 |
| test_alchemist_observed_shop_alternation | 6 |
| test_cal3_visit_budget_recorded | 1 |
| test_calibration_restore_deposits_recorded | 6 |
| test_calibration_visit_blocked_loop_recorded | 10 |
| test_cli | 234 |
| test_cli_empty_key | 1 |
| test_control_client | 33 |
| test_departure_unsatisfiable_weight_recorded | 7 |
| test_e6_prelanding_live_recorded | 1 |
| test_emit_ownership | 11 |
| test_entrance_travel_retired_recorded | 3 |
| test_equipment_encounter_sampling | 5 |
| test_equipment_encounters | 4 |
| test_equipment_in_home_stage1 | 16 |
| test_equipment_mutation | 17 |
| test_equipment_optimizer | 87 |
| test_equipment_swap_loop_incident | 19 |
| test_equipment_transaction_planner | 15 |
| test_equipment_transaction_session | 15 |
| test_esp_threat_rest_recorded | 16 |
| test_experience_potion | 13 |
| test_guardian_recall_pingpong_recorded | 7 |
| test_home_disposal | 15 |
| test_home_entry_capture | 8 |
| test_home_equipment_disposal | 6 |
| test_home_errand | 6 |
| test_home_knowledge_scan | 38 |
| test_home_light_alternation | 37 |
| test_home_light_alternation_cli | 7 |
| test_home_route_stall_recorded | 1 |
| test_home_visit | 21 |
| test_home_withdraw_deposit_alternation_recorded | 2 |
| test_home_withdraw_failed_stock_present_recorded | 6 |
| test_home_withdraw_moved_address | 8 |
| test_idw_block_recorded | 1 |
| test_incident_artifact_fidelity | 5 |
| test_latch_onset_capture | 7 |
| test_latch_ownership | 7 |
| test_loot_before_recall_recorded | 8 |
| test_loot_choke_oscillation_recorded | 4 |
| test_loot_ledger_mass_deferral_recorded | 9 |
| test_loot_triage | 14 |
| test_morivant_return_walks_away_recorded | 7 |
| test_morivant_travel_retired_recorded | 3 |
| test_overweight_home_unreachable_recorded | 12 |
| test_ownership_claims | 22 |
| test_ownership_metrics | 15 |
| test_ownership_s2a_classification | 16 |
| test_ownership_s2a1_closure | 80 |
| test_ownership_s2b1_ladder | 52 |
| test_ownership_s2b1b_close_pairs | 34 |
| test_ownership_s2b2_bar | 30 |
| test_ownership_s3a_record | 84 |
| test_pattern_a_owner_retired_recorded | 3 |
| test_pickup_pile_prompt_recorded | 12 |
| test_policy | 57 |
| test_policy_calibration | 71 |
| test_policy_combat | 294 |
| test_policy_equipment | 192 |
| test_policy_fundraising | 50 |
| test_policy_helpers | 23 |
| test_policy_home | 184 |
| test_policy_identification | 45 |
| test_policy_navigation | 129 |
| test_policy_observation | 57 |
| test_policy_quest | 335 |
| test_policy_shop | 279 |
| test_policy_structure | 7 |
| test_policy_supply | 202 |
| test_policy_town | 598 |
| test_protocol3_client | 29 |
| test_pure_decision_telemetry | 6 |
| test_quest_carry_departure_recorded | 4 |
| test_quest_carry_town_block | 4 |
| test_recall_read_cancel_pingpong | 3 |
| test_recall_read_cancel_pingpong_recorded | 5 |
| test_recall_readiness_contradiction | 4 |
| test_recall_stockout_set_end_recorded | 5 |
| test_recall_stockout_surplus_pins | 8 |
| test_redress_home_page_gap_recorded | 4 |
| test_restore_stall_recorded | 1 |
| test_sale_key_lint | 2 |
| test_shop_one_shot | 51 |
| test_stop_shape_recorded | 8 |
| test_stuck_prompt_staged_tail_recorded | 4 |
| test_test_fakery_lint | 13 |
| test_town_acquire_bypass_recorded | 4 |
| test_town_approach_retired_recorded | 8 |
| test_town_arbiter | 29 |
| test_town_arbiter_suppression | 4 |
| test_town_calibration_owner_retired_recorded | 6 |
| test_town_emit_ownership_recorded | 3 |
| test_town_home_candidate_stall_recorded | 4 |
| test_town_latency_caches | 14 |
| test_town_loot_store_20260926_recorded | 3 |
| test_town_maps | 6 |
| test_town_owner_cluster_incident | 5 |
| test_town_plan_exhausted_wander | 12 |
| test_town_producer_purity | 1 |
| test_town_producer_purity_part1 | 1 |
| test_town_producer_purity_part2 | 1 |
| test_town_producer_purity_part3 | 1 |
| test_town_producer_purity_part4 | 1 |
| test_town_producer_purity_part5 | 1 |
| test_town_producer_purity_part6 | 1 |
| test_town_progress_invariant | 22 |
| test_town_restock_trajectory | 21 |
| test_town_stall | 0 |
| test_town_unaffordable_supplies | 8 |
| test_unaffordable_claim_tour_recorded | 7 |
| test_unsafe_recall_fallback_recorded | 5 |
| test_wait_telemetry | 1 |
| test_warrior_equipment_evaluator | 11 |

Total: 115 modules, 3970 tests.
