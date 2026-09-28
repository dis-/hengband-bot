# New character calibration and identify-first incident

## Capture mechanism

- `incident-20260928-1712-newchar-calibration-identify-first.state.jsonl.gz` (decompressed lines 416 and 420): the worn Brass Lantern is `tval=39`, `sval=1`, `known=false`; after four takeoffs the equipment list is empty and pack `a`/`c`/`d` hold the known ring, armour and sword while `b` holds the unidentified lantern. Gold is 136.
- The matching decisions (decompressed lines 281, 289-300) retain `identification_need=normal` and an equipped incomplete light. The entry check used only whether identification was actionable, then calibration moved from `strip` to `capture`. Lines 289-292 post `ta`, `td`, `th`, `tg`; line 293 requests the naked character dump.
- Restore orders the light before body, ring and weapon. Line 294 reports `equipment-mutation:identify-first` and `equipment_transaction.entry_blocker=session-not-executable`; line 295 lists `calibration-restore:light` in `failed_transaction_item_ids`. The entire session is abandoned before any known item is reached. Lines 296-300 repeat the refusal and abandonment, ending at `town:blocked:owner-retired` with empty equipment.
- The quest's unidentified light wield is an explicit `quest_contract_exempt` call in `policy_quest.py:2846`; ordinary restore calls `policy_equipment.py:1986` without that flag. The exemption does not cover a later re-wield of the same item.

## Fix and regression pins

- Calibration checks the same identify-first predicate as wield before beginning or stripping; a newly unrewearable worn item during an existing deposit phase aborts safely. This leaves the lantern worn for the normal equipped identification flow, which requests or uses an Identify source when available.
- A restore session includes every recorded item that is currently re-wearable. One blocked lantern cannot prevent restoring the known sword, ring and armour. Durable redress still skips the unknown lantern, while the light departure gate remains closed until a usable known light is worn. The capture's Home board (decompressed state line 415) contains a known torch.
- `tests/test_policy_calibration.py` contains four new tests over an extracted capture fixture. They pin the original decision sequence and board fields, prevent premature calibration, verify the normal worn-item Identify command, exercise partial restore, and load redress debt into a fresh policy. Reverting the entry guard or restore filter fails these tests. Fixture provenance records the compressed source SHA-256 hashes.

## Required module results

All modules below ran individually with `PYTHONPATH=src;tests;scripts`. Result: **115 modules, 3,918 tests, zero failures**. `test_town_stall` ran 0 tests because its class setup skipped once when external Hengband edit data was unavailable; its seven discovered test methods were not counted as run.

| Module | Tests run |
| --- | ---: |
| `test_000_capture_ledger_hygiene` | 1 |
| `test_ability_sources_incident` | 8 |
| `test_buy_deposit_loop_recorded` | 3 |
| `test_cal3_visit_budget_recorded` | 1 |
| `test_calibration_restore_deposits_recorded` | 6 |
| `test_calibration_visit_blocked_loop_recorded` | 10 |
| `test_cli` | 234 |
| `test_cli_empty_key` | 1 |
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
| `test_morivant_return_walks_away_recorded` | 7 |
| `test_morivant_travel_retired_recorded` | 3 |
| `test_newchar_light_loop_recorded` | 4 |
| `test_overweight_home_unreachable_recorded` | 12 |
| `test_ownership_claims` | 22 |
| `test_ownership_metrics` | 15 |
| `test_ownership_s2a1_closure` | 80 |
| `test_ownership_s2a_classification` | 16 |
| `test_ownership_s2b1_ladder` | 52 |
| `test_ownership_s2b1b_close_pairs` | 34 |
| `test_ownership_s2b2_bar` | 30 |
| `test_ownership_s3a_record` | 84 |
| `test_pattern_a_owner_retired_recorded` | 3 |
| `test_pickup_pile_prompt_recorded` | 12 |
| `test_policy` | 57 |
| `test_policy_calibration` | 75 |
| `test_policy_combat` | 294 |
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
| `test_recall_read_cancel_pingpong_recorded` | 5 |
| `test_recall_stockout_set_end_recorded` | 5 |
| `test_redress_home_page_gap_recorded` | 4 |
| `test_restore_stall_recorded` | 1 |
| `test_runtime_file_isolation` | 13 |
| `test_sale_key_lint` | 2 |
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
| `test_unseen_caster_death_recorded` | 4 |
| `test_wait_telemetry` | 1 |
| `test_warrior_equipment_evaluator` | 11 |
