# S3.3 live short-route validation

## Recorded pin and awaiting-path audit

`tests/test_ownership_s3_3_live_short_route.py` pins the unmodified decision
224 board and claim #140, plus decision 223's posted travel and progress
distance 59. The capture's policy-state export is a projection without a
restorable claim register, so the test rebuilds that claim from its recorded
row. Before the fix the holder returned `None` with
`ownership:holder-silent:store-router`; now it reissues
`ENTRANCE_TRAVEL_MACRO`, updates the recorded goal's travel progress to
distance 5, and keeps claim #140 open with budget 8. A second class scenario
uses the recorded store route goal from decision 219 on the decision 224
board, without plan identity, and confirms a walking step to the same Reach.

The other awaiting states feeding `_town_holder_wait_key` were checked:

- A store-router Reach with a live store plan already uses
  `_shopping_approach_step` and `_shopping_approach_key`; a stale or missing
  plan with an open, routable Reach now walks toward its recorded cell.
- Equipment and calibration sessions with a pending action emit a wait or
  leave; an actionable current action asks the transaction executor for its
  next key.
- A posted store operation emits a leave or typed observation wait. A posted
  entry emits its typed wait. A current knowledge scan emits its typed wait.
- A suspended knowledge scan with an unreleasable post, or another unresolved
  non-discardable operation without an executable step, still reaches the
  visible `holder-silent` terminal. An unposted obligation without unresolved
  work takes the named `no-step:unposted` release.

## Replay gates

Each fixture ran in its own Python process through
`scripts/first_divergence_s3_3.py`. Every OFF digest matched its fixed hash;
every first difference matched `EXPECTED_FIRST` and had no trajectory defect.

