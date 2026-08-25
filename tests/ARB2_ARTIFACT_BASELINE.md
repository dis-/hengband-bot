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
