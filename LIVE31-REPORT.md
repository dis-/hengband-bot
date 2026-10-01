# live31 — diagnosis (step 1)

Base: dcb3fed7; worktree: bot-client-decl-r3b, branch decl-r3b.
Step 1 commit: 0193f0b4.
Step 2 implementation commit: bfd840d7.

Recorded evidence: incident-20261001-1235-calibration-restore-target-absent-2.state.jsonl.gz
and .decisions.jsonl.gz, copied without changing boards into the live31 fixture.
No game, live bot, logs, or other worktrees were modified.

The outstanding signature is `('岩石溶解の魔法棒 (25回分)', 65, 6)`.
At turn 1086352, inventory e contains count=3, charges=pval=25. The deposit
macro is `dhdg2\rdf2\rde3\rdddcdb10\rda13\r`. At terminal turn 1086783,
Home slot 14 contains the same kind with count=4, charges=pval=28 and name
`岩石溶解の魔法棒 (28回分)`. These mappings were printed directly from the
recorded JSON. This is pooled wand charge/count merging, not consumption.
The first and second historical restore macros leave precisely this debt.
An unchanged-code replay printed the same two macros and then
`town:blocked:calibration-restore-target-absent`.

The extra `way` equips the West-country mace; `wb` equips the Pattern war
hammer. Neither is the missing wand. `town:recover` posts `R&\r`, a rest,
not a use command. The final inventory contains neither the wand nor its
charge-renamed equivalent; the final Home catalogue positively contains it.

Existing identity handling before the fix:

| Change in calibration window | Current handling / location |
| --- | --- |
| Identification, awareness, newly revealed flags or bonuses | Misses: equipment_optimizer.py:356-385 hashes name and knowledge fields; policy_home.py:116-130 compares this digest. |
| Merge/split stack count | Handles count and staff `Nx` name prefix: equipment_optimizer.py:400-404; owed quantities: policy_home.py:2031-2051. |
| Pooled wand charges when merging/splitting | Misses: name and pval both hashed at equipment_optimizer.py:364,383. This incident is positive recorded evidence. |
| Inscription / printed annotations | Misses name changes: equipment_optimizer.py:364. |
| Charge use / recharge | Misses device name/pval changes. No charge-use command in this recorded calibration window; do not infer consumption from absence. |
| Light fuel / recharge timeout | Light name ignored: equipment_optimizer.py:362; timeout is excluded. |
| Wear/wield/takeoff, inventory relabel | Positive worn/carried observation: policy_home.py:73-109; physical slots excluded from move identity. |
| Consumption/destruction | No general positive command/effect reconciliation here. Restore batch observes actual quantity gain at policy_home.py:2223-2239. A disappeared item remains a typed terminal at policy_home.py:2503-2534; rest alone cannot prove consumption. |

The repair must compare observed physical properties with their transport
semantics: quantities and pooled resources can change; per-staff charges still
distinguish live28's debts. Previously known equipment properties cannot be
discarded just because identification or a printed annotation changes.

## Step 2 — movement reconciliation

`policy_home.py:122` now uses the original deposited observation (registered at
`policy_home.py:1470`), rather than a digest of the display string. The same
matcher is used for shelf selection, carried/worn reconciliation and actual
withdrawal observation. It keeps known physical properties, requires previously
known flags to remain present, permits further knowledge and annotations, and
separates pooled device resources from per-copy staff charges. No new threshold
or special guard for this sequence was introduced. OFF keeps the old matcher.
`policy.py:2317-2318,2609-2612` initializes the new checkpoint fields.

| Identity change | Reconciliation after repair |
| --- | --- |
| Identification / increasing knowledge | Compare available kind and previously known properties at policy_home.py:134-168; fully-known evidence cannot regress. An unidentified hidden sval remains distinguished by its recorded flavour (lines 141-144), never by a guessed kind. |
| Stack merge/split | Count is not identity; the actual deposit quantity remains the debt. Original observations are retained at policy_home.py:1470. Batch gains are checked at policy_home.py:2282-2288. |
| Inscription / printed known-flag annotations | Strip brace annotations for physical-name comparison at policy_home.py:136-140,170-174; known fields and flags still constrain the match. |
| Wand charge pooling, rod resource changes | Pooled pval is excluded at policy_home.py:160-162 and printed device resources are excluded at lines 138-140. This handles both Home merge and subsequent split. |
| Staff charge use | Staff charges remain per-copy evidence (policy_home.py:163-164), preserving live28. A used staff is not silently substituted for another charged staff. Deposited Home items cannot be used; after a positively observed restoration the debt is already discharged before a later use. |
| Fuel / timeout | Light fuel is excluded at policy_home.py:160-162,170; timeout never enters this identity. |
| Wear/wield | Positively observed possession discharges the debt at policy_home.py:75-113, with typed `calibration-restore:worn` or `calibration-restore:carried` at lines 94-97. |
| Consumption/destruction | Absence is not positive evidence of consumption. A confirmed take discharges debt as `calibration-restore:withdrawn` at policy_home.py:2320; later consumption cannot reopen it. Items still deposited at Home cannot be consumed by rest or an inventory use. The truly-absent live19 pin remains unchanged. |