| Case | OFF SHA-256 | First ON difference |
| --- | --- | --- |
| tour | `d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464` | list 2703, historical 2701: `7`, `shop:approach` |
| town | `7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1` | list 1179, historical 1177: CR, `equipment-transaction:atomic-deposit` |
| overweight | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` | list 3724, historical 3723: `3`, `shop:approach` |
| withdraw | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | none |
| recall | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | none |
| stuck | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | none |

`scripts/measure_s3_3_on.py` reported zero untyped empty ON keys for each of
the six cases. Its historical replay still reports typed holder-silent rows:
tour 13, town 7, overweight 15, and none in the other three cases. Those
captures do not contain the 2026-09-29 short entrance release.

## Required test modules

127 distinct modules, 4,061 tests, zero failures. `test_town_stall`
contains no unittest cases and exited successfully. Each module ran in its own
Python process.

| Module | Tests |
| --- | ---: |
| `test_000_capture_ledger_hygiene` | 1 |
| `test_ability_sources_incident` | 8 |
| `test_alchemist_observed_shop_alternation` | 6 |
| `test_buy_deposit_loop_recorded` | 3 |
| `test_cal3_visit_budget_recorded` | 1 |
| `test_calibration_restore_deposits_recorded` | 6 |
| `test_calibration_visit_blocked_loop_recorded` | 10 |
| `test_cli` | 234 |
| `test_cli_empty_key` | 1 |
| `test_cli_town_claim_switch` | 3 |
| `test_control_client` | 33 |
| `test_departure_unsatisfiable_weight_recorded` | 7 |
| `test_e6_prelanding_live_recorded` | 1 |
| `test_emit_ownership` | 11 |
| `test_entrance_travel_retired_recorded` | 3 |
| `test_equipment_encounter_sampling` | 5 |
| `test_equipment_encounters` | 4 |
| `test_equipment_in_home_stage1` | 16 |
| `test_equipment_mutation` | 17 |
| `test_equipment_optimizer` | 87 |
| `test_equipment_swap_loop_incident` | 19 |
| `test_equipment_transaction_planner` | 15 |
| `test_equipment_transaction_session` | 15 |
| `test_esp_threat_rest_recorded` | 16 |
| `test_experience_potion` | 13 |
| `test_first_dungeon_entrance_prompt_recorded` | 7 |
| `test_guardian_recall_pingpong_recorded` | 7 |
| `test_home_disposal` | 15 |
| `test_home_entry_capture` | 8 |
| `test_home_equipment_disposal` | 6 |
| `test_home_errand` | 6 |
| `test_home_knowledge_scan` | 38 |
| `test_home_light_alternation` | 37 |
| `test_home_light_alternation_cli` | 7 |
| `test_home_route_stall_recorded` | 1 |
| `test_home_visit` | 21 |
| `test_home_withdraw_deposit_alternation_recorded` | 2 |
| `test_home_withdraw_failed_stock_present_recorded` | 6 |
| `test_home_withdraw_moved_address` | 8 |
| `test_idw_block_recorded` | 1 |
| `test_incident_artifact_fidelity` | 5 |
| `test_latch_onset_capture` | 7 |
| `test_latch_ownership` | 7 |
| `test_loot_before_recall_recorded` | 8 |
| `test_loot_choke_oscillation_recorded` | 4 |
| `test_loot_ledger_mass_deferral_recorded` | 9 |
| `test_loot_triage` | 14 |
| `test_morivant_return_walks_away_recorded` | 7 |
| `test_morivant_travel_retired_recorded` | 3 |
| `test_newchar_light_churn_recorded` | 3 |
| `test_newchar_light_loop_recorded` | 4 |
| `test_newchar_town_wander_recorded` | 5 |
| `test_overweight_home_unreachable_recorded` | 12 |
| `test_ownership_claims` | 22 |
| `test_ownership_metrics` | 15 |
| `test_ownership_s2a1_closure` | 80 |
| `test_ownership_s2a_classification` | 16 |
| `test_ownership_s2b1_ladder` | 52 |
| `test_ownership_s2b1b_close_pairs` | 34 |
| `test_ownership_s2b2_bar` | 30 |
| `test_ownership_s3_3_delegation_record` | 19 |
| `test_ownership_s3_3_first_divergence` | 3 |
| `test_ownership_s3_3_live_short_route` | 2 |
| `test_ownership_s3a_record` | 107 |
| `test_pattern_a_owner_retired_recorded` | 3 |
| `test_pickup_pile_prompt_recorded` | 12 |
| `test_policy` | 57 |
| `test_policy_calibration` | 75 |
| `test_policy_combat` | 296 |
| `test_policy_equipment` | 192 |
| `test_policy_fundraising` | 50 |
| `test_policy_helpers` | 23 |
| `test_policy_home` | 184 |
| `test_policy_identification` | 45 |
| `test_policy_navigation` | 129 |
| `test_policy_observation` | 57 |
| `test_policy_quest` | 335 |
| `test_policy_shop` | 279 |
| `test_policy_structure` | 7 |
| `test_policy_supply` | 202 |
| `test_policy_town` | 598 |
| `test_protocol3_client` | 29 |
| `test_pure_decision_telemetry` | 6 |
| `test_quest34_target_dead_recorded` | 3 |
| `test_quest_carry_departure_recorded` | 4 |
| `test_quest_carry_town_block` | 4 |
| `test_recall_read_cancel_pingpong` | 3 |
| `test_recall_read_cancel_pingpong_recorded` | 5 |
| `test_recall_readiness_contradiction` | 4 |
| `test_recall_stockout_set_end_recorded` | 5 |
| `test_recall_stockout_surplus_pins` | 8 |
| `test_redress_home_page_gap_recorded` | 4 |
| `test_restore_stall_recorded` | 1 |
| `test_sale_key_lint` | 2 |
| `test_shop_one_shot` | 53 |
| `test_star_remove_curse_unused_recorded` | 2 |
| `test_stop_shape_recorded` | 8 |
| `test_stuck_prompt_staged_tail_recorded` | 4 |
| `test_test_fakery_lint` | 13 |
| `test_town_acquire_bypass_recorded` | 4 |
| `test_town_approach_retired_recorded` | 8 |
| `test_town_arbiter` | 29 |
| `test_town_arbiter_suppression` | 4 |
| `test_town_calibration_owner_retired_recorded` | 6 |
| `test_town_emit_ownership_recorded` | 3 |
| `test_town_home_candidate_stall_recorded` | 5 |
| `test_town_latency_caches` | 14 |
| `test_town_loot_store_20260926_recorded` | 3 |
| `test_town_maps` | 6 |
| `test_town_owner_cluster_incident` | 5 |
| `test_town_plan_exhausted_wander` | 12 |
| `test_town_producer_purity` | 1 |
| `test_town_producer_purity_part1` | 1 |
| `test_town_producer_purity_part2` | 1 |
| `test_town_producer_purity_part3` | 1 |
| `test_town_producer_purity_part4` | 1 |
| `test_town_producer_purity_part5` | 1 |
| `test_town_producer_purity_part6` | 1 |
| `test_town_progress_invariant` | 22 |
| `test_town_restock_trajectory` | 21 |
| `test_town_stall` | 0 |
| `test_town_unaffordable_supplies` | 8 |
| `test_unaffordable_claim_tour_recorded` | 7 |
| `test_unsafe_recall_fallback_recorded` | 5 |
| `test_unseen_caster_death_recorded` | 5 |
| `test_wait_telemetry` | 1 |
| `test_warrior_equipment_evaluator` | 11 |
