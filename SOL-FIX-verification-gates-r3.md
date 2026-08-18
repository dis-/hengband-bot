# Verification gates round 3 acceptance record

Date: 2026-08-18. Topic: `verification-gates-r3`.

## Fatal data-loss incident

The former `verify_scope.py` junctioned the live ignored `evidence/` and
`incident-captures/` directories into a detached worktree. Its subsequent
`git worktree remove --force` traversed those junctions and destroyed the live
contents of both directories. Both directories are now empty; the destroyed
artifacts are unavailable, so their exact byte count cannot be reconstructed.
This is the same failure class that destroyed 5.4 GB on 2026-08-17.

The replacement is copy-only. Cleanup refuses every symlink/junction/reparse
point, removes the inspected detached directory before unregistering it, and
prunes registrations at startup and shutdown. The synthetic full-cleanup and
simulated-kill test preserved `evidence/keep.bin` byte-for-byte and removed the
detached worktree. A second test changed the copied artifact and verified that
the source contents and mtime were unchanged.

## Historical hunk verdicts

No test-id eligibility/answer-key list exists. Timeouts and import/loader
failures are rejected as protection.

| Target | Result | Runtime / explanation |
| --- | --- | --- |
| `a961376` | PROTECTED (1/1) | 131.55 s wide run; the naturally derived CLI assertion protects the grouped change. |
| `dbce3b4` | PROTECTED (1/1) | 108.13 s wide run; naturally derived protection. |
| `fb22255` | 6 PROTECTED, 7 UNPROTECTED | 315.35 s; adjacent grouping applied. Seven isolated changes produced no new eligible failure and remain honestly red. |
| `00c57c2` | docstring SKIPPED, retry guard PROTECTED, backoff group UNPROTECTED in final run | 218.83 s; the producer/consumer hunks are grouped. The earlier 22.36 s grouped run found `test_absent_server_backoff_is_capped_by_request_budget`; the final environment timed out and, correctly, timeout did not count as protection. |
| `32a81a3` | PROTECTED (1/1 cross-file group) | 60.32 s; the new adapter and all CLI consumers were reverted together, and the 189-line new test module protected the unit. |

Generated JSON is in `jsonlog/hunk-guard-r3-<target>.json` (operator evidence,
not committed by this scripts/docs-only change).

## Ten regression probes

The synthetic-repository suite drives `main()` for both gates and completed in
66.2 s (`13 tests OK`; one privilege-dependent symlink creation probe skipped
on Windows, while reparse detection and full cleanup were exercised).

| Injected regression | Result |
| --- | --- |
| B1 baseline/source artifact mutation | RED |
| lint allowance count/failed accounting | RED |
| dead allowlist pattern | RED |
| timeout/import/failed-loader protection | RED |
| NEW-FILE automatic-unverified branch | RED |
| stale/wrong tree fingerprint | RED |
| failed/skipped count regression | RED |
| missing excluded-test/allowlist telemetry key | RED |
| missing no-behavioral-hunks warning/recognition | RED |
| remove-before-prune worktree cleanup regression | RED |

## `ce62506` baseline

`verify_scope.py --target ce62506 --timeout 120` ran in 220.79 s and returned
1. The generated JSON is `jsonlog/verify-scope-r3-ce62506.json`.

- The two declared missing-artifact failures and all nine declared lint shapes
  matched their allowlist entries; unmatched entries would have failed loudly.
- `test_home_visit` (four errors) and `test_worldmap_key_hygiene` (one error)
  are artifact-dependent. Their artifacts were destroyed by the B1 bug above.
- The lint command itself reported exactly the allowed nine findings, while
  `tests.test_test_fakery_lint` and `tests.test_policy` timed out. Timeouts are
  errors, never successes or protection.
- Historical `tests.test_golden_trajectory` also had a loader/import error.
- The live repaired gate scripts ran against the target product/tests. The
  emitted `errors`, `failed`, `skipped`, artifact inventory, tree fingerprint,
  and per-entry allowlist matched flags are measured rather than hardcoded.

`py_compile` passed, `git diff --check` passed, and the self-test runtime was
66.2 s. Claude Code read-only review was attempted through `claude.cmd` but
returned no result before the 180 s orchestration timeout.
