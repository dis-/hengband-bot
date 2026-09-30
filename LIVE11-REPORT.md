# Live11 shop one-shot declaration repair

## Cause

The captured 919 shelf was General Store (0). At 920 the saved shelf composed
`pf1\r\r\x1b`, but the mutable plan's next visit was Magic Shop (5).
`policy_shop.py` previously attached that operation to whichever visit survived
selection, rather than acquiring the observed shelf's store at composition.
At 921 the board was General Store (0), not a missing store page.

The empty-wait validation in `src/hengbot/policy.py:6600-6636` therefore rejected
the operation: its identity `(0, 920, tail)` did not equal the visit's
`(5, 920, tail)`, and the actual board store 0 did not match visit store 5.
The declaration also remained `acting` without a posted operation reference;
the visit's posted sequence was shelf observation 919 instead of entry 920.
This was not a legitimate change of the purchased store or item.

## Repair (step 1: 338c7ee1)

`src/hengbot/policy_shop.py:5006` reacquires the observed store for the composed
operation after selection, so plan advancement cannot redirect its visit.
Entry posting now acknowledges the declaration and uses the entry decision
sequence. Tail release uses the tail decision sequence for its posted reference.
`src/hengbot/policy.py:6250` advances the posted entry declaration when the matching
fresh store page opens, dispatching its already composed tail with the same work
identity. A different store or work identity still stops visibly.
No new policy attributes or thresholds were introduced.

## Pins (step 2)

`tests/test_live11.py` uses the recorded 919-921 decisions and state boards.
The positive pin starts with the recorded next-store visit, binds General Store,
acknowledges entry, preserves a lagged outside wait, dispatches the exact recorded
tail at 921, and acknowledges its inventory/gold observation declaration.
The negative pin replaces the observed page with a truly different store and
asserts `ownership:declaration-stale:shop-buy`. Both run before and after pickle
checkpoint restoration.

Each pin has one revert check: reverting step 1 fails the positive pin at the
store binding; reverting the new changed-store guard fails the negative pin
because it returns an empty wait instead of stopping. Production files were
restored after each check.

## Verification

Every module ran in its own codex-runtime Python process with
`PYTHONPATH=src;tests;scripts`.

| Verification | Result |
| --- | --- |
| tests.test_live11 | 2 passed |
| tests.test_shop_one_shot | 51 passed, 1 skipped, 1 existing failure |
| tests.test_live8 | 11 passed |
| tests.test_declarations_r3b | 15 passed |
| tests.test_test_fakery_lint | 13 passed |
| stuck s33 | 4 OFF rows, no divergence, no declaration gaps/mismatches |
| withdraw s33 | 34 OFF rows; expected divergence at index/sequence 20, no trajectory defect or declaration gaps/mismatches |

The existing failure is
`ShopOneShotTest.test_live_released_one_shot_watch_keeps_its_visit_in_town_bar`.
It expects an empty wait after two `choose_key` calls without acknowledging the
entry/tail posts; the declaration guard returns a stale stop. The exact same
failure was independently reproduced with both production files restored to
baseline 77b5ea8a. Its assertions and setup were left unchanged.

`EXPECTED_FIRST`, live checkout, logs, game, live2b, and the pre-existing
untracked `.live8b-revert.py` were untouched. No prohibited runner or full suite
was executed.
