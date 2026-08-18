# Verification gates rounds 4/5 acceptance record

Date: 2026-08-18. Topic: `verification-gates-r5`. Base: `0125b81`.

## Outcome

Failures are classified per failing test. Loader/collection `_FailedTest`
records never protect a hunk, while an ordinary test remains eligible even if
any of the eight exception names appears elsewhere in its module stderr. The
temporary `GATE STATUS` reviewer-override paragraph was removed from
`SOL-OPERATOR-BRIEF.md`; UNPROTECTED is again the mandatory gate signal.

The approved artifact-loss disposition is count-exact. On `ce62506`, all five
test allowances (1, 1, 4, 1, 1 failures) and the nine-finding lint allowance
appear as `matched: true` in `jsonlog/verify-scope-r5-ce62506.json`; any extra
failure or finding remains red.

## Semantic sabotage and injection tables

The fixed behavioral suite ran 25 tests with zero skips in 26.695 s. These
checks execute gate behavior on synthetic repositories or real subprocesses;
they do not merely search source text.

| Sabotage | Behavioral observation | RED count |
| --- | --- | --- |
| S1 exception filter disabled/string preserved | each named exception beside a real failure must retain that test id | 8/8 |
| S2 `new_file` forced false/string preserved | `main()` must emit NEW-FILE-UNVERIFIED and rc=1 | 1/1 |
| S3 docstring fallback disabled | indented docstring-only edit must remain nonbehavioral | 1/1 |
| S4 warning condition unreachable/string preserved | comment-only repository edit must emit NO-BEHAVIORAL-HUNKS | 1/1 |
| S5 matcher returns empty/string preserved | `main()` must reject the now-unmatched failing module | 1/1 |
| S6 structural-loader eligibility weakened | `_FailedTest` without exception-name assistance must remain ineligible | 1/1 |
| S7 historical answer key restored | module must expose no `INELIGIBLE_PROTECTORS` answer key | 1/1 |

| Injection miss | Behavioral observation | RED count |
| --- | --- | --- |
| M2 hardcoded failed/skipped | emitted FAIL and skipped records are counted 1/1 | 1/1 |
| M2b lint count accounting | two findings cannot consume a one-finding allowance | 1/1 |
| M8b atexit unregistered | subprocess exit removes an active unregistered temp tree | 1/1 |
| R4 live-tests glob | historical target returns a test absent from the live tree | 1/1 |

The startup sweep's synthetic check removed an old unregistered directory with
a dead PID sidecar while preserving an equally old directory owned by a live
PID. That did not prove Windows hard-kill recovery: round 6 found that the
Windows PID probe treated dead owners as live, so neither registered nor
unregistered killed-run directories could be reclaimed until that probe was
fixed.

## Historical hunk verdicts

The table below records `--wide --timeout 120` runs, one gate process at a
time. These must not be compared with default-mode timings.

| Target | Round 5 verdict | Delta from superseded record | Runtime |
| --- | --- | --- | --- |
| `32a81a3` | 4 protected, 3 unprotected, 1 new-file-unverified | r4: 0/7 plus new file; four true CLI pins restored; **wide only** | 629.165 s |
| `a961376` | 1 protected, 0 unprotected | unchanged | 25.154 s |
| `dbce3b4` | 3 protected, 0 unprotected | r3 recorded 1/1; two additional true grouped verdicts visible | 121.599 s |
| `00c57c2` | 2 protected, 0 unprotected, 1 skipped | r3 final had 1 protected/1 unprotected/1 skipped | 42.214 s |
| `fb22255` | 8 protected, 5 unprotected | r3 had 6 protected/7 unprotected | 763.742 s |

Like-for-like default-mode reviewer measurements were approximately 64 s for
`32a81a3` and 164 s for `fb22255`, so the default path got faster. The default
`32a81a3` verdict was 2 protected, 5 unprotected, and 1 new-file-unverified,
not the wide-only 4/3/1 verdict.

The required `32a81a3` hunk at lines 1935-1948 is protected by
`test_control_client.DisabledCliPinTest.test_disabled_parser_does_not_import_or_connect_or_write`.
JSON evidence is `jsonlog/hunk-guard-r5-<target>.json`.

## Scope gates and final checks

- `verify_scope.py --target ce62506 --timeout 120`: rc=0, 77.922 s.
- `verify_scope.py --target b199125 --timeout 120`: rc=0, 24.669 s.
- `hunk_guard` stderr now includes the `new_file_unverified` count.
- The live game and bot remained frozen/stopped; no `src/` or `tests/` file was
  touched by this round and no push was performed.
