# live32 — step 1 investigation

Base: `92b455ad`; worktree: `bot-client-decl-r3b`, branch `decl-r3b`.
Frozen evidence: `tests/fixtures/live32-shop-leave/provenance.json` (source and fixture hashes).

* At 4216 the outside route producer `_shopping_approach_key`
  (`src/hengbot/policy_shop.py:4797-4907`) probes the captured shelf via
  `_atomic_shop_transaction_key`. Its `_shop` call sets `shop:leave`
  (`policy_shop.py:4993`, `:4370`); composition returns None at `:5161`
  without restoring the caller's reason. The fallback emits direction `1`
  with a store-router Reach/route offer, but reason attribution selects
  shop-sell. `_claim_goal` falls through the `shop:leave` Observe typing
  (`claim_goal_typing.py:229`, `policy.py:4127`) and opens an unbound,
  generic store-operation Observe. The offer does not match shop-sell;
  execution is absent. Recorded claim 3266 confirms both facts.
* At 4217 `_town_special_key` takes `_terminal_equipment_blocker`
  (`policy_town.py:5723`, `policy.py:13716`) and `_town_blocked_key`
  (`policy_town.py:4873`) emits the town-plan result
  `town:blocked:equipment-calibration-required`
  escaped the final gate against that phantom holder. The final deferred row
  names that exact pre-stop reason. `_enforce_town_claim_result`
  (`policy.py:7052-7054`) produces `ownership:gate-missing:town-plan`.
  `_refuse_no_progress_cycle` is the last decorated call, not evidence that
  it detected a cycle: its only refusal result is `livelock:exhausted`
  (`policy_helpers.py:144`), which is absent. It saw the outside board at
  (46,83), turn 1140181, same pack/equipment as the leave seam. The unchanged
  equipment-calibration terminal reached the gate. Its owner-boundary test
  (`policy_helpers.py:124-134`) is false for that terminal, so no recurrence
  can trigger its refusal on this row. The detector decoration
  explains the rung and detectors owner on the stop row.
* `_next_required_store_type` recomputes live needs (`policy_shop.py:1040`),
  filters ledger refusals (`:1066`), then rebuilds the
  ordering projection (`:1086`). The recorded categories drop quest-speed /
  black-market at 6 and launcher-enchant at 4, leaving equipment-catalog /
  equipment-work at Home. Store 6 was marked attempted at turn 1140173 in
  the incident capture: both quest-speed and black-market require that it
  not be attempted (`policy_town.py:2785`, `:2886`). Launcher-enchant is
  optional and requires an actionable departure supplier / ready departure
  (`policy_town.py:2867`, `:3241-3246`); the recorded calibration-required
  blocker leaves departure unready and that optional registration gone.
  `_build_town_errand_plan` records the changed next
  stop (`policy_town.py:3513`). This is not permission to abandon an actual
  route: the adopted 2026-09-27 user decision requires walking to arrival.
  A phantom sale must never become its holder; the real route remains held
  until arrival. Rebuilding the future-stop projection alone needs no stop
  or fabricated operation completion.
* OFF `_s33_shadow_verdict` on this same recorded gate seam predicts
  `ownership:gate-missing:town-plan` (`policy.py:6850-6853`), agreeing with
  ON `_enforce_town_claim_result`. It is pure (pickle identity checked).
  Thus this evidence does not demonstrate a shadow-verdict defect; absence
  of this report in the earlier shadow session does not establish that the
  same sequence occurred there.

Step 1 pin: historical gate verdict agrees; production route-ownership pin
fails before the fix (`shop-sell` instead of `store-router`). No EXPECTED_FIRST
change and no live runtime changes.

## Step 2 fix and verification

`policy_shop.py:5156-5160` restores the caller's reason only when S3.3 ON
rejects an outside shelf composition without selecting a command. The route's
existing Reach slot and execution offer now match its owner. OFF retains the
recorded `1 / shop:leave`; real composed purchases and observed-stop terminals
return earlier and keep their own reasons. No new persistent attributes.

Recorded seam replay (also after pickle restoration):

* 4216: live `1 / shop:leave`; corrected ON `1 / shop:approach`, a store-router
  Reach to (45,84), with `route.resume` and a posted identity.
* 4217: live `None / ownership:gate-missing:town-plan`; corrected ON route
  continuation `9 / shop:approach` despite rebuilding `[7,6,4]` to `[7]`.
  The original holder id/goal survive, final gate admits it, violation is None.
  OFF shadow adjudication on that corrected declaration returns no stop, the
  same as ON admission. Historical phantom-holder shadow returns the recorded
  gate stop. Neither shadow call mutates the policy.
* Replay stops at the first changed key (4217). This is a focused production
  route/rebuild/gate seam attachment, not an exact restoration of the complete
  4,217-decision live lifetime. The two-hour live run was not restarted.
* User decisions: 「最後まで歩き切る」 is satisfied by preserving the original
  entrance Reach; 「町の用事は同じ順位（横取り禁止）」 is satisfied by keeping the
  same claim id and admitting its own route key. There is no posted sale to
  complete, release or transfer. R2 does not require a new screen capture:
  this changes reason attribution, not UI classification or continuation.

Single revert of the five runtime lines: module fails 2 of 4 tests (wrong
shop-sell owner, and `ownership:declaration-missing:shop-sell` instead of the
recorded-board route continuation). Restored fix passes all four.

Exactly the requested modules were run separately:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_live32_shop_leave | 4 | PASS |
| tests.test_s33_shadow_recorded | 6 | PASS |
| tests.test_live22_bounty | 12 | PASS |
| tests.test_live23_home_cycle | 7 | PASS |
| tests.test_declarations_r14 | 2 | PASS |
| tests.test_town_progress_invariant | 22 | PASS |
| tests.test_ownership_s2a_classification | 16 | PASS |
| tests.test_test_fakery_lint | 13 | PASS |

Total 82 tests. The requested r14 module includes its overweight seam measurement.
Additional explicitly authorized fixture checks used
`scripts/first_divergence_s3_3.py stuck s33` and `withdraw s33`; each checks its
complete OFF hash before ON:

* stuck: OFF `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`,
  four rows, ON no divergence, trajectory_defect None.
* withdraw: OFF `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`,
  34 rows, ON first difference `(3,3,ESC,equipment-transaction:catalogue-leave-for-scan)`,
  trajectory_defect None. EXPECTED_FIRST unchanged.

Assertion audit against `92b455ad`, verbatim:
`No changed pre-existing assertions or forbidden test edits.`
`git diff --check` passes.

## Pending for Claude — DO NOT RUN items

`scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`,
`scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`;
`tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`,
`tests.test_absorbing_states`; standalone long recorded tour/town/overweight
replays, town-producer-purity parts, full-fixture sweeps of
`scripts/first_divergence_s3_3.py` beyond the expressly authorized checks,
and any all-matching-module/full-suite sweep. No Claude review was invoked.

Commits: step 1 `17d70c50`; step 2 is the commit containing this final report,
the runtime correction and the additional rebuild pin.
