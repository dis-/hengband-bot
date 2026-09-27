# Speed-adjusted survival: cold shield audit

The first changed Home-withdrawal board is decision 5 in
`home-withdraw-failed-stock-present-20260925.jsonl.gz`. Its carried gear weighs
1,383 game units against a 1,600 unit limit. With Theoden withdrawn before
Avabia is put away the temporary maximum is 1,503; after swapping weapons and
keeping the shield in the pack it is 1,253. None incurs a weight slowdown.
`player-status/player-speed.cpp:300-322` applies a penalty only above the
limit, which `player/player-status.cpp:2576-2584` derives from strength.

The exact evaluator inputs on that board give this table. The hit column is
the encounter-weighted mean of `monster_melee_hit_chance` across 169 blows;
the evaluator uses half the displayed AC for this probability. Incoming damage
columns are per monster turn. Weighted columns sum each monster's expected
damage multiplied by its `extract_energy` value; divide their sum by player
energy 14 to get incoming damage per player action.

| Loadout | HP | AC | Mean hit | Melee | Ranged | Energy-weighted melee | Energy-weighted ranged | Player speed / energy | Incoming per player action | Survival actions | Melee DPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Avabia + cold shield | 550 | 64 | 0.761485 | 23.615594 | 9.203875 | 427.760306 | 181.793546 | 114 / 14 | 43.539561 | 12.632190 | 189.656652 |
| Theoden + cold shield | 601 | 52 | 0.800759 | 25.531631 | 9.204054 | 460.072322 | 181.801614 | 114 / 14 | 45.848138 | 13.108493 | 131.348154 |
| Theoden + empty off hand | 601 | 44 | 0.824323 | 26.837899 | 9.204054 | 482.340614 | 181.801614 | 114 / 14 | 47.438731 | 12.668973 | 142.958550 |

The shield improves survival when the weapon is fixed: 13.108493 versus
12.668973. The apparent improvement over *Avabia plus shield* changes the
weapon too. Theoden's +3 CON raises HP by 51, following
`player/player-status.cpp:411-414`; its empty off hand permits the two-hand
offense bonus in `player/player-status-flags.cpp:1664-1680`. The measured
player speed and energy do not change. With Theoden fixed, both loadouts make
five blows; the empty hand raises AC-100 hit chance from 0.74 to 0.76 and
expected damage per hit from 35.499501 to 37.620671. The shield's cold
resistance is already provided by a permanent source in the recorded player
state.

The other early replay has Theoden in both compared loadouts. Its shield-only
pair weighs 1,457/1,600 whether the shield is worn or carried, and both have
speed 114, energy 14, and HP 537. Shield on gives AC 54, 25.213754 melee plus
9.191970 ranged incoming per monster turn, weighted damage
454.509781 + 181.611921, 11.818493 survival actions, and 106.366254 melee
DPS. Shield in the pack gives AC 42, 27.114642 melee plus 9.191970 ranged
incoming, weighted damage 487.082957 + 181.611921, 11.242796 survival
actions, and 115.571205 melee DPS. The shield still protects. Empty hand
retains 95.13% of its survival and gains 8.65% offense, so the existing 5%
selection bands can choose it.

The operational selector is behaving as its existing field-wide bands specify.
Its maximum survival is 13.302338, so its 95% cutoff is 12.637221. Avabia
with shield misses that cutoff by 0.005031; Theoden with an empty off hand
clears it. Among those remaining, Theoden with shield has 131.348154 melee
DPS, below 95% of the empty-hand 142.958550. The existing offense band then
selects the empty hand. These exact values and both cutoffs are pinned in
`test_home_withdraw_failed_stock_present_recorded.py`. This is a real game
CON/two-hand effect plus the already approved selector rule, not an error in
AC or player-energy modeling. No evaluator rule or threshold changed.

## Disposition of the 14 round-2 skips

All 14 decorated tests are counterfactual new-code measurements; none is a
live-key equality assertion. All decorators were removed. Only the separate
live-key fidelity tests stop at the first changed action.

