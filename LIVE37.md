# live37: recorded Home scan gate finding

Base: b24fd077. Worktree: bot-client-decl-r3b, branch live37.

## Step 1 (source line numbers at b24fd077)

The recorded holders are store-router Reach claims 2566 (decision 3106,
14:45:29) and 8583 (decision 9682, 16:09:48). Both name (37,91),
`route:store:37,91`, `route.resume`; their visits have purpose `shopping`,
store_type 4, phase `entering`, requester `shop-buy`, no posted store operation.
The preceding recorded key is `7`, from (37,91) to (36,90). These facts were
printed from the two decision logs; the frozen extracts retain the original
records. This is Alchemist shopping, not a Home catalogue acquisition.

There is **no skipped entry gate on either recorded row**. The outside scan
at policy.py:8302-8376 calls `_defer_town_errand("home-scan", "outside-scan")`
at policy.py:8334. Both recorded claims contain the corresponding
`errand_deferred` row with the correct holder id and `token_would_admit: false`.
The OFF gate records this but returns false (policy.py:5861-5885); ON refuses
the producer. The scan is foreign work and must remain deferred under ON.
No new router catalogue dependency is justified by these records.

The false positive is at policy.py:6865-6870: shadow judges the emitted OFF
key as if it survived ON entry, without considering the gate actually
consulted before producing it. The planned correction binds the scan entry
verdict to its candidate key and checks this evidence in the shadow census.
An ungated key must still report `ownership:gate-missing:home-scan`.

The supplied first state capture is truncated: its first turn is 1301327,
after the incident turn 1271646; it contains 1858 rows. No board for decision
3106 exists there. The first case can therefore pin the recorded claim/gate
seam, not claim a complete public-policy replay. The second capture contains
the real boards at turns 1419549 and 1419557. Later boards following a changed
ON key will not be consumed (R4).

Running s33_shadow_report on decompressed, frozen decision extracts reports
one `ownership:gate-missing:home-scan` per incident. That script reads plain
JSONL, not gzip; directly passing gzip silently reports zero decisions.

No screen classification or modal continuation is changed (R2). No
EXPECTED_FIRST edits, assertion edits, thresholds, or new policy attributes.

assertion_audit (verbatim): `No changed pre-existing assertions or forbidden test edits.`
changed_preexisting_assertions: []

## Step 2

Step 1 commit: 4d0d89e6.

`_defer_town_errand` now records `producer_key` for the three immediate
knowledge-macro gates (policy.py:5869-5877). `_s33_shadow_verdict` matches that
candidate against the emitted key, holder claim id/family, deferred family,
and refusal verdict (policy.py:6878-6890). A proven entry refusal predicts
ON deferral, rather than pretending the OFF macro survives to ON's final
guard. It still checks the holder's structural continuation. An absent or
unrelated entry remains a gate leak; an invalid holder remains a visible
declaration stop. The actual producer is still refused by the existing gate
at policy.py:8354. No scan is relabelled as router work, no new delegation is
invented, and no final enforcement guard is relaxed.

Both recorded claim/gate seams now produce `would_stop: null`, while
`would_skip_families` still includes `home-scan`. The 9682 public-policy pin
uses the actual 1419557 board, the captured skill_exp response at turn
1418482, and the recorded invalidation precondition. Its OFF result remains
`~9\x1b\x1b`, `home:request-knowledge-scan`; ON refuses that producer and
emits `3`, `shop:approach`, preserving claim 8583 with no violation. The
historical next board is not consumed after this divergence. Fresh and
pickle-restored attachments agree; restoration also covers the new field
inside the existing per-decision deferral record.

The initial new module run failed four subtests, both incident seams before
and after restoration, with `ownership:gate-missing:home-scan`. A single
whole-runtime revert to b24fd077 (tests and fixtures unchanged) failed seven
assertions across the final five tests, with no errors. Restoring the fixed
runtime passed all five tests. Logs: `.live37-revert.log` and
`.live37-restored.log` in this worktree. The report script on recomputed
one-row shadow outputs reports one decision per incident, no would_stop,
no gate_leaks, and home-scan in would_skip. Original recorded logs remain
unchanged and still describe the old shadow implementation.

### Authorized verification

One module per process, codex runtime Python, `PYTHONPATH=src;tests;scripts`:

| Module | Result |
| --- | --- |
| tests.test_live37_home_scan | 5 passed |
| tests.test_s33_shadow_recorded | 6 passed |
| tests.test_live23_home_cycle | 7 passed |
| tests.test_live32_shop_leave | 4 passed |
| tests.test_policy_home | 184 run, 4 existing skips, OK |
| tests.test_town_progress_invariant | 22 passed |
| tests.test_ownership_s2a_classification | 16 passed |
| tests.test_test_fakery_lint | 13 passed |

Total: 257 tests run, 4 existing skips, no failures.

User-decision conformance: 「町の用事は同じ順位（横取り禁止）」 and
「最後まで歩き切る」 are preserved by the printed ON result `3`,
`shop:approach`, same holder 8583. Adopted rule 2.1 states 「OFF は数えるだけ、
ON はこの skip が効く」: the public OFF key/reason remains recorded, whereas
the public ON scan is refused. There is no release added to hide a handoff,
and the final-only foreign-output pin still reports the gate violation.

Authorized stuck/withdraw exceptions, each in its own process:

| Fixture/mode | Result |
| --- | --- |
| stuck OFF | 4 rows; c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 |
| stuck S3.3 | no first divergence; trajectory_defect null |
| withdraw OFF | 34 rows; a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 |
| withdraw S3.3 | first difference (3,3,ESC,equipment-transaction:catalogue-leave-for-scan); trajectory_defect null |

`git diff --check` passed. No pre-existing assertions were changed; no
EXPECTED_FIRST edit. The assertion audit before Step 2 commit is recorded
below after staging.

Step 2 assertion_audit (verbatim):
`No changed pre-existing assertions or forbidden test edits.`
changed_preexisting_assertions: []

### Pending for Claude (not run)

Per the DO-NOT-RUN block: scripts/test_parallel_runner.py,
scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py,
scripts/mutation_battery.py; tests.test_cli, tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states; long recorded tour/town/
overweight replays; town producer purity parts; full-fixture
scripts/first_divergence_s3_3.py runs; any matching-module sweep/full suite.
Only the explicitly authorized stuck/withdraw fixture runs were executed.

### Remaining evidence limitation

Decision 3106 has a real recorded claim/entry-verdict pin and ON gate-refusal
pin, but a full public-policy/route-continuation replay remains unproven:
the supplied state capture lost turn 1271646. No state, screen, or successful
continuation is fabricated to cover that loss. Decision 9682 has the public
OFF-shadow/ON proof. This is a shadow false-positive correction; the ON
producer gate already refused these foreign scans before this patch.
