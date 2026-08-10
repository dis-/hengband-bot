# Store visit ownership and no-progress refusal fix event

## 2026-08-09 end-the-oscillation-class fix event

`StoreVisit` is the single store-context authority.  The owner and purpose are
fixed when an approach opens the visit.  Its phases are `approaching`,
`entering`, `operating`, `leaving`, and `closed`; `composed_key` belongs to the
same record.  Entry confirmation and store observations transition that record,
and closure records one of `completed`, `abandoned-with-restore`, or
`refused-with-evidence`.  A Home page without a visit is recovery-only and
exits.  An existing equipment transaction observed on Home is imported once as
an operating visit, so the transaction that caused the trip retains ownership.

The independent fields replaced as authorities are
`_shopping_approach_store_type`, `_shopping_approach_goal`,
`_store_entry_wait_owner`, `_store_entry_wait_key`,
`_store_entry_posted_owner`, `_store_leave_inflight`, and
`_home_entry_operation_posted`.  Their old names are compatibility properties
over `StoreVisit`, not storage and not alternative decision inputs.  Equipment
transaction session, removed-item restore inventory, and failure evidence stay:
they describe the visit's operation and recovery obligation, not store-context
ownership.

At public `choose_key`, `EmissionState` defines equivalence as the same floor
and position, the same store type (including outside-store `None`), and identical
order-neutral projections of every pack and worn item: slot, base kind, name,
quantity, charges, inscription, knowledge, and equipment status.  Floor and
position identify physical state; store type identifies the active command
language; pack and equipment cover every resource or loadout change relevant to
the incident.  Messages, policy latches, and decision reasons are deliberately
excluded because disagreeing owners can change them without game progress.

The recurrence map is a rolling decision-stream window: each equivalent state
replaces its prior occurrence.  When a store-owned sequence returns through a
different state, proposes the same next key, and game turns advanced less than
the recurrence's own decision span, the transition is proven ineffective.  It
is refused immediately as the existing visible `livelock:exhausted` stop.  No
retry count, cap, cooldown, or owner-specific exception participates.

Pins include unique absorbing factories for all four historical shapes:
`visit-scan-address-burst`, `visit-abandon-blocked-home`,
`visit-approach-entrance-stepoff`, and `visit-live-shop-entry-exit-531`.  The
last retains the live 531-occurrence `shop:approach` -> `entry-await` ->
`store-context-exit` incident shape and proves the equipment/Home owner remains
attached.  The catalogue test drives all four through public `choose_key`.

## 2026-08-09 evidence-binding fix event

The four visit seeds no longer alias older hand-built worlds. Their compact
frames are copied from the preserved decision stream: archived decisions
4050-4052 for `home:scan-address-burst`, decisions 40-42 for
`equipment-transaction:abandon-blocked-home`, the 2026-08-07 02:57:15
entrance-step-off onset, and decisions 26-28 of the 4,390-decision run for the
live approach/entry/Home-exit cycle. Each is driven through public
`choose_key`; replaying the archived burst without irreversible game progress
must end at `livelock:exhausted`.

The same seeds at parent `286ac7e` failed historically as follows:

- `visit-scan-address-burst`: `decision bound exhausted`; 20 decisions,
  10 scan bursts and 10 Home exits.
- `visit-abandon-blocked-home`: `decision bound exhausted`; 20 decisions,
  7 approaches, 7 entry waits, and 6 blocked Home exits.
- `visit-approach-entrance-stepoff`: `decision bound exhausted`; 20 decisions,
  7 approaches, 7 entrance step-offs, and 6 Home scan pages.
- `visit-live-shop-entry-exit-531`: `decision bound exhausted`; 100 decisions,
  34 approaches, 33 entry waits, and 33 Home context exits.

## 2026-08-10 non-Home state-based routing fix event

time: `2026-08-10T21:55:53.9185568+09:00`

Measured mechanism (`jsonlog/evidence-recharge-block-wander.jsonl`, replayed
through the public decision boundary): Magic (5) and Home (7) were both entered
in `blocked_stores` with `unsatisfied_passes == 3` under
`TOWN_STOP_PASS_LIMIT == 3`; Temple (3) remained at one pass. The Magic page at
decisions 15 and 19 exposed an affordable Identify staff (`h`, 917 gold, 21
charges) but reported it as `preempted`. Decision 22 posted the successful
organization sale `d1y<Esc>`, then decision 26 exposed an affordable device
(`f`, 541 gold, 20 charges) and again reported `preempted`. The public trace
contains no buy composition; decisions 49 onward are `stuck:wander`.

Non-Home routes now ignore `blocked_stores`, `unsatisfied_passes`,
`need_attempts`, and `approach_fails` as count authorities. A live NeedSpec
claim remains routable after an observed buy or sale. A visit that leaves its
claim unsatisfied without an observed operation effect records
`attempted-without-effect` against durable store state (store
stock/page/context, messages, pack/equipment, and gold); an equivalent state
cannot route it again. Turn passage and raw walking position are deliberately
excluded, because WAIT and wandering are not store effects. Any changed durable
store state releases the refusal. There is no retry tally, cooldown, cap, or
tuning constant.

