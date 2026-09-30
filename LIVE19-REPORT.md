# Live19 recorded cause (step 1)

Base: main adf8f3e1, branch decl-r3b. Read-only evidence:
`C:/hengband/bot-client/jsonlog/incident-20261001-0317-town-loop-calibration-unrestored-home-withdraw.{decisions,state,posted-characters,ownership-claims}.jsonl.gz`
and `incident-captures/20261001-031647-loop-detected`.

(a) OFF admission: policy.py:5875-5876 returns the producer immediately when
S3.3 is OFF; _defer_town_errand:5800-5811 likewise only enforces when ON.
The debt check at 5778 is conditional on that switch. After the calibration-owned
restore-equip session completes (policy_calibration.py:924-940), the next
_equipment_transaction_town_key calls _prepare_equipment_optimization
(policy_equipment.py:2150). That method admits a calibrated character at 660
without checking that deposited supplies are still owed. Thus 3027 opens a new
foreign session while phase is restore-supplies, and 3028 withdraws pC.
3021-3026 are calibration's own equipment executor, not this foreign session.

(b) The remaining target at 3038 is ('????? [1,+0]',31,1).
The original inventory contains it (turn 549266); 3011 deposits it in dhdg...
It is withdrawn by 3028 pC and equipped by 3031 wa: at turn 549401 and 549419
it is in equipment slot arms. The 38-item Home scan before 3034 contains no
matching gloves. The restore batch selects 17 other signatures; its observer
only clears signatures with inventory increases (policy_home.py:2040-2044,
2067-2080). It never reconciles the glove already worn. It was neither consumed
nor renamed nor deposited by 3036. 3036 dm52 deposits 52 torches from a 57-stack,
leaving five. Unknown/average gloves in Home are distinct from these known +0 gloves.

(c) Batch planning limits pack slots but ignores weight and original deposit
quantities (policy_home.py:1846-1890). It uses owner_item.count for both the
macro and confirmation, withdrawing 57 torches instead of the original five,
16 cure-critical potions instead of ten, and two unknown scrolls instead of one.
The overweight branch explicitly yields to ordinary Home deposit processing
(policy_calibration.py:1242-1253); _atomic_home_deposit_key stages the home-visit
weight-overload operation (policy_home.py:2587-2597). That is 3035-3036.

(d) _defer_unobserved_home_withdrawal retains calibration debt when cross-area
is ON and sets town:blocked:calibration-restore-target-absent
(policy_home.py:2329-2340). Its caller immediately invokes _town_entrance_step_off_key
with the generic home:atomic-withdraw-target-unobserved literal (1674-1690),
overwriting the terminal at policy_town.py:1522-1526. The stale block is also
snapshot-local (1543-1555). The retained debt keeps requesting Home and
the successful movement continually supplies a new one-step Reach; the cycle
never spends a restore-operation bound. Only the driver's 1500-decision floor
loop bound stops it at 03:16:47.

The specified shadow-report command against gzip returns zero rows because
s3_live_report.rows_in_window uses Path.open, not gzip.open. The same report
will be run against a local decompressed copy, preserving the source read-only.

## Step 2: owned restoration and bounded composition

Commit `3d749f86` implements the correction:

- `policy_calibration.py:89` derives physical ownership from the existing phase,
  suspended phase, redress obligation and deposited-supply debt. No new persistent
  attribute or threshold was added. `policy.py:5796` and `5877` ask that owner
  before executing a town producer even with S3.3 OFF. Survival/protocol work
  retains its existing precedence; calibration's own equipment session is allowed.
  Generic Home disposal and town routing wait during restoration; calibration
  calls its Home route/composer directly. `policy_equipment.py:656` also prevents
  a departure evaluator or other direct optimizer caller from opening a foreign
  session. The early admitted-session branch at `policy.py:9689` obeys the same owner.
- `policy_home.py:1399` binds restoration to calibration's debt rather than a
  different queued Home item/errand or foreign session. `policy_home.py:1828`
  checks the selected original quantity against observed stock and the existing
  strength-derived weight limit. `1885` reserves that same weight cumulatively
  across the macro, retaining descending shelf order. The recorded 57-torch
  stack contributes only the five originally deposited torches (`py5\r`), not
  all 57. A batch that cannot include its selected take sends that take alone;
  observed completion invalidates addresses before the next batch.
- `policy_home.py:2037` keeps a single take's debt until its effect is observed.
  Original quantities remain available while the take is pending. Supply debt
  remains physical with both switches OFF, including floor interruption and
  exhausted Home visits (`policy_calibration.py:879`, `897`, `1023`).
- `policy_home.py:1691` preserves an absent calibration target as a typed terminal
  instead of overwriting it with step-off movement. The producer declares no-step
  with a named cause (`policy_calibration.py:118`); the OFF exit returns no key
  (`policy.py:6832`). Existing S3.3 ON declaration enforcement remains active.
  Unknown addresses earn a fresh scan only when the full catalogue actually
  contains the owned item. Insufficient weight/stock or an imported foreign
  session also ends visibly with debt intact. `policy_home.py:2397` disallows
  unrelated deposits mid-restore, and `policy_calibration.py:1283` no longer
  hands an overweight restore to the ordinary deposit family.

