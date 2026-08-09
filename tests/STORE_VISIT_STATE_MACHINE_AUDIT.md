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
