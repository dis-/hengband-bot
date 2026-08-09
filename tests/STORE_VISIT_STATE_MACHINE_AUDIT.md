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