| Module | Tests restored | Measured consequence |
| --- | --- | --- |
| Home withdrawal | `test_the_take_shortened_the_prefix_past_the_shovel`, `test_w1_confirming_board_rescans_instead_of_deferring`, `test_w1_after_the_rescan_the_shovels_are_taken` | The recorded board does not confirm the new Theoden withdrawal, so Theoden remains deferred; the later scroll/shovel measurement still runs. |
| Morivant travel | `test_m1_recorded_walk_closing_its_distance_is_not_retired`, `test_m2_walk_that_stops_closing_the_distance_is_still_retired` | The later walk belongs to `store-router`, with progress on movement and retirement after stalled steps. |
| Recall stockout | `test_s1_recorded_stockout_run_survives_next_town_decision`, `test_s4_no_cross_town_shopping_is_started`, `test_s2_resolved_recall_shortage_ends_the_set_at_gold_target` | The unconfirmed equipment transaction owns decision 1426; the shortage and shopping probes still run. |
| Unaffordable claim tour | `test_s3_new_code_replay_names_remaining_violations`, `test_u2_affordable_optional_purchases_still_happen`, `test_root_cause_claims_on_the_post_purchase_board`, `test_u1_after_the_healing_purchase_the_bot_departs`, `test_u3_required_supply_claims_are_not_released`, `test_s2a1_observe_goals_complete_on_their_confirmed_effect` | The claim-row and S3 measurements continue on the new code through the old recorded boards. |

The claim-tour counterfactual has 60 S3 violations, all `owner-change`; their
exact owner pairs and sequence numbers are pinned in the restored S3 test.
Most are handoffs from the unconfirmed equipment transaction. Calibration
still owns rows 2998-3003. The replay measures 53 abandoned equipment
transaction Observe claims, 1,314 next-row Reach completions, and no purchase
at either recorded optional-purchase board (both keys are shop observe/leave).
The recorded post-purchase board still has 3,729 gold, but its four departure
failures are calibration/equipment readiness, and the equipment transaction
owns both the decision and the two gold-variant supply probes. These are
measured consequences of continuing after index 2, not live-key equality
claims.

## Module checks

Each module ran in its own Python process. The two stage-one capture tests and
the equipment swap incident read their missing local capture files from the
existing read-only `C:\hengband\bot-client\jsonlog` tree. The stage-one module
has eight pre-existing expected failures.

| Required core module | Tests | Required core module | Tests |
| --- | ---: | --- | ---: |
| `test_equipment_optimizer` | 87 | `test_warrior_optimization` | 36 |
| `test_policy_equipment` | 192 | `test_optimizer_purity` | 15 |
| `test_equipment_in_home_stage1` | 16 | | |

| Recorded module | Tests | Recorded module | Tests |
| --- | ---: | --- | ---: |
| `test_cal3_visit_budget_recorded` | 1 | `test_calibration_restore_deposits_recorded` | 6 |
| `test_calibration_visit_blocked_loop_recorded` | 10 | `test_departure_unsatisfiable_weight_recorded` | 7 |
| `test_e6_prelanding_live_recorded` | 1 | `test_entrance_travel_retired_recorded` | 3 |
| `test_esp_threat_rest_recorded` | 16 | `test_guardian_recall_pingpong_recorded` | 7 |
| `test_home_route_stall_recorded` | 1 | `test_home_withdraw_deposit_alternation_recorded` | 2 |
| `test_home_withdraw_failed_stock_present_recorded` | 6 | `test_idw_block_recorded` | 1 |
| `test_loot_before_recall_recorded` | 7 | `test_loot_choke_oscillation_recorded` | 4 |
| `test_morivant_return_walks_away_recorded` | 7 | `test_morivant_travel_retired_recorded` | 3 |
| `test_overweight_home_unreachable_recorded` | 11 | `test_pattern_a_owner_retired_recorded` | 3 |
| `test_pickup_pile_prompt_recorded` | 12 | `test_quest_carry_departure_recorded` | 4 |
| `test_recall_read_cancel_pingpong_recorded` | 5 | `test_recall_stockout_set_end_recorded` | 4 |
| `test_redress_home_page_gap_recorded` | 4 | `test_restore_stall_recorded` | 1 |
| `test_stop_shape_recorded` | 8 | `test_stuck_prompt_staged_tail_recorded` | 4 |
| `test_town_acquire_bypass_recorded` | 4 | `test_town_approach_retired_recorded` | 8 |
| `test_town_calibration_owner_retired_recorded` | 6 | `test_town_emit_ownership_recorded` | 3 |
| `test_town_loot_store_20260926_recorded` | 3 | `test_unaffordable_claim_tour_recorded` | 7 |
| `test_unsafe_recall_fallback_recorded` | 5 | | |

| Incident or additional module | Tests | Incident or additional module | Tests |
| --- | ---: | --- | ---: |
| `test_ability_sources_incident` | 8 | `test_equipment_swap_loop_incident` | 19 |
| `test_incident_artifact_fidelity` | 5 | `test_town_owner_cluster_incident` | 5 |
| `test_warrior_loadout_evaluator` | 11 | `test_ownership_s3a_record` | 78 |

Totals: 346 required core, 174 recorded, 37 incident, and 89 additional
tests; 646 tests overall. The final seven-test claim-tour process passed after
its exact counterfactual pins were updated.