The original incident source lines 7113/7114 show the predeposit wand; source
line 7187 shows final Home slot 14. They are fixture lines 12/13 and 86.
The provenance JSON records the source/fixture hashes and every source line.

The fresh first divergence is the original macro with `py3\r` inserted after
`pz2\r`: it now takes three wands from the four-wand/28-charge shelf. The test
constructs their three-wand/21-charge response and the remaining one-wand/
7-charge shelf from the pre-decision board, then observes both restore batches
to completion. It does not use historical boards as effects after divergence.
Independently reconstructed historical intents reach the real terminal board;
the new recovery command there is `5po3\r\x1b`, versus the live no-key terminal.
The constructed response discharges the last debt and ends calibration.

New pins also retain distinct hidden mushroom flavours, reject a changed known
weapon bonus, accept annotation/knowledge growth, record worn outcomes, and
cover new and old checkpoint defaults. Existing live19/live28 assertions and
EXPECTED_FIRST were not edited. R2 adds no screen requirement here: no screen
classification or modal continuation was changed, and no UI screen was faked.

## Verification

Python: C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe;
PYTHONPATH=src;tests;scripts, PYTHONUTF8=1. Each module ran in its own process.

| Authorized module | Tests | Result |
| --- | ---: | --- |
| tests.test_calibration_live31 | 6 | PASS |
| tests.test_calibration_live19 | 11 | PASS, existing pins unchanged |
| tests.test_calibration_live25 | 6 | PASS |
| tests.test_calibration_live28 | 3 | PASS, existing pins unchanged |
| tests.test_policy_calibration | 75 | PASS |
| tests.test_calibration_restore_deposits_recorded | 6 | PASS |
| tests.test_policy_home | 184 | PASS, 4 existing skips |
| tests.test_live23_home_cycle | 7 | PASS |
| tests.test_ownership_s2a_classification | 16 | PASS |
| tests.test_test_fakery_lint | 13 | PASS |
| Total | 327 | PASS, 4 skips |

The single matcher revert to dcb3fed7 runs the new module: six tests, three
failures. The original first macro omits `py3\r`; the terminal board emits
`5` instead of `5po3\r\x1b`; annotation reconciliation fails. The script's
finally block restores the source byte-for-byte. This is one actual revert
run; an earlier script invocation failed before changing source due to CRLF
boundary matching, which was corrected before running the actual check.

| Short recorded fixture | OFF digest | S3.3 result |
| --- | --- | --- |
| stuck | c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | No divergence; expected null |
| withdraw | a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | Exact ruling #9 row: (3, 3, ESC, equipment-transaction:catalogue-leave-for-scan) |

Both modes have no declaration gap or mismatch rows and no trajectory defect.
The fixture runner reports existing detector missing declarations (stuck: one
in both modes; withdraw: two in OFF, zero before the S3.3 first divergence).
EXPECTED_FIRST remains unchanged. The four JSON reports and ten module logs
are under reports/live31-*. PowerShell stderr capture added NativeCommandError
formatting to some passing logs; every reported process exit code was zero.

Assertion audit (before each commit):
`No changed pre-existing assertions or forbidden test edits.`
No pre-existing assertion was changed, removed or weakened. `git diff --check`
passed. No live bot or game was run. The unrelated pre-existing untracked
`.live8b-revert.py` was left untouched.

Pending for Claude under the inherited DO-NOT-RUN block (not executed here):
scripts/test_parallel_runner.py, scripts/test_timing_runner.py,
scripts/hunk_guard.py, scripts/verify_scope.py, scripts/mutation_battery.py,
tests.test_cli, tests.test_policy_town, tests.test_policy_shop,
tests.test_absorbing_states, long recorded tour/town/overweight replays,
town producer purity parts, full-fixture runs of scripts/first_divergence_s3_3.py
(only the explicit stuck/withdraw exception ran), and any all-matching-module
sweep. No additional test module or gate script was run.
