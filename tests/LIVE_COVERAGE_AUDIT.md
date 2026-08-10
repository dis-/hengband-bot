# Live coverage audit fix event

## 2026-08-10 initial decision-log audit

Command:

```text
py -3 scripts/live_coverage_audit.py jsonlog/evidence-double-recall-read.jsonl jsonlog/evidence-identify-staff-departure-loop.jsonl
```

The two logs contained 36 distinct reasons and 21 distinct composed key shapes. The audit reported these
17 distinct orphans (combined occurrence counts):

```text
ORPHANED key-shape "\x1b`n'." count=4
ORPHANED key-shape '5do\x1b' count=2
ORPHANED key-shape 'Cf\ry\x1b\x1b' count=13
ORPHANED key-shape '\x1b`n#.' count=10
ORPHANED key-shape '\x1b`n$.' count=4
ORPHANED key-shape '\x1b`n&.' count=6
ORPHANED key-shape 'pl\r' count=1
ORPHANED key-shape 'pm3\r\r' count=4
ORPHANED key-shape 'pq21\r\r' count=2
ORPHANED key-shape 'pq27\r\r' count=2
ORPHANED key-shape 'pq42\r\r' count=2
ORPHANED key-shape 'rha' count=2
ORPHANED key-shape '{n@0\r' count=2
ORPHANED reason shop:batch-sell count=15
ORPHANED reason shop:buy-healing count=1
ORPHANED reason shop:sale-inscription-unobserved-leave count=2
ORPHANED reason town:wait-restock:temple count=2
```

The exit status was 1, as required by the default zero-orphan gate.

## 2026-08-10 depth-first optimization fix event

The unconstrained equipment selector now evaluates the requirement-free optimum
first, then considers the 81, 50-80, 40-49, 31-39, 26-30, 21-25, 20, and
requirement-free 19 bands in descending order.  Each satisfying band is adopted
only when its melee output is at least one half of the free optimum; zero free
melee uses ability-only classification.  The result and live policy telemetry
record every considered band with set existence, band melee, free melee, ratio,
and `no-set` or `melee-ratio` refusal, plus the chosen band and ratio.

Known-flags-only evidence remains authoritative.  The optimizer equivalence key
now retains the known depth-gate flag set so a metric-equivalent FA/rConf item is
not erased before band descent.  The live-catalogue regression records the base
result in its docstring: `dee4194 classified this catalogue at 19`; the fixed
selector derives 25 while retaining the rFire katana.

Pins added in `tests/test_equipment_optimizer.py` cover the live catalogue,
one-band retry after an 81-band melee-ratio refusal, requirement-free termination,
zero-melee ability classification, and every-band telemetry.

Scenario transfer: no old depth/classification test was deleted, renamed, or
changed.  All old scenarios remain in their original tests; the five new scenarios
live in the five depth-descent tests named above.

The live coverage command used the standing evidence pair because the default
evidence glob encountered a pre-existing UTF-8 BOM.  It reported these 16 orphans:

```text
key-shape "\x1b`n'."; key-shape '5do\x1b'; key-shape 'Cf\ry\x1b\x1b';
key-shape '\x1b`n#.'; key-shape '\x1b`n$.'; key-shape '\x1b`n&.';
key-shape 'd0\r'; key-shape 'pl\r'; key-shape 'pm3\r\r';
key-shape 'pq21\r\r'; key-shape 'pq27\r\r'; key-shape 'pq42\r\r';
key-shape '{n@0\r'; reason shop:buy-healing;
reason shop:sale-inscription-unobserved-leave;
reason town:wait-restock:temple
```

## Home random-teleport suppression one-shot fix event

time: `2026-08-10T09:03:41.5596751+09:00`

Measured chain: the fixture copied from
`jsonlog/evidence-home-stop-cycle.jsonl` records a complete `~9` scan of 117
items, the selected incomplete Home sword
`home:b57f63b4c7ce1c07:0` (`tval=23`, `sval=25`), and the repeating
`shop:approach` -> `store:entry-await-observation` ->
`home:store-context-exit` cycle.  Every copied cycle record has
`town_plan.index=0`; the later records reach `town:blocked:repetition` waits.
At `81f86dc`, the public replay emitted only `5` where the fixed route emits
`5 pa\x1b`, and its absorbing seed failed on decision 4 with
`visible terminal repeated without ending drive`.

One-shot composition: selected Home-origin suppression now arms the standard
outside `_home_pending_item` address.  At the Home entrance, the completed
knowledge order and observed 12-item page size derive page 1, page-relative
letter `a`, and compose `5 pa\x1b` (entry, one page, take, exit) as a single
posted decision.  The observed pack delta completes the original Home plan
stop; the existing pack branch then emits `{q.\r`.  A zero-space public pin is
owned by the pre-existing `01k<slot>` disposal path and never posts `p`.

Scenario transfer:

- The old in-store scenario
  `GlobalEquipmentOptimizationOwnershipTest.test_withdraws_home_random_teleport_item_before_inscribing`
  remains under the same name and now covers outside arming; the deleted
  `home:queue-random-teleport-for-inscription` branch has no remaining test or
  producer.
- Its former store-page selection/leave behavior transfers to
  `test_home_random_teleport_uses_derived_page_address_then_pack_inscription`,
  which covers the copied cycle, public page-relative composition, observed
  Home-stop completion, and the existing outside inscription.
- Pack-origin direct inscription remains in
  `test_inscribes_pack_random_teleport_item_in_town`.
- Zero-space deferral lives in
  `test_zero_pack_space_defers_home_suppression_to_existing_disposal`.
- The approach/exit liveness scenario lives in absorbing seed
  `home-random-teleport-suppression-one-shot`.

The live coverage audit of the preserved evidence reports these six existing
orphans: key shapes `5pY\x1b`, `Cf\ry\x1b\x1b`, `wn`, and `wnd`; reasons
`equipment-transaction:await-confirmation-leave-home` and
`home:atomic-withdraw-target-unobserved`.  The deleted
`home:queue-random-teleport-for-inscription` reason is absent from the orphan
list.

## 2026-08-10 retroactive `400be44` home-suppression-one-shot fix event

time: `2026-08-10T10:07:05.9377068+09:00`

The measured `~9` catalogue contained 117 Home items and selected the incomplete
Home sword `home:b57f63b4c7ce1c07:0`. The incident repeatedly approached and
left Home with `town_plan.index=0`. `400be44` replaced the obsolete in-store
selection with an outside-armed, catalogue-addressed one-shot: item index 12 at
observed page size 12 composes `5 pa\x1b`, observes the pack delta, then follows
through with the outside `{q.\r` inscription. Its pins cover derived page
arithmetic, one complete sender key, outside arming, pack inscription, zero-pack
disposal, bounded catalogue size, and the registered absorbing seed. The
historical `81f86dc` seed fails across 20 decisions with zero progress and nine
Home entries/exits; the `400be44` route reaches the withdrawal.

Scenario transfer: the in-store selection scenario remained under
`test_withdraws_home_random_teleport_item_before_inscribing`; store addressing
and follow-through moved to
`test_home_random_teleport_uses_derived_page_address_then_pack_inscription`;
pack-origin inscription remained in
`test_inscribes_pack_random_teleport_item_in_town`; zero-space handling moved to
`test_zero_pack_space_defers_home_suppression_to_existing_disposal`; and the
approach/exit liveness scenario moved to absorbing seed
`home-random-teleport-suppression-one-shot`.

## 2026-08-10 deferred Home-suppression remediation fix event

time: `2026-08-10T10:07:05.9377068+09:00`

A refused suppression take now records its signature in
`_deferred_home_items`, cannot re-arm the outside withdrawal, and is no longer
actionable to equipment departure readiness. The public refusal world runs
eight decisions, posts `5 pa\x1b` exactly once, retains the deferred signature,
and bounds `home:atomic-withdraw-target-unobserved` to at most one occurrence.
An arming-guard-only scratch mutation produced seven such spins in the same
eight-decision drive; the restored tip produced zero. Deferred suppression
therefore follows the existing departure rule: deferred means not actionable,
so a confirmed loadout may proceed instead of requiring another Home take.

Observed suppression completion now passes through the `NeedSpec` registry;
the temporary bypass flag was deleted. Atomic-withdraw pass reporting is
limited to the suppression owner, so a twelve-item calibration restore retains
its one catalogue Home pass and adds no restore-withdraw visits, need attempts,
or unsatisfied passes. Arming is outside-only and uses
`_town_pack_space_ready` with `MIN_FREE_PACK_SLOTS`. The evidence fixture's
sequence-29 row is emitter-shaped verbatim, with `incomplete_items` and
`incomplete_item_details` nested under `equipment_optimization`.

The happy-path registered seed enters and exits Home once, observes the
withdrawal, and posts the outside inscription on decision 2. It passes
byte-identically at `400be44` and therefore does not discriminate the deferred
re-arming guard. The separate
`home-random-teleport-suppression-refusal` seed uses the refusal world: at
`400be44` it exhausts 20 decisions with
`home:atomic-withdraw-target-unobserved` repeated 19 times, while at `9290496`
and the current tip it defers the take once and reaches a different decision.
The default five-mutation battery passed 5/5 with
`repo_tree_untouched: true`, sale-key lint reported zero violations, and the
fixture-only live coverage audit reported this one existing orphan:
`key-shape 'Cf\ry\x1b\x1b'`.

Scenario transfer:

- No test was deleted or renamed, and zero test names were lost.
- The existing one-shot public scenario remains in
  `test_home_random_teleport_uses_derived_page_address_then_pack_inscription`,
  now also pinning registry evaluation and the nested verbatim fixture shape.
- Its outside-only and pack-capacity premises are additionally pinned by
  `test_home_suppression_arming_is_outside_and_uses_town_pack_predicate`.
- Deferred departure actionability lives in
  `test_deferred_home_suppression_is_not_actionable_for_departure`.
- Refused-take liveness lives in
  `test_refused_home_suppression_take_defers_once_and_does_not_rearm`.
- Calibration pass ownership remains in
  `test_public_calibration_restore_converges_twelve_items`.
- The unchanged seed name `home-random-teleport-suppression-one-shot` owns the
  withdrawal-plus-inscription happy path; it does not pin the deferred guard.
- `home-random-teleport-suppression-refusal` owns the `400be44` historical
  failure and pins release from the guard-reverted absorbing shape.

## 2026-08-10 store-input-ownership fix event

time: `2026-08-10T12:46:37.0193204+09:00`

The killer-1 gate hole was measured in the policy state machine: only an
explicit entrance WAIT and `_step_toward`'s disclosed one-tile destination
armed `_store_entry_posted_owner`. Native `shop:approach` travel can run all
the way onto the store tile without another bot snapshot, but its composed
travel key was never registered as a possible entry. The ledger's `9` took
that uncovered path. Native store travel now owns the same lagged observation
barrier before any store operation can compose.

| Killer-1 replay | aadc336 | fixed |
| --- | --- | --- |
| approach post | ``\x1b`n%.`` (the captured landmark is `9`) | same |
| post confirmed as possible entry | `False` | `True` |
| lagged surface decision | key `8`, reason `probe` | key empty, reason `store:entry-await-observation` |
| next store operation | could race entry flush | composes only from the observed store page |

Historical aadc336 failure: `AssertionError: d raced entry flush: no
store:entry-await-observation` (observed output: `confirm False`, `lagged '8'
probe`).

| Killer-2 replay | adb6d53 | aadc336 | fixed |
| --- | --- | --- | --- |
| fresh authoritative store page | ownerless ESC posted | ESC refused | `wait` |
| genuine stall past configured 1.5s bound | ownerless ESC posted | still refused forever | `incident_stop('store-input-ownership-stall')` |
| vanished out-of-store window | send failure did not arm terminal recovery | same | failed attempts count toward `TERMINAL_NUDGE_LIMIT` |

Historical adb6d53 failure: `AssertionError: ownerless ESC posted into open
store prompt` with `sent True posted ['\x1b']`. Historical aadc336 failure:
`AssertionError: unbounded absorbing refusal: no bounded leave or
incident_stop` with `sent 0 posted []` after twenty attempts.

| Killer-3 buy-confirm replay | adb6d53 | fixed |
| --- | --- | --- |
| open prompt owner | `shop:await-buy-confirmation` | same |
| foreign answer | `shop:leave` / Escape | sender refuses and retains marker |
| fallback state | unchanged exhausted buy window | wait count reset to 0 and generation rebound to the purchase owner |
| completion | confirm could not complete through the foreign-owner fallback | observed pack +1 and gold -20 clear `_store_buy_inflight` |

Historical adb6d53 failure: `AssertionError: foreign shop:leave refusal has no
purchase-owned fallback; confirm cannot complete`; the inflight tuple was
unchanged before and after refusal.

Batch-sale composition now resolves `(name, tval, sval)` together with the
sale inscription. A missing or colliding foreign inscription returns no sale
key and records `shop:batch-sale-signature-unobserved` instead of leaking
`StopIteration`. Post-sale survivor verification also uses its exact sale tag.

Scenario transfer:

- `test_repeated_store_refusals_cannot_arm_terminal_recovery`, which asserted
  the absorbing state, is replaced by
  `test_store_recovery_waits_fresh_then_ends_drive_at_stall_bound`; the former
  dead-window half transfers to
  `test_failed_window_send_still_reaches_terminal_attempt_bound`.
- The unchanged ownerless-ESC scenario remains in
  `test_live_store_transaction_refuses_unowned_stall_escape`.
- Native entry-flush ordering lives in
  `test_native_store_travel_owns_lagged_entry_observation`.
- Foreign buy-confirm ownership and completion live in
  `test_preserved_sale_prompt_rejects_foreign_escape_owner`,
  `test_live_shaped_recall_purchase_completes_with_gold_and_pack_delta`.
- Sale completion and inscription collision live in
  `test_live_shaped_sale_reaches_price_confirm_and_gold_delta` and
  `test_batch_sale_missing_or_foreign_inscription_is_visible_refusal`.
- `test_batch_straggler_advances_attempt_and_does_not_rebatch` keeps its name;
  its survivor now truthfully retains the `@1` inscription of the refused
  sale. No scenario or test name was otherwise lost.

The evidence ledger live-coverage audit reports seven existing orphans: key
shapes ``\x1b`n'.``, `Cf\ry\x1b\x1b`, ``\x1b`n$.``, ``\x1b`n&.``, `pj2\r\r`, and
`rhe`; and reason
`town:entrance-step-off:town:await-recall-confirmation`. The default mutation
battery passed 5/5 with `repo_tree_untouched: true`; sale-key lint reported
zero violations; changed-file fakery lint introduced zero new violations. The
real-repository full suite passed twice with `PYTHONPATH=src` and the mandated
runtime: 2,518 tests in 221.200s and 2,518 tests in 215.354s, both `OK
(skipped=1)`.
