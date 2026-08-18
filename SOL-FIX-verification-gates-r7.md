# Verification gates round 7 acceptance record

Date: 2026-08-19. Topic: `verification-gates-r7`. Script base: `9b1380d`.
Live HEAD advanced concurrently to `bae256a`; no `src/` or `tests/` file was
touched by this round, the bot was not started, and the frozen game was left
alone.

## Repairs

The home-knowledge allowance again matches the real unittest token
`stalled_capture`. The manufactured `missing evidence/stalled-capture.jsonl`
fixture is gone, and its mutation now changes the live underscore spelling to
the dead hyphen spelling. This is an unsigned `KNOWN_FAILURES` correction
pending the reviewer sign-off required by `SOL-OPERATOR-BRIEF.md`.

Worktree cleanup now performs the inspected `shutil.rmtree` before asking git
to unregister the worktree, so git never recursively traverses copied runtime
evidence. The ordering pin and mutation agree with that direction. The
live-artifact self-test supplies its synthetic repository as the cleanup root,
preventing leaked registrations. Seven old `vgate-copy-*` directories were
removed; the final gate-fixture inventory in `%TEMP%` was empty.

An AST pin now rejects an inline set/list/tuple/dict literal subtracted from
`failures` or `new_failures`. Its mutation replaces
`failures - baseline[module]` with an inline literal answer key and is RED.

## Acceptance outputs and runtimes

- Final self-tests: rc=0, 35/35 green, zero skips, 21.814 s unittest runtime,
  22.119 s wall; zero newly created `%TEMP%` residue.
- Final mutation battery: rc=0, 9/9 RED, 3.008 s wall. RED entries were
  `failed-test-filter-deleted`, `inline-answer-key-denylist`,
  `inline-literal-answer-key`, `docstring-prose-fallback-removed`,
  `dead-stalled-capture-pattern`, `git-remover-before-inspected-removal`,
  `lint-allowance-count-disabled`, `excluded-test-prefix-wrong`, and
  `known-failure-matcher-disabled`.
- `verify_scope.py --target ce62506 --timeout 120`: rc=0, 69.572 s wall;
  21 `ran`, 6 `failed_known`; home knowledge reported `matched=True` on
  `stalled_capture`. Fingerprint:
  `b2221d4e49d56eda50f633827beb40099c65242fc73d01d351ed482fafa81c07`.
- `verify_scope.py --target HEAD --timeout 120`: resolved to `bae256a`, rc=1,
  70.667 s wall; 22 `ran`, 5 `failed_known`, 3 `failed`. This is a recorded
  baseline disposition, not a green claim. Exact failures were three Q2
  recovery tests in `tests.test_policy`, both
  `TestTreeFakeryLint.test_inline_exception_count_is_ratcheted` and
  `TestTreeFakeryLint.test_tree_has_only_catalogued_undeclared_shapes`, and
  `TownRestockStallTrajectoryTest.test_hungry_character_escapes_recall_restock_owner_alternation`.
  The test-fakery allowance was unmatched because that module had two
  failures. Fingerprint:
  `d4c3e07f64df9f3157dd658c0791ec20891d63f2583cd25c16e15b3ca2ca581b`.

Both generated runs recorded 65 skipped tests and the same copied runtime
inventory: empty `evidence/` and the complete live `incident-captures/`
inventory. Their JSON outputs remain outside the repository at
`%TEMP%/verify-scope-r7-ce62506.json` and
`%TEMP%/verify-scope-r7-head.json`. No push was performed.
