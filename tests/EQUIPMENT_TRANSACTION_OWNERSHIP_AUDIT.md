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

## 2026-08-09 terminal and restore-rebuild fix event

Terminal definition: a policy terminal ends the CLI drive after one logged,
final decision.  A reason label does not make a repeated key terminal.  The CLI
registers `equipment-transaction:restore-blocked-terminal` as a final stop and
does not post its key.  The absorbing harness separately asks whether the
modelled terminal ends the drive; a visible reason repeated more than three
times without that fact is a failure.

Terminal-site audit for every `self.last_reason = ...terminal...` assignment in
`policy.py`:

- `_equipment_transaction_town_owner_key`, pre-existing terminal branch: it is
  reached only after snapshot reconciliation finds no recoverable action and a
  genuinely missing owned remainder; the CLI logs that decision and stops
  before posting `WAIT_KEY` (or the store leave key).
- `_equipment_transaction_town_owner_key`, no-key sibling: it has the same
  disposition.  It cannot be the no-session/pack-gear path because that path
  now rebuilds the restore session before routing; if routing nevertheless has
  no key, the registered CLI final stop owns the decision.

Restore-rebuild rule: interruption and a no-session observation both discard
only the failed attempt.  The policy reconciles the owned set against currently
equipped slots, builds equip actions for pack identities, prepends Home
withdrawals for Home-known identities, and repeats this reconstruction after a
recoverable prefix completes.  Missing identities are reported in
`transaction_restore_remainder`; recoverable gear is restored before that
remainder can produce the final stop.

Naked-with-gear invariant: when transaction-owned wearable gear is in the pack
and no danger blocks town maintenance, the next public `choose_key` decisions
are equip commands until that gear is worn.  A stale restore latch or missing
session cannot hand control to ordinary town policy and cannot emit a terminal
wait while such an equip action exists.

Pins:

- `test_public_no_session_latched_restore_dresses_pack_again` starts with ten
  owned pack items, no session, the restore latch set, and the stale terminal
  reason set; all ten public decisions equip the items and empty ownership.
- `test_blocked_restore_reaches_visible_named_terminal` restores the reachable
  prefix before exposing and reporting one genuinely missing identity.
- `test_named_infinite_wait_is_not_a_drive_ending_terminal` fails a synthetic
  named infinite wait on its fourth identical decision.

Historical `158a35e` result for the public dress-again shape was
`AssertionError: ([('5', 'equipment-transaction:restore-blocked-terminal')],
0, None)`.  This is the same reason emitted by all 959 measured incident
decisions.  The old harness classified a visible label immediately and could
therefore pass such a named wait; under the strengthened rule the synthetic
replay fails after four consecutive decisions.  All 18 unique seed factories
are green at tip under the drive-ending rule; no tip seed succeeds merely by
repeating a named wait.

## 2026-08-09 owned-loadout derivation review fix event

The public `choose_key` incident pin now holds the 47-item owned equipment
catalog fixed and compares the complete selected slot-to-item loadout while
recall depth varies independently through 30F, 31F, 32F, 33F, 34F, and 35F,
then pack item count changes, then gold changes.  Every decision selects the
identical loadout.  The independent public classifier pin covers the real
character loadout plus 20F and 30F synthetic loadouts; against `4664f6c` it
fails by observed values (`2 != 19`, `2 != 20`, and `2 != 30`), not import
failure.

The four surviving fallback-era test names were rewritten as:

- `test_alternate_selection_picks_deepest_dungeon_at_or_below_limit`
- `test_owned_loadout_depth_is_not_inferred_from_recall_destinations`
- `test_alternate_selection_uses_recall_landing_not_entrance_depth`
- `test_bounded_alternate_selection_can_use_the_yeek_cave`

Verification used the codex primary runtime with `PYTHONPATH=src`.  Test-fakery
lint retained its ratchet of 8 undeclared and 101 declared findings; sale lint
reported zero findings; mutation battery met 5/5 expectations with
`repo_tree_untouched: true`.  Two consecutive full-suite runs each passed 2465
tests with one skip (208.126s and 208.980s).
