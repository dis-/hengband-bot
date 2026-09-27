# Ownership S3.3 prerequisites (record-only)

Base: `49cc369f`. The six isolated replays compare SHA-256 of the complete
ordered `(key, reason)` stream against that base. All six hashes match. Raw
per-replay counts and one representative decision sequence for every
`(classification, requester, operator)` pair are in
`s3-prereq-comparison.jsonl`. The measurement command is
`PYTHONPATH=src:tests:scripts:. python scripts/measure_s3_prereq.py CASE`;
on Windows use semicolons in `PYTHONPATH`. The `CASE` values are `tour`,
`town`, `overweight`, `withdraw`, `recall`, and `stuck`.

## Changes

1. A Home exit after `equipment-transaction-complete` now records a Terminal
   continuation of the completed transaction instead of opening a fresh
   store-operation Observe claim. A production-path pin checks the closed
   claim and the exit row.
2. Router plan stops pass a formal `router_plan_stop` marker and record the
   family supported by their plan need categories. Mixed or unknown categories
   have no invented family and become `requester-missing`. Visit reuse records
   the current requester's family and structure, including after checkpoint
   restore. `_claim_family_of` no longer reads the queued Home request.
3. `shop:await-leave-confirmation` continues the visit claim that held the
   pending leave. A new store operation while that leave is unconfirmed is
   recorded as `leave-confirmation-interruption`. The town pin moves the false
   1958 owner change to actual interruptions at 1947 and 1957.
5. Claim recording no longer overwrites `decision_attribution`. Purpose
   duplicates for identification and Experience quaffing resolve the actual
   command target slot; unrecognized command shapes remain untyped rather than
   matching the filed item by coincidence.
6. The overweight pin's stale requester note was replaced. Its genuine visit
   mismatch pin changed from 17 to 4 after router requests were classified;
   the assertion remains exact.

Item 4 was left unchanged, as instructed.

## Replay measurements

| Replay | Rows | S3 classes | S3 gate | Genuine | Router plan stop | Requester missing | Key/reason vs base |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| Tour | 4267 | owner-change 2; transaction-contention 1 | 3 | 16 | 3 | 29 | identical |
| Town approach | 2052 | owner-change 3; purpose-duplicate 1; leave-confirmation-interruption 2 | 6 | 11 | 2 | 13 | identical |
| Overweight | 3782 | owner-change 1 | 1 | 4 | 0 | 18 | identical |
| Home withdraw | 34 | none | 0 | 5 | 1 | 9 | identical |
| Recall cancel | 18 | none | 0 | 0 | 0 | 0 | identical |
| Stuck prompt | 4 | none | 0 | 0 | 0 | 0 | identical |

`requester-missing` is a recording defect, never counted as a genuine visit
owner mismatch. Remaining rows include visits with no named plan family and
mixed-family stops. The JSONL contains each representative requester/operator
pair and its decision sequence. The S3 gate excludes plan handoffs; all six
captures recorded zero plan handoffs in these replays. Town's gate of 6 exceeds
the provisional 5-row threshold because the previously hidden pending-leave
interruptions are now counted; the 1947 and 1957 rows require S3.3 behavior
enforcement, not a record-only release.

## Verification

Each module below was run in a separate Python process. All runnable modules
passed. `test_equipment_swap_loop_incident` could not set up because this
worktree lacks `jsonlog/incident-equip-swap-loop-20260826.jsonl`; the test
ran 0 cases and raised `FileNotFoundError`. The protected `jsonlog` directory
was not changed.

| Module | Tests | Module | Tests |
| --- | ---: | --- | ---: |
| test_cal3_visit_budget_recorded | 1 | test_calibration_restore_deposits_recorded | 6 |
| test_calibration_visit_blocked_loop_recorded | 10 | test_departure_unsatisfiable_weight_recorded | 7 |
| test_e6_prelanding_live_recorded | 1 | test_entrance_travel_retired_recorded | 3 |
| test_esp_threat_rest_recorded | 16 | test_guardian_recall_pingpong_recorded | 7 |
| test_home_route_stall_recorded | 1 | test_home_withdraw_deposit_alternation_recorded | 2 |
| test_home_withdraw_failed_stock_present_recorded | 5 | test_idw_block_recorded | 1 |
| test_loot_before_recall_recorded | 7 | test_loot_choke_oscillation_recorded | 4 |
| test_morivant_return_walks_away_recorded | 7 | test_morivant_travel_retired_recorded | 3 |
| test_overweight_home_unreachable_recorded | 11 | test_pattern_a_owner_retired_recorded | 3 |
| test_pickup_pile_prompt_recorded | 12 | test_quest_carry_departure_recorded | 4 |
| test_recall_read_cancel_pingpong_recorded | 5 | test_recall_stockout_set_end_recorded | 4 |
| test_redress_home_page_gap_recorded | 4 | test_restore_stall_recorded | 1 |
| test_stop_shape_recorded | 8 | test_stuck_prompt_staged_tail_recorded | 4 |
| test_town_acquire_bypass_recorded | 4 | test_town_approach_retired_recorded | 8 |
| test_town_calibration_owner_retired_recorded | 6 | test_town_emit_ownership_recorded | 3 |
| test_town_loot_store_20260926_recorded | 3 | test_unaffordable_claim_tour_recorded | 7 |
| test_unsafe_recall_fallback_recorded | 5 | test_ability_sources_incident | 8 |
| test_equipment_swap_loop_incident | 0 (fixture missing) | test_incident_artifact_fidelity | 5 |
| test_town_owner_cluster_incident | 5 | test_ownership_claims | 22 |
| test_ownership_metrics | 15 | test_ownership_s2a1_closure | 80 |
| test_ownership_s2a_classification | 16 | test_ownership_s2b1b_close_pairs | 34 |
| test_ownership_s2b1_ladder | 52 | test_ownership_s2b2_bar | 30 |
| test_ownership_s3a_record | 84 | test_experience_potion | 13 |
| test_pure_decision_telemetry | 6 | test_policy_home | 184 |
| test_policy_town | 598 | test_policy_shop | 279 (1 skipped) |
| test_policy_equipment | 192 | test_cli | 234 |

The policy/CLI and affected replay modules were run again after the final
recording changes. All passed. The source diff also passed `git diff --check`.
