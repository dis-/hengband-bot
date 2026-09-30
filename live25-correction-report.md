# live25 correction from 14e49a53

The CORRECTION overrides the unconditional retained cap in step 2. Full owed
restoration that fits the weight limit now restores every owed quantity.
Only projected overweight restoration caps supply debt at the existing retention
quantity, in decreasing removable-weight order, leaving surplus in Home under
calibration ownership. Required quantities remain unchanged and the existing
weight-limit terminal remains when required restoration cannot fit.

Implementation: `src/hengbot/policy_home.py:44` projects equipment plus the current
pack plus all physically available outstanding debt, and returns without
altering debt when weight is at or below the limit (also when no limit is known).
No new persisted attribute, threshold, screen classifier or UI continuation.

The complete pre-live25 `tests/test_calibration_live19.py` was restored byte for
byte from d3b17a15's parent. Its ten tests passed with the original owed-torch
expectations, including OFF full-stack behavior and enforced deposit quantities.

The recorded live25 pin remains. Earlier overweight deposits already leave
excess in Home; remaining full restore debt therefore weighs 1379 / 1700,
including five torches. The previous unconditional cap incorrectly omitted
those 150 weight. The corrected macro is
`5pQ72\rpMpLpx5\rpopl8\rpk13\rpi4\rph10\rpgpc5\r\x1b`.
It completes in one batch with debt empty, no deposit scheduled, and the
intentionally stashed 630-weight armor/scythe remaining in Home. Constructed
command responses remain explicitly counterfactual, not subsequent historical
boards presented as the effects of a changed key.

New recorded-board capacity variants place full owed weight exactly at 1700
and at 1701. These are explicitly labeled equipment-weight counterfactuals.
At 1700 all owed quantities are restored; at 1701 the five unneeded torches
stay in Home and the resulting weight is 1551. Both switches and checkpoint
variants are pinned. The old-checkpoint case now explicitly exceeds capacity
before checking lazy kept-in-Home accounting. Required-only overweight retains
its exact terminal and quantity assertions.

Single revert: replacing only policy_home.py with 14e49a53 fails all four
exact-limit switch/checkpoint variants; restoring the file passes all six
live25 tests. See live25-correction-revert.txt and live25-correction-pin.txt.

Step 1 evidence remains in live25-report.md (commit e3944ad0): source state
lines 4013,4037,4051 show 1004 before calibration, 404 after re-equipping,
1700 at the partial restore, with limit 1700 and identical equipment/stats.
The legacy full restore debt exceeds 1700 because prior overweight deposits
were registered as restoration debt. The terminal was raised for the next
owed item, not because the already restored board exceeded its limit.
Restore-signature protection excluded those items from excess disposal.

Assertion audit against 14e49a53 exits zero. Its verbatim output and every
indexed changed assertion, with the authorizing CORRECTION clause, are in
live25-correction-event.jsonl. The original live19 assertions are restored
as explicitly requested; exact live25 macro/weight expectations now include
owed torches. No EXPECTED_FIRST was changed.

Verification: every specified module in its own process, with
PYTHONPATH=src;tests;scripts and the installed Python 3.13 executable, avoiding
the WindowsApps stub. Results:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_calibration_live25 | 6 | OK |
| tests.test_calibration_live19 | 10 | OK, original expectations |
| tests.test_policy_calibration | 75 | OK |
| tests.test_calibration_crossarea_debt | 5 | OK |
| tests.test_calibration_restore_deposits_recorded | 6 | OK |
| tests.test_calibration_visit_blocked_loop_recorded | 10 | OK |
| tests.test_policy_home | 184 | OK, 4 existing skips |
| tests.test_live23_home_cycle | 6 | OK |
| tests.test_ownership_s2a_classification | 16 | OK |
| tests.test_test_fakery_lint | 13 | OK |
| tests.test_stuck_prompt_staged_tail_recorded | 4 | OK |
| tests.test_home_withdraw_failed_stock_present_recorded | 6 | OK |

Stuck OFF hash c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5;
S3.3 has no divergence. Withdraw OFF hash
a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9;
S3.3 still diverges at index 3 (OFF knowledge request vs ON catalogue exit),
while frozen EXPECTED_FIRST remains index 20. The earlier report reproduced
this on unchanged 70b9772b; this correction retains that existing mismatch.

Pending for Claude (DO NOT RUN): scripts/test_parallel_runner.py,
scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py,
scripts/mutation_battery.py, tests.test_cli, tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states, long tour/town/overweight
replays, town producer purity, full-fixture first_divergence_s3_3.py runs,
full suite. Only the expressly exempted stuck/withdraw fixtures ran.

All 341 tests passed (4 existing skips). Commits before this correction:
e3944ad0 (evidence), d3b17a15 (initial fix), 14e49a53 (initial report).