When every remaining live non-Home claim is refused by that equivalence, the
drive latches the visible `town:blocked:departure-unsatisfiable` exit. This is
structural: every attempt either changes the finite observable game state and
permits a newly evaluated route, satisfies a claim, or enters the visible exit;
an equivalent no-effect state cannot emit the route again.

Scenario transfer:

- `test_blocked_store_ledger_kills_departure_blocking_claim` ->
  `test_nonhome_count_block_does_not_kill_departure_blocking_claim`.
- `test_exhausted_need_budget_kills_departure_blocking_claim` ->
  `test_nonhome_need_count_does_not_kill_departure_blocking_claim`.
- `test_exhausted_approach_failures_kill_departure_blocking_claim` ->
  `test_nonhome_approach_count_does_not_kill_departure_blocking_claim`.
- `test_non_home_leave_blocks_reopened_out_of_stock_stop` retains its name but
  now pins state-equivalence refusal and the visible terminal after one
  no-effect visit.
- `test_cross_town_identify_capture_starts_travel_instead_of_visible_stop`
  replaces its synthetic attempt count with an equivalent-state refusal.
- Home scenarios are not transferred: the ordinary three-pass bound, the
  calibration 54-visit ceiling, Home pass ledger, and block authority remain
  byte-for-byte on their original decision path.

Live-coverage audit of the preserved fix evidence reports seven pre-existing
orphans: key shapes `Cf\ry<Esc><Esc>`, `<Esc>\`n$.`, `<Esc>\`n&.`,
`d1y<Esc>`, and `{j@1<Enter>`, plus reasons `shop:observe-and-leave` and
`shop:one-shot-sell`. The changed tests add no source-text-only decision fake.

Verification: the mandated full suite passed twice at tip (2,539 tests in
221.037s and 221.678s, one existing skip each). The mutation battery passed
5/5 with `repo_tree_untouched: true`; sale-key lint reported zero violations.
At historical base `830690d`, the transferred count-retirement pins fail by
construction because count-blocked, count-budget-exhausted, and
count-approach-exhausted non-Home claims are discarded, while the retained
evidence proceeds from decision 49 as `stuck:wander` with no buy.

## 2026-08-11 absorbing-seed restoration and alternation-bound fix event

time: `2026-08-11T01:47:27.0653803+09:00`

Restored `invalid-command-noop-home-cycle` verbatim from the `092c42e` blob
and kept it registered.  The catalogue now contains 27 unique seeds.  The
seed had been silently deleted by `63c799a`; a failing absorbing seed is
evidence and must not be removed to make a change pass.

The CLI previously reset `blocked_streak` in
`_advance_town_blocked_streak` whenever an emitted decision reason was
neither `town:blocked:*` nor `shop:leave`.  Thus a real `R300\r` restock wait
erased the preceding blocked decision.  The fuse now compares each observed
snapshot with the existing `_town_observable_effect_state` projection.  Only
an observed durable store effect resets the streak; once a block is observed,
interleaved no-progress restock waits, rests, wandering, and other filler
decisions advance it.  `shop:leave` retains its established non-counting,
non-resetting treatment.  No constant or gate changed;
`TOWN_BLOCKED_STOP_LIMIT == 30` remains the bound.

Blast-radius confirmation covers all six block reasons released by per-
decision re-derivation: `restocked-recall-store-unreachable`,
`dominated-item-destroy-failed`, `departure-no-light`, `digging-tool-lost`,
`equipment-home-unavailable`, and `equipment-departure-incomplete`.  The last
two originate in `_terminal_equipment_blocker`.  Each reaches the same bounded
visible fuse through an alternating no-progress filler row.

The authored `StaleVerdictWorld.visible_terminal` override was removed; the
stale-verdict seed uses the real terminal protocol.  The fixture-literal
`test_stale_restock_evidence_chain_and_walkable_store_are_preserved` and its
now-unused JSON fixture were deleted.  The three drive-ending terminal latches
are each exercised across 40 materially distinct observations.

Measured restored-seed results:

- `63c799a`: FAIL, decision bound exhausted; 40 decisions, 20
  `town:wait-restock:temple`, 20
  `town:blocked:restocked-recall-store-unreachable`, zero durable progress.
- tip: PASS, drive-ending `town:blocked:*` fuse; 31 decisions, 16 restock
  waits and 15 blocked rows, zero durable progress.
- `092c42e`: PASS, drive-ending `town:blocked:*` fuse; 31 decisions, one
  restock wait and 30 blocked rows, zero durable progress.

The `63c799a` fix event claimed +3 test names, but the historical source delta
is +4 names.  This remediation measures 2,545 tests, +1 versus the required
2,544 baseline, with one existing skip.  The mandated full suite passed twice;
the 27-seed absorbing catalogue passed; mutation battery passed 5/5 with
`repo_tree_untouched: true`; sale-key lint reported zero; and the repository
fakery guard reported no new undeclared/source-text-only shape.  The stale-
latch parent behavior remains the required `'5' != '6'` failure, while the
durable-refusal and terminal-latching pins remain green.
