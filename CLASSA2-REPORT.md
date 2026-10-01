# Class A2 correction

Worktree: `C:\hengband\bot-client-decl-r3b`, branch `decl-r3b`.
The directory initially had `live37` checked out; switched to the requested
`decl-r3b` without changing its existing untracked files. Merged main b24fd077
as fbbff994; no conflicts.

## Cause and fix

`src/hengbot/cli.py:2241` constructs the established one-shot purchase plan:
the purchase prefix (e.g. `pa`) is posted from the observed store boundary,
followed by quantity/confirmation and store exit waits. The common compiler
at `src/hengbot/observed_input.py:76` and `:160` instead rebound those waits
to Japanese recorded features and split the prefix into `p` plus an item-source
wait. The existing English production-executor pin advances directly from
`pa` to confirmation, so the inserted Japanese chooser wait terminated it.

`src/hengbot/observed_input.py:67` now retains the established one-shot plan
on an observed English purchase-menu screen. `src/hengbot/cli.py:2158` supplies
the executor's existing bound screen value for that decision. The operation
still enters the store first, posts its purchase prefix once at the store
boundary, and observes confirmation and exit separately. Recorded Japanese
Class A chooser and price gates remain strict. English chooser splitting is
still an unrecorded form and retains the baseline; this is not a claim of a
new recorded English chooser implementation.

Added only `active = None` to the four CapturingExecutor fakes and the
DeathExecutor fake in `tests/test_cli.py` (lines 222, 240, 260, 280, 303).
No new executor/checkpoint attributes. No pin or EXPECTED_FIRST changes.

## Commits

- fbbff994: merge main b24fd077 into decl-r3b.
- ae3585b1: preserve observed English store one-shot purchase staging.
- 84780362: expose inactive operation state in CLI executor fakes.

## Verification

Each requested module ran in its own process with `PYTHONPATH=src;tests;scripts`
and Python 3.13 at `C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe`.

| Module | Tests | Result | Seconds |
| --- | ---: | --- | ---: |
| tests.test_shop_one_shot | 53 | OK, 1 skipped | 2.007 |
| tests.test_cli | 234 | OK | 18.846 |
| tests.test_classA_observed_input | 29 | OK | 10.881 |
| tests.test_input_executor | 73 | OK | 2.118 |
| tests.test_live11 | 2 | OK | 2.604 |
| tests.test_execution_declaration | 29 | OK | 14.188 |
| tests.test_live30_identify_normal | 9 | OK | 26.885 |
| tests.test_live35_store_page | 3 | OK | 0.340 |
| tests.test_test_fakery_lint | 13 | OK | 76.326 |

Total: 445 tests, 444 passed, 1 skipped. The CLI and shop modules each used
one process and finished under one minute. The unchanged production purchase
pin verifies accepted segments `5`, `pa`, Enter, ESC. No additional test-module
or revert execution was performed under the exact-module/one-process limit.

Ran only the short stuck and withdraw cases of first_divergence_s3_3.py,
each in OFF and S3.3 modes:

| Case | OFF rows | OFF SHA256 | S3.3 first divergence | Defect |
| --- | ---: | --- | --- | --- |
| stuck | 4 | c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none | none |
| withdraw | 34 | a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | (3, 3, ESC, equipment-transaction:catalogue-leave-for-scan) | none |

All measured declaration gaps and mismatch counts were empty. Existing OFF
detector declarations remain absent in one stuck decision and two withdraw
decisions, as in the baseline. No game or bot was launched. Existing untracked
files were preserved.
