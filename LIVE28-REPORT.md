Live28 step 1 - main 08fef4dc

Evidence is copied verbatim into tests/fixtures/live28-calibration-restore-20261001.jsonl.gz (state rows from turn 932800 onward). No live files were modified.

The false absent signature is `鑑定の杖 (21回分)`, tval 55, sval 5. The first recorded withdrawal (decision 15200, turn 933258) includes `pu` for the 21-charge staff. Its response at 933266 carries that exact staff. The 4-charge staff remains Home at index 11 as `鑑定の杖 (2x 4回分)`; its movement identity is unchanged (05c11698dbca6008). The 21-charge movement identity is 5a1cc9e61dd59af6. Thus neither consumption, identification nor the extra weapon equip caused the missing target.

Root: src/hengbot/policy_home.py:2217 selects the first owner with either equal signature OR equal tval/sval. After the two-charge staff is discharged, observation of the 21-charge staff incorrectly discharges the earlier four-charge debt. The 21-charge debt survives both withdrawals and reaches the typed terminal. src/hengbot/policy_home.py:1974 additionally excludes merged stack names from batch candidates despite the movement match at :81. The single withdrawal success in src/hengbot/policy.py:7853 has the same broad owner selection.

Probe: validation/live28/probe.py reproduces the exact first macro, then prints outstanding 21-charge and ammo debt, with the recorded second macro `5pN99\r\x1b`. The extra equip `way` restores the mace to sub_hand; final equipment and initial equipment have the same weapons. Earlier withdrawal already satisfied the 21-charge target, but not the four-charge target.

Step 1 commit: 15d6a546. File:line references above refer to base 08fef4dc.

Step 2 commit: f55c5298. Exact owner/movement matching replaces tval/sval aliasing in batch and single withdrawal observation (policy_home.py:2262; policy.py:7852). Merged shelf names enter batches using movement identity (policy_home.py:2005). Positively observed equipment or carried targets reconcile (policy_home.py:74; policy_calibration.py:1011), without adding checkpoint attributes. The reconciliation completion label is `calibration-restore-observed`. Shelf-present partial deposits remain owed unless worn possession satisfies the quantity.

Applied Claude live28 RULING dated 2026-10-01 10:58 to the live19 historical glove expectation: no target-absent terminal, glove debt and quantity removed, all other remaining debt unchanged. Added a fresh/checkpoint pin where the glove is neither Home, carried nor worn; it retains the typed target-absent terminal. EXPECTED_FIRST unchanged. Pre-existing untracked .live8b-revert.py untouched.

Single revert check: all three new live28 pins fail on base 08fef4dc; restored code passes all three. Recorded first macro changes to include `pv1\r` for the merged four-charge staff. Historical-first recovery changes the second macro from `5pN99\r\x1b` to `5pN99\rpl1\r\x1b`, then constructed command responses complete restoration. Old checkpoint's already-carried 21-charge staff also reconciles.

Stuck/withdraw fixtures ran independently in OFF and S3.3 modes. OFF hashes match c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 and a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9. Stuck S3.3: no divergence. Withdraw S3.3: early-divergence at decision 3 (`~9\x1b`, home:request-knowledge-scan -> `\x1b`, equipment-transaction:catalogue-leave-for-scan), against EXPECTED_FIRST decision 20; reported for Claude, not hidden or repinned. Declaration gaps and mismatches are empty for both fixtures/modes. This command exits zero while reporting the trajectory defect; it is not an all-green S3.3 assertion result.

DO-NOT-RUN pending for Claude: scripts/test_parallel_runner.py, scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py, scripts/mutation_battery.py, tests.test_cli, tests.test_policy_town, tests.test_policy_shop, tests.test_absorbing_states, long tour/town/overweight replays, town producer purity parts, full-fixture runs of scripts/first_divergence_s3_3.py, and all matching module sweeps. Only the expressly authorized stuck/withdraw fixture runs were performed.

Verification (each module in its own Python 3.13 process, PYTHONPATH=src;tests;scripts):

- tests.test_calibration_live28: 3 tests, PASS
- tests.test_calibration_live19: 11 tests, PASS
- tests.test_calibration_live25: 6 tests, PASS
- tests.test_policy_calibration: 75 tests, PASS
- tests.test_calibration_restore_deposits_recorded: 6 tests, PASS
- tests.test_policy_home: 184 tests, PASS (4 skipped)
- tests.test_live23_home_cycle: 7 tests, PASS
- tests.test_ownership_s2a_classification: 16 tests, PASS
- tests.test_test_fakery_lint: 13 tests, PASS

Total: 321 tests, 4 skipped. git diff --check passed. Full process logs and fixture JSON are in validation/live28/.
