# catcycle investigation (base 0d6349a7)

Step 1: the registered equipment-txn catalogue holder is supposed to send the
outside scan: `policy.py:6805-6842` already returns HOME_KNOWLEDGE_MACRO outside
and declares `equipment:acquire-home-catalog` / `home.catalogue.acquire`.
The declaration alone does not dispatch a producer. `policy.py:8825-8827` calls
it only inside Home with cross-area or S3.3 sequencing enabled; the generic
holder dispatcher at `policy.py:6392-6393` belongs to enforced town admission.
The earlier public choose-key branch at `policy.py:7435-7477` instead approaches
Home on an outside entrance with stale knowledge and a nearly full warrior pack.
It replaces the continuation with `home.approach-for-equipment-catalog`, so the
partial page leaves again. The ordinary outside scan at `policy.py:8319-8354`
also excludes every store entrance; it cannot rescue this board.

Recorded decisions 1063-1125 are frozen with original source line indices and
source hashes in tests/fixtures/catcycle/provenance.json. Rows 1064,1066,...1122
are 30 catalogue ESCs; rows 1065,1067,...1123 are 30 re-entry 5s. The supplied
63-row window includes the initial travel and rows 1124/1125; it is not 63 full
enter/leave pairs. All 32 Home boards in the cycle window show page_top=0,
stock_num=63, and 52 visible items. Thus it revisits the same partial first page,
not successive pages. Any partial page enters the same incomplete-page branch.

Why 1124: row 1123's equipment-txn claim 720 is retired. Retirement is applied
at `policy.py:4674-4675`; `_claim_errand_hold` (`policy.py:5620-5626`) accepts
only open holders. After the recorded 5 opens Home, the retired holder cannot
win the catalogue branch. The routed, invalidated page then reaches the ordinary
open-Home scan (`policy.py:9037-9059`) under a new home-scan claim 721. Row 1125
records that claim completing home-knowledge-current, followed by route-unfulfilled.

Required behavior: "the registered catalogue work, after leaving for the complete
list, posts the knowledge scan as its own next step (declared by the same owner),
adopts the catalogue, and only then re-enters Home". Ruling #9's withdraw row
must remain `(3,3,ESC,equipment-transaction:catalogue-leave-for-scan)`; no changes
to EXPECTED_FIRST are authorized.

No pre-existing assertions changed. No runtime/game/other-worktree writes.

Step 1 assertion_audit (verbatim, before commit 5136a4f0):

```text
No changed pre-existing assertions or forbidden test edits.
```

Step 2 fix: `policy.py:7399` dispatches the registered catalogue continuation
on an outside town board before ordinary Home acquisition. It reconciles the
observed exit through the existing StoreVisit leave setter, asks the same
equipment-txn producer for the scan, and completes that holder when the
catalogue is adopted before falling through to any later work. The producer
(`policy.py:6833`) observes an already posted scan without sending `5` at the
entrance: the awaiting declaration retains the accepted operation_ref.
No new policy attributes, thresholds, or switches were introduced.

The new `tests.test_catcycle` pins read frozen decisions, posted characters,
partial-page/outside boards, and the earlier skill_exp response from this same
incident. The public requirement pin starts outside Home, posts the unchanged
recorded travel and ESC, then stops at its first changed key (1065: historical
`5` / travel-home:await-entry versus fixed `~9` / catalogue-request-knowledge).
It asserts the same claim id/owner and no violation, also after checkpoint
restore. Adoption is independently attached to the genuine recorded 1124 ~9
reply; it is not passed off as the effect of the changed 1065 key. The reply
contains 63 items; the holder completes home-knowledge-current before subsequent
outside work. A supplemental delayed-reply seam verifies an awaiting declaration
with the posted scan's operation_ref and no re-entry command.

Verification performed (one module per Python process):

| Module | Result |
| --- | --- |
| tests.test_catcycle | 4 passed |
| tests.test_live23_home_cycle | 7 passed |
| tests.test_unaffordable_claim_tour_recorded | 7 passed, 672.751 seconds |
| tests.test_live37_home_scan | 5 passed |
| tests.test_town_progress_invariant | 22 passed |
| tests.test_ownership_s2a_classification | 16 passed |
| tests.test_test_fakery_lint | 13 passed |
| tests.test_policy_home | 184 run, 3 failures, 4 skips; baseline comparison below |

stuck OFF and S3.3: 4 OFF rows, SHA
`c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`,
no ON difference or trajectory defect. withdraw OFF and S3.3: 34 OFF rows,
SHA `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`,
ON first difference `(3,3,ESC,equipment-transaction:catalogue-leave-for-scan)`,
trajectory_defect=null. Full measurements are the four catcycle-*-off/s33.json
files in this report directory. EXPECTED_FIRST is untouched.

Pending for Claude (DO NOT RUN here): scripts/test_parallel_runner.py,
scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py,
scripts/mutation_battery.py; tests.test_cli, tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states; long town/overweight recorded
replays, town producer purity parts, full-fixture first_divergence_s3_3 runs
except the explicitly authorized stuck/withdraw cases, and matching-module
sweeps. The tour test module alone is expressly authorized by this task.

Single revert check: replaced only policy.py with the git blob at 0d6349a7
once, ran the new pin module in its own process, and restored the fixed bytes
in finally. Four tests ran and 8 subcase failures exposed `5` /
equipment-transaction:travel-home:await-entry instead of `~9` /
equipment-transaction:catalogue-request-knowledge. Full output:
catcycle-single-revert.txt. The frozen-cycle evidence test itself stays green.

During that same single revert, a separate process ran just the three failing
Home tests. All reproduced identically on the baseline (catcycle-home-baseline.txt):
test_production_executor_home_atomic_deposit_enters_then_posts_once (line 3348,
SendResult.TERMINAL); test_matches_game_weight_limit_and_preserves_plain_plus_highest_ammo
(line 497, [14,0,27] versus [72,0,27]);
test_overweight_rearm_tracks_successful_deposit_progress_to_weight_limit
(line 709, 3 versus 4 passes). These are existing failures, pending for Claude;
no assertions or unrelated behavior were modified to make the module green.

Step 2 assertion_audit (verbatim):

```text
No changed pre-existing assertions or forbidden test edits.
```

User-rule conformance evidence: "登録済みの依頼を優先" is pinned by the same
equipment-txn id owning ESC then ~9, with no foreign-owner handoff. The task's
"declared by the same owner" keeps the existing catalogue work_id rather than
opening a new home-scan errand.
The task's "adopts the catalogue, and only then re-enters Home" is pinned by
the real 63-item response closing that holder before the next outside decision.
There is no changed-screen classification or new UI macro.
