# live19b

Calibration now deposits unrelated retention surplus before continuing an overweight
restore. It calls the ordinary Home deposit composers directly, keeps the phase
and outstanding signatures, and identifies entry/tail operations as calibration.
It retains the original restore signatures, including successful withdrawal
batches, to prevent a restore/deposit loop. The existing Home retry budget and
rejection handling remain in use; no threshold was added.

Changes:
- `src/hengbot/policy_calibration.py:1284`: await an outstanding deposit, select
  excess, re-file an absent Home route, compose the deposit, and continue restore.
  No depositable excess remains a typed `calibration-restore-weight-limit` stop;
  unavailable/failed Home composition has its own typed cause.
- `src/hengbot/policy_home.py:19`: checkpoint-compatible restore protection;
  original deposits and withdrawal batches populate it, and a new calibration
  clears it. Selection at line 1073 protects pending and already-restored stacks,
  including the existing crossarea type/sval alias matching.
- `src/hengbot/policy_home.py:2415`: explicit calibration-only restore-excess
  entry to the ordinary atomic composer. Open-page and staged operations retain
  calibration ownership. `:2926` uses the existing overweight/retention selector.

Pins in `tests/test_calibration_live19.py`:
- `:65`: unrelated cursed loot is deposited by calibration, its staged tail is
  calibration-owned, all restore debt/quantities survive, and supplies restore
  completes. OFF/ON ownership enforcement and checkpoint restore all pass.
  Route state is initially absent. Responses after the changed command are
  explicitly synthetic; recorded boards supply the input facts.
- `:128`: a successfully restored overweight torch stack cannot be re-deposited;
  remaining debt stays owed and produces a typed terminal. Refused unrelated
  excess also produces the terminal.
- `:161`: an older checkpoint without the new protection field acquires it from
  the outstanding debt without depositing that debt.
- Existing byte-faithful live19 replay, bounded quantity/weight, missing-target
  terminal, and foreign-producer exclusion pins still pass without modification.

Verification (one module per Python process, `PYTHONPATH=src;tests;scripts`):

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_calibration_live19 | 9 | PASS |
| tests.test_calibration_crossarea_debt | 5 | PASS |
| tests.test_live8 | 11 | PASS |
| tests.test_test_fakery_lint | 13 | PASS |
| tests.test_town_producer_purity_part1 | 1 (186 cells) | PASS |

One revert check replaced only the overweight recovery branch with the old
weight-limit terminal. The unrelated-excess pin failed in all four combinations.
The original source bytes were restored, the temporary runner removed, and the
calibration modules were rerun successfully. `git diff --check` passed.

Authorized `first_divergence_s3_3.py` fixtures only:

| Fixture/mode | OFF rows | OFF SHA256 | First divergence / trajectory defect |
| --- | ---: | --- | --- |
| stuck off | 4 | c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none |
| stuck s33 | 4 | same | none / none |
| withdraw off | 34 | a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | none |
| withdraw s33 | 34 | same | index/sequence 20, `ESC` + `` `n%. `` (`shop:travel`) / none |

The withdraw S3.3 difference matches the existing EXPECTED_FIRST. Declaration
mismatch counts and gap rows are empty in all four runs. Existing detector
declaration omissions remain: stuck 1; withdraw OFF 2, S3.3 prefix 1. Withdraw
OFF has 20 gate-final rows, matching the existing fixture result. No
EXPECTED_FIRST entry was edited.

Commits:
- `946bbf8e`: merge main (live20), no conflicts.
- `700e9254`: excess deposit implementation and pins.
- `8aada832`: alias protection and older checkpoint coverage.
- `ab2b83cd`: re-file Home approach before composing excess deposits.

Work stayed in this worktree. No game, bot process, other worktree, prohibited
suite/gate, or long replay was operated. The pre-existing untracked
`.live8b-revert.py` was left intact. This report is stored outside read-only
jsonlog; main's tracked event file was brought in only by the requested merge.

{"topic":"live19b","implementer":"gpt-6.1-sol","status":"complete","pins":["calibration-owned-excess-deposit-and-restore-completion","no-depositable-excess-typed-terminal","recorded-live19-replay","restored-stack-protection","older-checkpoint"],"tests":39,"single_revert":"caught-four-combinations","fixtures":{"stuck_off":"identity","stuck_s33":"no-divergence","withdraw_off":"identity","withdraw_s33":"expected-first-20"},"commits":["946bbf8e","700e9254","8aada832","ab2b83cd"]}