## Recorded pins and the single revert check

`tests/test_calibration_live19.py` uses 84 byte-faithful state/knowledge rows:
83 rows at turns 549266-549431 plus the preceding recorded skill-exp response.
The separate decision fixture contains original decisions 3008-3040 (33 rows).
Both have source provenance and decompressed SHA-256. The state hash is
`f2b061635c3c867f73b972d06a04a6d2c2e2ac78b4216610a98b8e1b7431131d`.

The deposit producer registers the original carried-item debt. The recorded
3034 macro's letters/counts reconstruct its actual pending observation, which
is reconciled by `_observe_calibration_restore_batch` against the recorded
response. The subsequent 3037 Home knowledge is then fed to the production
withdraw composer and final exit. Before: a movement key `9` and
`town:entrance-step-off:home:atomic-withdraw-target-unobserved`. After: no key,
`town:blocked:calibration-restore-target-absent`, with the glove debt retained.
The direction differs from live `6` because the isolated replay does not import
the whole visit-count history; it reaches the same unbounded step-off branch.
This recovery proof is repeated after pickle checkpoint restoration.

Separate pins exercise the newly planned macro's quantities and cumulative
weight, including constrained capacity, OFF/ON producer admission after a
checkpoint, and a completely OFF missing-target/overweight terminal. The public
`choose_key` capture continuation produces `wf, wb, wb, wb, wa(, wa, ~9+Escape`;
all seven claim owners are calibration, with no foreign equipment-txn owner.
The equipment-transaction reason strings during rewearing are retained because
that executor is calibration's own session. Direct optimizer and all competing
town producer entry pins prove that no foreign session can be opened while debt
remains. The unchanged recorded post-macro boards are used only for recovery;
we do not claim they are responses to a changed macro or that a counterfactual
full restoration was observed live. The demonstrated outcome is the allowed
typed stop, not a fabricated restoration success.

Exactly one revert check restored all four changed production files from
`eacb335d`, ran only the six new pins, then restored every fixed byte in `finally`.
It failed behaviorally with eight assertion failures and no import/errors:
legacy movement, incorrect stack quantities, and foreign entry/optimizer
admission. The fixed code passes. Log: `reports/live19-revert-before.log`;
procedure: `reports/live19-revert.py`.

The existing overweight calibration pin was strengthened and renamed
`test_overweight_restore_stops_without_foreign_deposit_or_erasing_debt`.
Its old default class -1 never reached the warrior restoration branch; it now
constructs a warrior and asserts the exact typed stop, no emitted key, no deposit,
and retained debt. No existing pin or assertion was deleted or loosened.

## Authorized verification

Python 3.13: `C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe`,
`PYTHONPATH=src;tests;scripts`, one test module per process.

| Module | Passed |
| --- | ---: |
| tests.test_calibration_live19 | 6 |
| tests.test_calibration_crossarea_debt | 5 |
| tests.test_live8 | 11 |
| tests.test_declarations_r11 | 10 |
| tests.test_test_fakery_lint | 13 |
| tests.test_town_producer_purity_part1 | 1 |
| Total | 46 |

Only the two listed calibration modules were touched/run. Exactly one purity
part was run (285.759 seconds). No full suite, prohibited runner/gate, long
recorded replay, or other purity part was run.

| Fixture | OFF identity | S3.3 first difference | trajectory_defect |
| --- | --- | --- | --- |
| stuck | 4 rows; c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | None | null |
| withdraw | 34 rows; a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | index 20: rkc / town:enchant-launcher-todam ? Escape + `n%. / shop:travel | null |

Both fixtures were run in separate OFF and S3.3 processes. EXPECTED_FIRST was
untouched. Detailed outputs and counts are in `reports/live19-verification.json`
and the four `reports/live19-{stuck,withdraw}-{off,s33}.json` files.

The decompressed-copy shadow report measures 4,425 decision rows and 1,716
shadow rows, including six equipment-txn unrestored stops first seen at 3027
and 1,353 home-visit unrestored stops. Source JSONL gzip files were never modified.
The copy used for the report was removed afterwards; the report is preserved at
`reports/live19-shadow.json`.

Commits: `eacb335d` (recorded cause / step 1), `3d749f86` (production fix, pins,
fixtures and bounded verification / step 2). This report is committed separately.
No game, executable, live bot, other worktree or jsonlog write. The existing
untracked `.live8b-revert.py` is untouched.


{"topic":"live19","implementer":"gpt-6.1-sol","base":"adf8f3e1","commits":["eacb335d","3d749f86"],"cause":"foreign-equipment-plan-and-whole-Home-stack-restore-with-lost-terminal","remaining_target":"????? [1,+0]","target_location":"equipment:arms","result":"owned-restore-or-typed-stop-even-off","single_revert_failures":8,"tests_passed":46,"tests_failed":0,"stuck_off_identity":true,"withdraw_off_identity":true,"s33_stuck":"expected-no-difference","s33_withdraw":"expected-index-20","expected_first_changed":false,"new_thresholds":0,"new_persistent_attributes":0}
