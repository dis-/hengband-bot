# First dungeon entrance prompt

## Mechanism and evidence

The captured town board is turn 82671 at the dungeon entrance (31, 150).
Decision 31 selected `descend` with `>\ry`; the posted-character log records
`>`, CR, and `y` within 2 ms. The run then stopped at the first-entrance
`[y/n]` question. The capture contains the preceding board and posted keys,
but no intervening screen trace, so it does not establish which game read
consumed or discarded `y`.

The game checks `DungeonService::check_first_entrance` on a surface descent,
prints the returned entrance message, then calls `input_check` only when that
message exists (`C:\hengband\src\cmd-action\cmd-move.cpp:269-276`). The service
returns no message once the dungeon record says it has been entered
(`C:\hengband\src\system\services\dungeon-service.cpp:70-78`).
`input_check_strict` calls `msg_erase` before printing the question and reading
its answer (`C:\hengband\src\core\asking-player.cpp:237-254`). `msg_erase` can
call `msg_flush` (`C:\hengband\src\view\display-messages.cpp:330-343`), whose
`-more-` loop consumes CR as a page dismissal (`:171-207`). There is no
unconditional input flush in this `input_check` path; `inkey` flushes queued
input only when its `inkey_xtra` flag is set
(`C:\hengband\src\io\input-key-acceptor.cpp:192-209`). These facts explain
why pre-posting CR and `y` cannot bind `y` to the later confirmation. The open
question proves that `y` did not reach the confirmation read; the exact fate of
that byte cannot be resolved from this capture.

## Fix and pins

The policy decision remains `>\ry` for the recorded producer contract. The
live executor now sends only `>` initially. It dismisses each observed
`-more-` page through its existing page handler, then sends `y` only for the
exact first-entrance question in Japanese or English. The confirmation is an
optional continuation: when a previously entered dungeon returns directly to
the command board, the executor drops `y`. A sender without screen observation
refuses the macro. Other confirmations remain unowned by this operation.

`tests/fixtures/first-dungeon-entrance-board.json.gz` contains the final
captured board with the decision and posted-byte evidence. The new recorded
test module pins that evidence, the first-entry message and confirmation
sequence, both locales, a repeat entry without a prompt, an unrelated
confirmation, the no-observation sender, and a restored policy checkpoint.
Reverting the executor split makes the accepted-segment assertions fail and
reintroduces the unowned confirmation in the source-ordered fake.

## Required module sweep

Each listed `tests/test_*.py` module ran in its own Python process with
`PYTHONPATH=src;tests;scripts`. A module count is the number of tests reported
by `unittest` in that process. The table below will be filled from the sweep.

