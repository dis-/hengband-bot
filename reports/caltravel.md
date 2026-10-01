# Calibration travel audit (base a4e51bf9)

| Branch | Base source | Declaration before fix |
| --- | --- | --- |
| deposit, away from Home | policy_calibration.py:1292-1298 | Generic route declaration only; missing calibration phase continuation. |
| deposit, Home entrance/open Home | policy_calibration.py:1282-1290 | Home composer declares its operation; preserve exact operation binding. |
| restore travel | policy_calibration.py:1472-1495 | calibration, home-reached, calibration.restore-supplies; preserves Home operation declarations. |
| restore excess deposit at Home | policy_calibration.py:1373-1399 | Home operation declaration or calibration restore-excess declaration. |
| restore excess, away from Home | policy_calibration.py:1400-1495 | Falls through restore knowledge/visit/travel, declared as above. |
| strip/equip session Home approach | policy_equipment.py:2240-2245,2133-2146 | calibration when session owned, home-reached, equipment.next-action. |

Recorded decisions: 4676 at 1722292 sends ESC `n(. with calibration:deposit-travel; 4677 at 1722384 returns no key, ownership:holder-silent:calibration. The generic declaration says arrive:45,123 / route.resume; it does not declare calibration.deposit. No checkpoint was captured; the pin must state its attachment wall and compare the first key before consuming its response.

No screen classification or modal code changes are needed. No new persistent attributes are planned. EXPECTED_FIRST remains untouched.

## Fix and recorded proof

Deposit travel now declares `calibration:deposit-travel`, `home-reached`, and
`calibration.deposit` after composing the key, unless the Home executor already
declared the exact operation. The existing restore declaration and the
strip/equip session declaration remain valid. Awaiting declaration validation
and dispatch accept the deposit continuation. OFF holder handling follows the
same declared calibration Home continuation; ON interrupted Home entry returns
to calibration's producer instead of composing a store-router replacement.

The fixture contains verbatim player-turn boards at 1722292 and 1722384 plus
decision facts 4676/4677. Extract it with
`tests/extract_caltravel_fixture.py <read-only log directory>`.
Normalized decompressed SHA256:
`270606f1b1cc4d5cfa3e5b03a0d5899433d9eb84e8ea0a9461b8903aef8404b5`.
The first decision equals the live key and reason before its response is fed.
The second decision is the first divergence; no later recorded board is used.
Attachment and executor walls are documented in the pin. The next decision
uses the ordinary production ladder. OFF/ON and restored/unrestored all return
``ESC `n(.`` / `calibration:deposit-travel`, with a calibration phase declaration.
This proves continuation on the recorded short-travel response, not eventual
arrival at Home.

The single source revert check failed in all four combinations. OFF reproduced
`None` / `ownership:holder-silent:calibration`; ON composed a generic
`store:entry-interrupted-replan` declaration instead of calibration's declared
phase. The source was restored in a finally block. See caltravel-revert-check.txt.

## Verification

- New recorded pin: 1 test, four combinations, PASS.
- tests.test_crash_position_key_recorded: 1 test, PASS.
- tests.test_calibration_live33 + tests.test_calibration_live34: exactly one
  process, 5 tests, PASS in 518.197 seconds.
- tests.test_policy_calibration: 75 tests, PASS.
- tests.test_test_fakery_lint: 13 tests, PASS. An unused lint allowance in
  the new pin was removed after the first lint run reported it as stale.
- tests.test_calibration_live25: 6 tests; four subtests of one test FAIL at line
  220 (`1546 != 1551`). Baseline a4e51bf9 reproduced all four failures with zero
  errors, including checkpoint variants. This is an existing weight-accounting
  assertion failure; no assertion or weight policy was changed. Baseline code
  was loaded from git in an independent process, without changing worktree files.
- stuck OFF/S3.3: OFF hash `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`,
  4 rows, no first divergence, trajectory_defect null.
- withdraw OFF/S3.3: OFF hash `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`,
  34 OFF rows; ON stops at the pre-fixed first difference, index/sequence 3,
  `ESC` / `equipment-transaction:catalogue-leave-for-scan`; trajectory_defect null.
  EXPECTED_FIRST was not edited.

## DO NOT RUN (Claude handoff)

No full-suite runner or gate scripts were run. The forbidden list remains:
scripts/test_parallel_runner.py, scripts/test_timing_runner.py,
scripts/hunk_guard.py, scripts/verify_scope.py, scripts/mutation_battery.py;
tests.test_cli, tests.test_policy_town, tests.test_policy_shop,
tests.test_absorbing_states; long tour/town/overweight recorded replays;
town producer purity parts; full-fixture runs of scripts/first_divergence_s3_3.py
(this round explicitly permits only stuck/withdraw OFF+S3.3); and any all-matching
module sweep. live33/live34 are this round's explicit one-process exception to
the one-module-per-process rule. Game, bot process, exe, live logs and other
worktrees were untouched.

## Audit and commits

Step 1: a188bc9f (branch audit). Before that commit, assertion audit output was:
`No changed pre-existing assertions or forbidden test edits.`
Step 2 adds only new assertions. No changed pre-existing assertions; no new
persistent attributes; no tunable thresholds; no screen changes.
Printed source evidence: `src/hengbot/model.py:338:STORE_HOME = 7`.

Step 2 assertion audit output (verbatim):
`No changed pre-existing assertions or forbidden test edits.`
Step 2 implementation and verification are committed together (the commit containing this report).
