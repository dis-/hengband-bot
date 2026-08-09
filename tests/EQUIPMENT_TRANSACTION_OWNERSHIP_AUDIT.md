# Equipment transaction ownership fix event

## 2026-08-09 interrupted optimization fix event

Ownership rule: after a live optimizer transaction has observed any take-off,
the transaction owns every town decision until completion or restoration.  The
rule is enforced at the top of `HengbotPolicy._decide`, before store dispatch,
shopping, selling, disposal, fundraising, or errands can select an action.

Restore guarantee: every confirmed take-off records the physical item identity
and its former slot.  Abandonment replaces the failed plan with equip actions
for the entire owned set; ownership is released item-by-item only after an
equip/reposition or successful final deposit is observed.  A failure in that
restore retains the session and ownership at the visible absorbing terminal
`equipment-transaction:restore-blocked-terminal`.

Classifier guard: `_retention_surplus` returns zero and
`_equipment_disposal_reserved` returns true for transaction-owned items.  The
independent `_current_store_sale_candidates` aggregator also filters them, so a
town-owner routing regression cannot recreate the permanent sale.

The plan already composes Home withdrawals before `PHASE_EQUIP` take-offs, so
replacement gear from Home is in the pack before stripping begins.  Deliberate
empty target slots and failures after stripping still require the restore path.

Pins:

- `test_public_blocked_mid_strip_owns_town_and_installs_full_restore`
- `test_transaction_owned_item_refused_by_classifier_guards`
- `test_blocked_restore_reaches_visible_named_terminal`
- absorbing seed `transaction-abandoned-mid-strip`

Historical `cc142ed` result for the three public pins was quoted directly from
an isolated detached worktree: `EEF`; the ownership pin raised missing
`_equipment_transaction_restoring`, the terminal pin found the abandoned
session was `None`, and the classifier pin failed with
`AssertionError: 30 != 0`.

## 2026-08-09 completing optimization fix event

Measured answers:

- `HengbotPolicy._choose_key` treated every independently observed Home page
  with an active transaction and no posted atomic operation as
  `uncomposed-home-entry`.  That self-created block made
  `_equipment_transaction_home_key` see `session.executable == false` and call
  abandonment.  In the retained shape the required context was `home`, the
  entry blocker was `inside-store`, and ten confirmed take-offs were owned.
- Every Home `Escape` flowed through `_report_town_stop_pass`.  An unsatisfied
  pass increments both `current_stop_passes` and
  `unsatisfied_passes[STORE_HOME]`; therefore each abandon/leave/retry charged
  the completion allowance.  The decision log measured `3 -> 18`, fifteen
  failed passes in 69 seconds, after which Home was blocked.
- `equipment_work_need_present` inspected only the synthetic
  `equipment-work` category.  It omitted the registry's equally authoritative
  executable `equipment-transaction` claim, allowing telemetry to report
  `outstanding_equipment_work=true` and projected need `false`; the projection
  side was wrong.

Progress rule: an active executable transaction advances in its required
context.  Observing Home is a handoff to the entrance-bound atomic withdrawal,
not failure evidence.  Abandonment now requires independent evidence such as a
planner blocker, missing bound identity, rejected dispatch, unavailable route,
or exhausted confirmation observation bound.  A self-created context state is
not evidence.

Pins:

- `test_live_inside_home_with_ten_removed_items_preserves_transaction_progress`
- `test_abandonment_does_not_consume_home_completion_pass`
- `test_outstanding_equipment_work_always_projects_a_home_need`
- `test_completing_optimization_performs_zero_restores`
- absorbing seed `abandon-retry-home-pass-burn`

Historical `5dcd319` result for the first three pins was quoted directly before
the fix: `FFF`.  The observed values were reason
`equipment-transaction:abandon-blocked-home`, Home unsatisfied passes `0 -> 1`,
and projection `outstanding=true`, `need=false`.  At the fixed tip, successful
completion invokes abandonment/restoration zero times; restore remains only the
last-resort safety path.
