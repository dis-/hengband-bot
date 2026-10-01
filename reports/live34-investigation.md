# Live34 calibration investigation (base 64e3fabe)

Rule: calibration is the producer of every action in its physical sequence. Equipment and Home are its executors, not competing errands. Each command declares acting, confirmation names the actual posted operation as awaiting, and observed completion declares done. Equipment session identity is checked before treating an executor as calibration; unrelated equipment work remains gated.

Frozen inputs: tests/fixtures/live34-{0317,0812,0812b,1041,1235,1342,1416}.json.gz, extracted without changes from the named incident state/decision streams. 0812b also covers the live25 calibration included in the 0812 incident. The initial attachment consumes preceding recorded Home/skill knowledge, observes the first deposit board, and calls the production calibration begin. Each replay ends at its first changed key; later recorded boards are never used as responses. Independent strip attachments use the first recorded takeoff board and production begin/install, to expose executor defects beyond an earlier legitimate entry divergence. These are independent attachments, not continuations of a changed command.

| Sequence | ON result before fix | Cause (base file:line) |
|---|---|---|
| 02:58 / 0317 | entry ends at 3014: step-off instead of ta; independent strip stops at 3015 | policy.py:5819-5834 treats calibration-owned executor as equipment-txn; policy_equipment.py:2153 asks that foreign family and policy_equipment.py:2136 declares releasing for calibration |
| 08:12 / 0812 | entry ends at 13: step-off instead of ta; independent strip stops at 14 | same executor admission/declaration gap |
| live25 / 0812b | entry ends at 1254: step-off instead of ta; independent strip stops at 1255 | same executor admission/declaration gap |
| 10:41 / 1041 | entry ends at 15178: step-off instead of tb; independent strip stops at 15179 | same executor admission/declaration gap |
| 12:35 / 1235 | entry ends at 5561: step-off instead of tb; independent strip stops at 5562 | same executor admission/declaration gap |
| 13:42 / 1342 | 5/6 match; 7 changes to 5 / home:atomic-deposit; no ON stop | prior live33 fix policy_calibration.py:1244-1265 already continues the deposit |
| 14:16 / 1416 | initial map attachment chooses a different step-off at 136; independent strip stops at 138 | same executor gap; live stop 145 additionally follows claim expiry at 144, invalidating the claim-bound child token (policy.py:5790-5800) |

The live 14:16 decision log shows claim 76 expiring within-exceeded at 144 and claim 77 holding the light takeoff; at 145 the executor reports no-step/deferred-by-town-holder under calibration, leaving a non-discardable releasing declaration. Structural validation rejects it at policy.py:6237-6239. Increasing the eight-observation limit or rebinding unrelated grants would mask the producer-family error; neither is needed.

Other declaration seams to cover under the same rule: Home equipment outcomes currently offer equipment-txn even for calibration (policy_equipment.py:1774-1787); knowledge/excess-deposit offers use calibration.restore-supplies as their continuation but the awaiting dispatcher only recognizes calibration.capture.observe (policy.py:6291-6318,6440-6470). Completion should be recorded at the calibration phase's observed end, not inferred from missing work.

Baseline evidence: reports/live34-strip-before.txt. No EXPECTED_FIRST changes. Existing untracked .live8b-revert.py retained.

DO NOT RUN / pending for Claude: scripts/test_parallel_runner.py, scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py, scripts/mutation_battery.py; tests.test_cli, tests.test_policy_town, tests.test_policy_shop, tests.test_absorbing_states; long tour/town/overweight replays; town producer purity parts; full-fixture first_divergence_s3_3.py and all matching-module sweeps. Only stuck/withdraw off+s33 are authorized exceptions.