| Module | Tests | Result |
| --- | ---: | --- |
| `test_000_capture_ledger_hygiene` | 1 | PASS |
| `test_ability_sources_incident` | 8 | PASS |
| `test_buy_deposit_loop_recorded` | 3 | PASS |
| `test_cal3_visit_budget_recorded` | 1 | PASS |
| `test_calibration_restore_deposits_recorded` | 6 | PASS |
| `test_calibration_visit_blocked_loop_recorded` | 10 | PASS |
| `test_cli` | 234 | PASS (rerun) |
| `test_cli_empty_key` | 1 | PASS |
| `test_control_client` | 33 | PASS |
| `test_departure_unsatisfiable_weight_recorded` | 7 | PASS |
| `test_e6_prelanding_live_recorded` | 1 | PASS |
| `test_entrance_travel_retired_recorded` | 3 | PASS |
| `test_equipment_swap_loop_incident` | 19 | PASS |
| `test_esp_threat_rest_recorded` | 16 | PASS |
| `test_first_dungeon_entrance_prompt_recorded` | 7 | PASS |
| `test_guardian_recall_pingpong_recorded` | 7 | PASS |
| `test_home_entry_capture` | 8 | PASS |
| `test_home_light_alternation_cli` | 7 | PASS |
| `test_home_route_stall_recorded` | 1 | PASS |
| `test_home_withdraw_deposit_alternation_recorded` | 2 | PASS |
| `test_home_withdraw_failed_stock_present_recorded` | 6 | PASS |
| `test_idw_block_recorded` | 1 | PASS |
| `test_incident_artifact_fidelity` | 5 | PASS |
| `test_input_executor` | 73 | FAIL |
| `test_latch_onset_capture` | 7 | FAIL |
| `test_loot_before_recall_recorded` | 8 | PASS |
| `test_loot_choke_oscillation_recorded` | 4 | PASS |
| `test_loot_ledger_mass_deferral_recorded` | 9 | PASS |
| `test_morivant_return_walks_away_recorded` | 7 | PASS |
| `test_morivant_travel_retired_recorded` | 3 | PASS |
| `test_newchar_light_loop_recorded` | 4 | PASS |
| `test_newchar_town_wander_recorded` | 5 | PASS |
| `test_overweight_home_unreachable_recorded` | 12 | PASS |
| `test_pattern_a_owner_retired_recorded` | 3 | PASS |
| `test_pickup_pile_prompt_recorded` | 12 | PASS |
| `test_policy` | 57 | PASS |
| `test_policy_calibration` | 75 | PASS |
| `test_policy_combat` | 294 | PASS |
| `test_policy_equipment` | 192 | PASS |
| `test_policy_fundraising` | 50 | PASS |
| `test_policy_helpers` | 23 | PASS |
| `test_policy_home` | 184 | PASS |
| `test_policy_identification` | 45 | PASS |
| `test_policy_navigation` | 129 | PASS |
| `test_policy_observation` | 57 | PASS |
| `test_policy_quest` | 335 | PASS |
| `test_policy_shop` | 279 | PASS |
| `test_policy_structure` | 7 | PASS (rerun) |
| `test_policy_supply` | 202 | PASS |
| `test_policy_town` | 598 | PASS |
| `test_protocol3_client` | 29 | PASS |
| `test_pure_decision_telemetry` | 6 | PASS |
| `test_quest_carry_departure_recorded` | 4 | PASS |
| `test_quest34_target_dead_recorded` | 3 | PASS |
| `test_recall_read_cancel_pingpong_recorded` | 5 | PASS |
| `test_recall_stockout_set_end_recorded` | 5 | PASS |
| `test_redress_home_page_gap_recorded` | 4 | PASS |
| `test_restore_stall_recorded` | 1 | PASS |
| `test_runtime_file_isolation` | 13 | PASS |
| `test_sale_key_lint` | 2 | PASS |
| `test_staged_prompt_chain_rewrite` | 5 | PASS |
| `test_star_remove_curse_unused_recorded` | 2 | PASS |
| `test_stop_shape_recorded` | 8 | PASS |
| `test_stuck_prompt_staged_tail_recorded` | 4 | PASS |
| `test_test_fakery_lint` | 13 | PASS |
| `test_town_acquire_bypass_recorded` | 4 | PASS |
| `test_town_approach_retired_recorded` | 8 | PASS |
| `test_town_calibration_owner_retired_recorded` | 6 | PASS |
| `test_town_emit_ownership_recorded` | 3 | PASS |
| `test_town_home_candidate_stall_recorded` | 5 | PASS |
| `test_town_loot_store_20260926_recorded` | 3 | PASS |
| `test_town_owner_cluster_incident` | 5 | PASS |
| `test_unaffordable_claim_tour_recorded` | 7 | PASS |
| `test_unsafe_recall_fallback_recorded` | 5 | PASS |
| `test_unseen_caster_death_recorded` | 4 | PASS |
| `test_wait_telemetry` | 1 | PASS |

Final: 76 modules, 3216 tests; 74 modules passed (including reruns), 2 modules each had one unrelated failing test.

- `test_input_executor`: 73 tests, 1 error. `test_recorded_recall_depth_shape_completes_through_sender_path` requires absent read-only `jsonlog/incident-20260919-2230-recall-depth-prompt.jsonl`.
- `test_latch_onset_capture`: 7 tests, 1 failure. `test_slim_checkpoint_replays_old_home_deferral_producer_decision` sees different current monrace definitions after checkpoint restoration.
- `test_cli` (234 tests) and `test_policy_structure` (7 tests) passed on rerun after fixes during this work.
