# Class C3 verification

All requested modules ran individually with the Codex runtime Python 3.12 and
`PYTHONPATH=src;tests;scripts`. The shop module was bounded to 60 seconds and
completed in 27.95 seconds. No full-suite runner or prohibited gate was run.

| Module | Tests | Result |
| --- | ---: | --- |
| `tests.test_policy_shop` | 279 | PASS, 1 existing skip |
| `tests.test_classC_departure_remedies` | 5 | PASS |
| `tests.test_classC2_departure_recorded` | 9 | PASS |
| `tests.test_live36_weight` | 7 | PASS |
| `tests.test_identify_staff_live27_recorded` | 1 | PASS |
| `tests.test_departure_unsatisfiable_weight_recorded` | 7 | PASS |
| `tests.test_ammo_surplus` | 4 | PASS |
| `tests.test_quest_ammo_not_bought` | 8 | PASS |
| `tests.test_town_progress_invariant` | 22 | PASS |
| `tests.test_ownership_s2a_classification` | 16 | PASS |
| `tests.test_test_fakery_lint` | 13 | PASS |

Total: 371 tests, one existing skip. The two explicitly listed ammunition
modules above are the repository's modules with `ammo`/`quest_ammo` in their
names; no all-matching execution sweep was used. Each full module has its
own `.txt` output and `.json` count/exit/time artifact.

## Requested replay comparisons

| Case | Mode | OFF rows | First S3.3 difference | Trajectory defect |
| --- | --- | ---: | --- | --- |
| stuck | OFF | 4 | none | n/a |
| stuck | S3.3 | 4 | none | none |
| withdraw | OFF | 34 | none | n/a |
| withdraw | S3.3 | 34 | sequence 3, ESC / `equipment-transaction:catalogue-leave-for-scan` | none |

Both OFF stream hashes remain the pinned values:

- stuck: `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`
- withdraw: `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`

The withdrawal S3.3 difference remains the existing `EXPECTED_FIRST`, which
was not edited. Declaration gap rows and mismatch counts are empty in all
four reports. The existing detector declaration omissions remain: one in
stuck OFF/S3.3, two in withdraw OFF, zero before withdraw's S3.3 divergence.
All four structured reports are unchanged from the Class C2 measurements.

## Single-revert proof and final pin checks

`classC3-single-revert.py` disables only one production hunk at a time. It
runs explicitly named pins as one module per process, uses a separate empty
bytecode-cache prefix, and restores both source files byte-for-byte in
`finally`. It never edits tests, fixtures, assertions or `EXPECTED_FIRST`.

- Reverting the refreshed-plan shop guard makes the unchanged regression pin
  fail with `4 is not None`.
- Restoring the old constant-99 ammunition target makes the four-shot deposit
  and fitting-procurement pins fail. Restoring the production target makes
  both pass.
- The final restored Class C2 pin invocation also checks the new phase-scroll
  then four-shot batch assertion and the post-deposit safe-recall assertion.
  These assertions were added after the nine-test module run; their final
  check is recorded separately rather than repeating the entire module.

Exact exit codes, source hashes and the byte-exact restoration result are
in `classC3-single-revert.json`. The corresponding text artifacts retain
the expected failures and final restored results.

No pre-existing `tests.test_policy_shop` pin or `EXPECTED_FIRST` changed.
The updated Class C2/live36 expectations express the new explicit ammunition
decision with exact quantities; all other required supplies remain protected.

The DO-NOT-RUN module/script list pending for Claude is in
`classC3-implementation.md`.
