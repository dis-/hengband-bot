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

Step 2 implementation

The same calibration producer owns the installed equipment session at both entry admission and its ordinary calibration rung (policy.py:5810,5930; policy_calibration.py:1093). This uses the existing session target identity, including after a claim expires; it grants nothing to an unrelated equipment session. The equipment Home executor now declares the same producer as its town executor (policy_equipment.py:1773,1827). No new attributes or limits were introduced.

Home send/observe declarations are preserved instead of overwritten with a travel/excess-deposit declaration (policy_calibration.py:151,1385,1480). Calibration's posted restore scan has a valid phase continuation in both pure shadow validation and the bounded producer dispatcher (policy.py:6318,6458), and repeated knowledge waits retain the original posted operation reference. Observed restoration ends with done/complete only when phase, suspension, equipment debt, supply debt and pending Home operations have all ended (policy_calibration.py:133).

The batch exposed another actual ON stop after the initial executor fix: 0812 decision 30, ownership:declaration-stale:calibration. Cause: base policy_calibration.py:1424-1434 overwrote the Home withdrawal's declaration with calibration:restore-travel / calibration.restore-supplies, while base policy.py:6298-6318 recognized only the capture continuation. reports/live34-after.txt records that intermediate failure. Preserving the exact Home binding removes that stop; the completed supply restore can advance to the next recorded board.

Final recorded ON boundaries (zero ON stops to each boundary):

| Sequence | Deposit-start replay ends at | Independent strip replay ends at | Independent restore replay ends at |
|---|---|---|---|
| 0317 | 3027, different post-redress entry step | 3027 | 3034, Home entry wait instead of full withdrawal |
| 0812 | 31, supply restoration completed; next command differs | 28 | 29, Home entry wait instead of full withdrawal |
| 0812b / live25 | 1272, changed restore macro | 1271 | 1272, Home entry wait instead of full withdrawal |
| 1041 | 15200, changed restore macro | 15199 | 15200, Home entry wait instead of full withdrawal |
| 1235 | 5585, changed restore macro | 5584 | 5585, Home entry wait instead of full withdrawal |
| 1342 | 7, 5 / home:atomic-deposit replaces the recorded stop | not present in capture | not present in capture |
| 1416 | 136, different step-off direction from fresh map attachment | 145, next actual takeoff replaces the recorded stop | not present in capture |

All earlier recorded commands remain actual responses until these first changed keys. Every independent phase attachment is named; later boards are not borrowed across a changed key. Restore attachments verify the historical deposit selectors/quantities through the production deposit producer and invalidate the old Home addresses through the production observer before replaying ~9. Existing live19/25/28/31/33 modules cover their deeper historical reconciliation and physical restoration cases separately.

The new module has three pins with checkpoint restoration and OFF shadow checks. The final full-module run passed all three tests; the restore attachment was then strengthened to invalidate the confirmed historical deposits' catalogue and check exact deposit commands, and that changed test passed separately (five sequences, all checkpoints). Every available OFF frame predicts no ON stop; each measured ON frame and each unresolved posted calibration declaration is also checked. OFF and ON can legitimately reach different first changed commands; the pins do not force later boards into either trajectory.
