# live14 regression repair

Worktree: `C:\hengband\bot-client-decl-r3b`, branch `decl-r3b`.
Starting HEAD: `4f85e04f`. No live runtime, other worktree, test expectation,
or `EXPECTED_FIRST` was modified. No new policy attributes or thresholds.

## Bisect

For each named pin independently, binary search over the ordered commits from
`c2db64f5` through `7e1d2499`, using the existing pin with each revision's three
changed production modules. Temporary replacements were restored in `finally`.
Both pins: `c2db64f5` PASS, `7e1d2499` FAIL, `77b5ea8a` PASS,
`dbabcd42` FAIL, `338c7ee1` FAIL. First bad commit for both is
`338c7ee17ec3b2e48bd4c4844f29760cc1034cf8`; last good is `77b5ea8a`.

## Failure 1: fresh Home catalogue one-shot purchase

Pin: `tests.test_policy_shop.ProbePurityIncidentPinsTest.test_pin_fresh_home_catalogue_composes_one_shot_purchase`.

Cause: `338c7ee1` changed `policy_shop.py` composition to stamp the current
decision as `posted_sequence`. The next outside decision consequently takes
the entry-observation branch at `src/hengbot/policy.py:7386`, which formerly
always returned reason `store:entry-await-observation`. This is a staged
shop purchase, whose established reason is `shop:one-shot-in-flight`.

Fix: retain that reason for posted shop-buy/shop-sell operations in this
branch. Keep the empty unsent key and the page-observation barrier, and keep
the generic entry reason for other entries. Commit: `1b187af6`.

## Failure 2: observed Magic page after town-plan advance

Pin: `tests.test_town_progress_invariant.TownProgressInvariantTest.test_live_shaped_magic_observe_then_compose_ignores_advanced_plan`.

Cause: the acquisition introduced by `338c7ee1` in
`src/hengbot/policy_shop.py:5025` meets a foreign town-plan visit still marked
LEAVING, composed ESC, posted sequence 253 and posted turn 273512, with no
posted operation. `src/hengbot/emit_ownership.py:49` classifies it as
`leaving-with-posted-sequence`, so `town_arbiter.py:239` refuses the observed
Magic shelf and composition returns None. The composable outside snapshot
already confirms that the prior ESC left the shop.

Fix: at `src/hengbot/policy_shop.py:5012`, close only that completed ESC exit
before acquisition, requiring LEAVING, composed ESC, no posted operation,
and an outside observation at or after its posted turn. Preserve the observed
shelf acquisition and live11 declaration continuation. Commit: `1175b841`.

## Verification

One test module per process, using Codex runtime Python with
`PYTHONPATH=src;tests;scripts`:

| Check | Result |
| --- | --- |
| Named policy_shop incident pin | 1 PASS |
| tests.test_town_progress_invariant | 22 PASS |
| tests.test_shop_one_shot | 53 run, 1 skipped, PASS |
| tests.test_live8 | 11 PASS |
| tests.test_live11 | 2 PASS, including checkpoint and changed-store rejection |
| tests.test_test_fakery_lint | 13 PASS |
| Single revert of reason fix | Original reason mismatch caught; restored PASS |
| Single revert of exit fix | Original None vs WAIT_KEY mismatch caught; restored PASS |
| git diff --check | PASS |

The inherited DO NOT RUN block explicitly forbids the full
`tests.test_policy_shop` module, so only its requested incident pin was run.
No full suite, prohibited runner, or gate script was run.

The live14 exception permits the two S3.3 fixtures below:

| Fixture | OFF rows/hash | S3.3 result |
| --- | --- | --- |
| stuck | 4 / c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | No first divergence; trajectory_defect null |
| withdraw | 34 / a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | First divergence index/sequence 20, shop:travel with ESC-backtick-n-percent-dot, exactly EXPECTED_FIRST; trajectory_defect null |

Both fixtures had empty declaration gap and mismatch lists. These runs stop
at the first ON/OFF difference and do not claim validation beyond that point.
