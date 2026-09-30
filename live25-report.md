# live25: calibration restore weight limit

Base: `70b9772b`, branch `decl-r3b`. Evidence is the read-only live25
`incident-20261001-0812-calibration-restore-weight-limit` capture.

## Step 1: recorded cause

References below are decompressed JSONL line numbers in that capture's state log.
The committed fixture preserves them as `live25_source_line`.

* state:3991 (688489): total carried weight 2247, limit 1700.
* state:4002 (688498): after first overweight deposit, weight 2049.
* state:4013 (688511): after both overweight deposits, weight 1004.
* state:4019 (688516): after calibration pack deposit, weight 404.
* state:4037 (688636): after re-equipping, weight 404, pack empty.
* state:4051 (688644): restore response weight **1700**, exactly the limit;
  the terminal is raised because the next owed item cannot fit, rather than
  because the current board exceeds the limit.

The same equipment occupies the same slots before and after calibration
(state:4013,4037,4051), with total weight 404. Lantern fuel decreases by ten
turns, which does not change its weight. Level 21 and all stat indices `(27,0,5,20,24,3)` are
identical. The 72 bullets were carried before calibration; they were not a
merged-stack over-withdrawal. The actual cause is that overweight deposits
made while calibration's phase is `deposit` become restore debt too.
At the base commit, `policy_home.py:1316` registers all deposited quantities in that phase,
including the prior overweight disposal. The restore then brings back spare
armor/weapons (870 weight) and bullets (360), plus supplies, filling the limit.
These are heavier than the 1004 board because that board had already stashed
the armor, weapons, devices and supplies.

At the base commit, `policy_home.py:19` retains every restore signature after debt discharge;
`policy_home.py:1073` excludes matching items from overweight disposal during
enforced restoration. The restored unidentified mushroom, recall scrolls, devices, spare
armor/weapons and bullets are all protected. Remaining restore debt cannot
fit; `policy_home.py:1858` emits the weight-limit terminal before withdrawal.
Protection makes arbitrary deposit/withdraw cycling impossible, but the debt
must distinguish required restoration from excess intentionally kept in Home.

## Step 2: implemented fix

`src/hengbot/policy_home.py:1364` separates temporary calibration deposits
from overweight disposal: only the deposited share of the existing retention
reservation becomes restore debt. Excess, including the overweight-disposed
armor and scythe (630 weight), stays in Home under calibration's accounting.
The two weapons temporarily deposited after weight cleanup still return.

`src/hengbot/policy_home.py:25` plans supply withdrawals against the complete
projected owed pack, using the existing retention authority. It restores
`min(owed, retained)` and releases the rest as `kept_in_home` without taking
it out first. Missing equipment remains debt; utility/identification devices
retain their physical restoration obligation. No new threshold is introduced.
The existing weight-limit stop remains when the retained debt cannot fit.

`src/hengbot/policy.py:12905` exposes the quantities kept in Home in calibration
diagnostics. Old checkpoints acquire the new accounting lazily; the field
survives checkpoint restoration and resets at the next calibration. Both are
pinned in `tests/test_calibration_live25.py`.

The recorded entrance goes through production observation to seed recall
depth 18. Required supplies stay strict: recall **8**, teleport **13**, cure
critical **10**, bullets **72**, oil **5**, healing **4**, speed **1**.
One restore macro completes at weight **1229 / 1700**, with no deposit queued.
The recorded restored pack is heavier because the legacy macro restores
the 630-weight armor/scythe and other intentionally stashed excess.

The pin compares the recorded deposit macros through the real deposit producer,
then calls the real restore composer and observation/reconciliation paths.
After the changed restore command, its pending quantities construct a
counterfactual pack/Home response; subsequent historical boards are not treated
as responses to the new command. This is replay verification, not a live game run.

Single revert check: reverting the three implementation files to `70b9772b`
reproduced `town:blocked:calibration-restore-weight-limit` in all four
OFF/ON × checkpoint cases. Restoring the implementation passed all five new
tests. See `live25-revert-check.txt` and `live25-pin-results.txt`.

## Completed verification

Each module ran in its own normal Python process (`PYTHONPATH=src;tests;scripts`).

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_calibration_live25 | 5 | OK |
| tests.test_calibration_live19 | 10 | OK |
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

Stuck OFF hash: `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`;
S3.3 first divergence: none.
Withdraw OFF hash: `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`.
S3.3 first divergence is at index 3 (`~9 ESC` versus `ESC`, catalogue-leave-for-scan),
earlier than the frozen EXPECTED_FIRST index 20. The same result was reproduced
on **unchanged main 70b9772b** during the revert window: it predates live25.
EXPECTED_FIRST was not edited. This existing mismatch remains for Claude.

Assertion-change audit exited zero. Its full output, before/after declarations,
and quoted user clauses are preserved verbatim in `live25-event.json`.
No existing assertion was removed or loosened. live19 now asserts exact retained
quantities and that unneeded torches stay in Home; the shelf count 57, kept
quantity 5, OFF full-stack behavior, weight bounds, capacity stop, historical
restore protection and foreign-producer exclusion remain explicit.

Commits: evidence `e3944ad0`; implementation and pins `d3b17a15`.

## Verification scope

Only the expressly requested modules and stuck/withdraw OFF+S3.3 fixtures will
run, each in its own process. No EXPECTED_FIRST values will be changed.
Pending for Claude: `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`,
`scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`,
`tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`,
`tests.test_absorbing_states`, long tour/town/overweight recorded replays,
town producer purity, full-fixture `scripts/first_divergence_s3_3.py`, full suite.
