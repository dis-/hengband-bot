# live16

Worktree: `C:\hengband\bot-client-decl-r3b`, branch `decl-r3b`, starting
HEAD `d4a126d7`. Fix commit: `33b34a17`.

## Four failures

All four originate in `4f85e04f`, whose `policy_equipment.py:2516-2518`
removed the full-equipped macro's slash and result-dismissal suffix.

| Failure | Cause | Fix |
| --- | --- | --- |
| Town dragon helm | Public decision changed from `rs/j` + ESC x8 to `rsj`. | Public town producer requests macro notation at `policy.py:10798`; `policy_equipment.py:2522-2524` retains its route and dismissal suffix. |
| Town 56-item heavy-curse catalog | Public decision changed from `rs/b` + ESC x8 to `rsb`. | Same macro composition fix. Required identification remains in place. |
| Home D3.2 full identification | Public decision changed from `ri/a` + ESC x8 to `ria`. | Same macro composition fix; no weapon takeoff or alternation added. |
| Departure recorded row 86 | Historical `ri/e` + ESC x8, reason `identify:full-equipped`, became `rie` with the same reason. | Same fix restores the recorded key. All 117 boards replay with only the existing declared differences at 110, 112, 115, 116. |

The compact internal prompt-step form remains available to direct callers,
preserving the existing live13/live15 pins. Both forms install the staged source
and target gates. At `cli.py:2550-2555`, the equipped target continuation removes
the macro's slash before the existing full-identify logic removes the blind
dismissal tail. The input executor then sends `/` only on an observed inventory
chooser and selects the bound equipment letter on an equipment chooser. Its
existing observed viewer-page/final handling owns result dismissal.

This separates the public decision notation from the bytes actually posted.
The recorded live13 equipment page receives `a`, and the live15 source page
receives `f`. No new post-target result is fabricated: those pins stop when the
next screen is unavailable. The new macro pin also tests an explicitly declared
counterfactual inventory chooser followed by the recorded equipment chooser;
that route receives `/`, then `a`.

## Bounded bisect

Binary search of the eight supplied live13/live14/live15 commits, using the
single departure replay test in a separate process for each revision:

| Revision | Result |
| --- | --- |
| Current pre-fix `d4a126d7` | FAIL: extra divergence 86 |
| Midpoint `1175b841` | FAIL: extra divergence 86 |
| `4f85e04f` | FAIL: extra divergence 86 |
| Adjacent predecessor `85c8ba20` | PASS |
| Fixed `33b34a17` | PASS |

Historical production files were read with `git show` into a temporary package
inside this worktree. The five production files changed in the supplied range
were replaced there; each historical replay ran against that package, with
unchanged fixtures and assertions. No other worktree was changed.

## Verification

Normal Python 3.13, `PYTHONPATH=src;tests;scripts`, one test module per process.

| Allowed verification | Tests / result |
| --- | --- |
| `tests.test_policy_town` (only the two named tests) | 2 PASS |
| `tests.test_home_light_alternation` | 37 PASS |
| `tests.test_departure_unsatisfiable_weight_recorded` | 7 PASS |
| `tests.test_live13_full_equipped_identify` | 1 PASS |
| `tests.test_live15_identify_source` (existing and new pin, separate invocations) | 2 PASS |
| `tests.test_test_fakery_lint` | 13 PASS |
| S3.3 `stuck` first-divergence fixture | OFF hash unchanged; 4 rows; no divergence; no trajectory defect |
| S3.3 `withdraw` first-divergence fixture | OFF hash unchanged; 34 rows; designed first divergence at row 20; no trajectory defect |

62 tests passed. The single revert check removing the CLI slash normalization
killed the new macro pin in both chooser cases; the production file was restored.
`git diff --check` passed. No pre-existing expectation, `EXPECTED_FIRST`, fixture,
runtime JSON log, or other worktree was edited. No new persistent attributes or
tunable thresholds were introduced. The pre-existing untracked
`.live8b-revert.py` was left alone.

{"topic":"live16","implementer":"gpt-6.1-sol","status":"fixed","origin_commit":"4f85e04f","fix_commit":"33b34a17","failures_fixed":4,"tests_passed":62,"single_revert":"killed","stuck_s33":"pass","withdraw_s33":"pass","expected_first_changed":false,"preexisting_expectations_changed":false}
