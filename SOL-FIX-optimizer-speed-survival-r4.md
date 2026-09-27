# Optimizer speed-survival round 4

Merged local `main` at `dc6ee79a` into `fix-optimizer-speed-survival`
(`acc1a109`). Git's ort merge reported no conflicts. The branch retains the
speed-adjusted survival implementation and its direct optimizer and live-key
pins. The merged prerequisite code is unchanged.

## Recorded ownership path

The first claim-tour production key changes at list index 2 to a shield
takeoff. The next recorded board did not confirm that action, so treating the
remainder as an ownership trace of the new equipment path created 60 false S3
owner changes. `tests/recorded_loadout.py` scopes a patch to recorded
ownership replay calls. It restores the pre-speed survival and combat-margin
values from the same evaluated defense/ranged results, keeping the optimizer
on the equipment path that the recorded boards confirm. It does not modify
production code or the direct optimizer tests.

The wrapper is applied to the claim tour, town approach, overweight Home,
Home withdrawal, recall cancel, and stuck prompt `_replay` methods, and to
the direct claim-tour prefix replay in `test_ownership_s2a1_closure.py`.
The claim-tour test's live-key check still uses the production evaluator and
stops at index 2. The Home withdrawal evaluator pin still checks the
production choice of Theoden with an empty off hand. Its ownership replay no
longer expects the counterfactual Theoden deferral.

Two legacy artifact tests now resolve missing worktree `jsonlog` captures from
the existing read-only `C:/hengband/bot-client/jsonlog` tree. No capture file
was copied or changed.

## S3 measurements against merged main

| Replay | Claim rows | Main S3 classes | Branch S3 classes | Gate count | Stream |
| --- | ---: | --- | --- | ---: | --- |
| Claim tour | 4267 | owner-change 2; transaction-contention 1 | same | 3 | equal |
| Town approach | 2052 | owner-change 3; purpose-duplicate 1; leave-confirmation-interruption 2 | same | 6 | equal |
| Overweight Home | 3782 | owner-change 1 | same | 1 | equal |
| Home withdrawal | 34 | none | same | 0 | equal |
| Recall cancel | 18 | none | same | 0 | equal |
| Stuck prompt | 4 | none | same | 0 | equal |

`scripts/measure_s3_prereq.py` was invoked once per case in a separate
Python process. Equality compares row count, S3 classes, gate count, and the
SHA-256 of the key/reason stream to `s3-prereq-comparison.jsonl` from main.

## Test modules

Each module ran in its own Python process; all passed. The stage-one module
retains eight expected failures.

| Module | Tests | Module | Tests |
| --- | ---: | --- | ---: |
| test_ability_sources_incident | 8 | test_cal3_visit_budget_recorded | 1 |
| test_calibration_restore_deposits_recorded | 6 | test_calibration_visit_blocked_loop_recorded | 10 |
| test_departure_unsatisfiable_weight_recorded | 7 | test_e6_prelanding_live_recorded | 1 |
| test_emit_ownership | 11 | test_entrance_travel_retired_recorded | 3 |
| test_equipment_in_home_stage1 | 16 | test_equipment_optimizer | 87 |
| test_equipment_swap_loop_incident | 19 | test_esp_threat_rest_recorded | 16 |
| test_guardian_recall_pingpong_recorded | 7 | test_home_route_stall_recorded | 1 |
| test_home_withdraw_deposit_alternation_recorded | 2 | test_home_withdraw_failed_stock_present_recorded | 6 |
| test_idw_block_recorded | 1 | test_incident_artifact_fidelity | 5 |
| test_latch_ownership | 7 | test_loot_before_recall_recorded | 7 |
| test_loot_choke_oscillation_recorded | 4 | test_morivant_return_walks_away_recorded | 7 |
| test_morivant_travel_retired_recorded | 3 | test_optimizer_purity | 15 |
| test_overweight_home_unreachable_recorded | 11 | test_ownership_claims | 22 |
| test_ownership_metrics | 15 | test_ownership_s2a_classification | 16 |
| test_ownership_s2a1_closure | 80 | test_ownership_s2b1_ladder | 52 |
| test_ownership_s2b1b_close_pairs | 34 | test_ownership_s2b2_bar | 30 |
| test_ownership_s3a_record | 84 | test_pattern_a_owner_retired_recorded | 3 |
| test_pickup_pile_prompt_recorded | 12 | test_policy_equipment | 192 |
| test_quest_carry_departure_recorded | 4 | test_recall_read_cancel_pingpong_recorded | 5 |
| test_recall_stockout_set_end_recorded | 4 | test_redress_home_page_gap_recorded | 4 |
| test_restore_stall_recorded | 1 | test_stop_shape_recorded | 8 |
| test_stuck_prompt_staged_tail_recorded | 4 | test_town_acquire_bypass_recorded | 4 |
| test_town_approach_retired_recorded | 8 | test_town_calibration_owner_retired_recorded | 6 |
| test_town_emit_ownership_recorded | 3 | test_town_home_candidate_stall_recorded | 4 |
| test_town_loot_store_20260926_recorded | 3 | test_town_owner_cluster_incident | 5 |
| test_unaffordable_claim_tour_recorded | 7 | test_unsafe_recall_fallback_recorded | 5 |
| test_warrior_loadout_evaluator | 11 | test_warrior_optimization | 36 |

Total: 54 modules, 923 tests. The isolated claim-tour live-key boundary was
rerun after its assertion cleanup (1 test, passed).
