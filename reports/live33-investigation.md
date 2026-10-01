Live33 investigation (base 92b455ad)

Recorded evidence: incident-20261001-1342-s33-on-declaration-unrestored-calibration, decision sequences 5/6/7, turns 1140630/1140640. The attached calibration record currently has no redress_obligation; observed_turn 1086413. The capture policy-state format does not serialize calibration phase or restore signatures, so it cannot establish those fields at the incident instant.

A recorded entrance attachment, using production skill/Home consumption and choose_key, reproduces keys 5, dhdg6\rdf2\rde10\rdd15\rdc4\rdb10\rda5\rESC, then the stop. Calibration begins a NEW deposit phase, rather than loading supply debt from disk. policy_calibration.py:209-232 loads only redress_obligation (or legacy confirmed equipment), not supply signatures. policy_home.py:1455-1474 registers the five new supply debts: oil, recall, teleport, healing, cure critical. stripped_unrestored is false. The character is dressed; new supplies were actually deposited at row 6. This is real NEW debt, not proof of stale restart debt.

policy_calibration.py:1230-1251 hands deposit work to generic Home routing with a None key. The first two-stage overweight batch belongs to calibration (policy_home.py:2840-2844,2959-2963); the public reason still says home:weight-overload-deposit. After the batch is observed, another candidate remains, the calibration producer offers deposit-handoff but returns None, and the ladder ultimately emits policy:none-wait. policy.py:6883-6894 sees no pending atomic operation and no errand holder (the recorded goal is Terminal), so it stops for the existing debt before calibration can continue. The same pure predicate is used by the OFF shadow at policy.py:6837-6840 and predicts that stop on the same attached state.

Fix direction: under restoration enforcement, calibration executes its own deposit continuation through the existing entrance composer, instead of depending on the generic routing handoff. No UI classifier or new screen is needed. Preserve OFF behavior. Restart pins cover an empty durable record, a satisfied durable redress record, and a genuine redress obligation. No evidence after the first changed key is treated as its response.


Step 2 result

The durable record is level 24 and the recorded entrance character is level 25: stale_reason prints `level`. This explains the new calibration deposit phase. The current durable record contains no redress obligation. No new supply-debt persistence was invented; the real restart loader already reconciles redress against observed equipment. New pins prove no debt for an empty record or already-worn identities, and preservation for an identity still carried. Checkpoint coverage uses the existing attributes; only the derived town-need registry of local predicates is discarded before pickle and rebuilt.

Root fix: policy_calibration.py:1244 executes enforced deposit continuation through the existing Home composer and calibration-requested approach. Ordinary OFF handoff remains unchanged. On the recorded attachment, rows 5 and 6 match live key AND reason; row 7 changes from None / ownership:declaration-unrestored:calibration to 5 / home:atomic-deposit. The first changed key ends the pin; no later board is consumed as its response. Crossarea ON with S3.3 OFF and S3.3 ON agree, including shadow would_stop=None. The baseline source single revert fails with AssertionError: None != '5'; fixed source passes.

Verification (one module per process):
- tests.test_calibration_live33: 2 passed
- tests.test_calibration_live19: 11 passed
- tests.test_calibration_live25: 6 passed
- tests.test_calibration_live28: 3 passed
- tests.test_calibration_live31: 6 passed
- tests.test_calibration_crossarea_debt: 5 passed
- tests.test_policy_calibration: 75 passed
- tests.test_s33_shadow_recorded: 6 passed
- tests.test_ownership_s2a_classification: 16 passed
- tests.test_test_fakery_lint: 13 passed
Total: 143 passed. The calibration fixture payload was added to the pin after the initial run; the changed module was rerun and passed.

Allowed fixture exception: stuck off and s33 hash c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5, no divergence; withdraw off hash a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9, s33 first divergence list_index=3, historical_sequence=3, new_sequence=3, ESC / equipment-transaction:catalogue-leave-for-scan, trajectory_defect=None. EXPECTED_FIRST untouched.

Pending for Claude (DO NOT RUN by implementer): scripts/test_parallel_runner.py, scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py, scripts/mutation_battery.py; tests.test_cli, tests.test_policy_town, tests.test_policy_shop, tests.test_absorbing_states; long tour/town/overweight recorded replays; town producer purity parts; full-fixture first_divergence_s3_3.py runs and all matching-module sweeps. No live game/bot/hold change or push.

Assertion audit: No changed pre-existing assertions or forbidden test edits.
Investigation commit: 55bf8211. Implementation commit is the commit containing this report update.
