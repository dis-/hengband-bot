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
