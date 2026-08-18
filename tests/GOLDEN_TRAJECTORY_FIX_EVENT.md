# Golden trajectory fix event

## 2026-08-18 `golden-trajectory`

Measured:

- The fresh Q34 quick-start model issues and consumes exactly one empty-Home
  knowledge scan, composes the initial torch purchase, approaches and posts
  quest acceptance, and engages the quest-floor navigator in that order.
- At HEAD (`a6ae647`) the five-test module completes in 5.47 seconds: three
  pass and the two unavailable incident artifacts skip with their paths.
- With `src/` exported to throwaway directories, the golden test fails at
  both `ce62506^` and `54a7c6f^`: each repeats
  `('opening-q34:wait', '5')` seven times and trips the pair bound.
- `incident-captures/20260818-1814-opening-stall/` and
  `incident-captures/20260818-decision-110/` are absent in this checkout.
  Their regressions therefore skip explicitly; no pass is claimed for either
  missing real artifact. The converter's malformed-window and missing-capture
  behavior is covered independently.

Inferred:

- Single-decision pins could not establish that Home absence releases the
  purchase owner or that acceptance hands off to execution. The ordered
  milestone drive covers both transitions while avoiding an exact-key golden
  transcript.
- Gold, position, floor, and pack signature form the trajectory progress
  projection. Owner and identical `(reason, key)` bounds make an absorbing
  opening failure visible even when emitted turns continue changing.

Scope: tests only; no product or script changes, no live game, no bot start,
and no push.

Verification:

- `tests.test_policy`: 2077 tests in 426.055s, OK (13 skipped).
- `tests.test_cli` excluding `DecisionTimingTest`: 176 tests in 3.477s, OK.
- `tests.test_absorbing_states`: 17 tests in 18.384s, OK.
- `tests.test_home_visit`: 16 run with four known missing-artifact errors.
- `tests.test_shop_one_shot`: 36 run with the known missing
  `evidence-sale-inflight-lines.jsonl` error.
- `tests.test_home_knowledge_scan`: 21 run with the known absent stalled
  capture failure.
- `tests.test_test_fakery_lint`: its matrix passed, but the tree census retains
  two pre-existing undeclared collaborator-wall findings in
  `test_once_records_tcp_shadow_after_successful_send` and
  `test_q34_restock_wait_publishes_supplier_reason`; the new module added none.
- `py_compile` and `git diff --check -- tests` succeeded.
