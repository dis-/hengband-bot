# Town store claim projection audit

The town route is now derived on every decision from
`_enumerate_live_store_claims`.  Its owner list is explicit: the established
need registry supplies catalogue and queued-identity Home work,
identification, procurement, disposal, fundraising, curse, sale, and optional
shopping owners; calibration/optimizer work and executable equipment
transactions are added as state-machine owners.

`TownErrandPlan` is only an ordered projection.  A missing or exhausted view,
or a newly appearing category after a visited stop, cannot suppress a live
claim.  `TownVisitLedger.blocked_stores`, `approach_fails`, and
`unsatisfied_passes` remain the terminal authorities.  Home therefore keeps
the unchanged 54-pass equipment-work ceiling and ordinary stores keep
`TOWN_STOP_PASS_LIMIT`.

Deleted cached-plan repair state:

- `HengbotPolicy._completed_home_can_rearm`
- `TownVisitLedger.rearmed_categories`
- `TownErrandPlan.rearmed_home_categories`
- the category re-arm guards and mutations in the exhausted/attempted plan
  branches

Their guarantee is provided by comparing the current claim projection with
the prior ordering view; the ledger, rather than re-arm state, supplies every
hard stop.  Telemetry is renamed from `home_route_rearm` to
`home_route_projection`.  Runtime reason strings and named terminals are
unchanged.

Historical tests retain their names.  Expectations that a completed cached
stop suppresses a still-live owner now assert reacquisition; insertion and
re-arm bookkeeping assertions now inspect projected stops/categories and the
unchanged ledger bounds.

## 2026-08-08 fix event

Reproducible owner list: need-registry owners (catalogue/queued Home identity,
identification, procurement, disposal, fundraising, curse, sale, optional
shopping), calibration/optimizer equipment work, and executable equipment
transactions.  The deleted fields and branches are listed above; current
claim enumeration plus ledger bounds replace them.

Declared expectation changes: completed or exhausted cached stops no longer
suppress live claims; newly projected stops do not populate
`inserted_this_visit`; removed re-arm telemetry/bookkeeping assertions now
inspect `need_categories`, `home_route_projection`, and ledger counters.  The
identification handoff pin now observes that its live Home claim routes before
the former exhausted-plan deferral transition.  No runtime reason string or
named terminal was renamed.

Pins: public `choose_key` tests cover a null plan, an exhausted plan, and new
calibration work after Home was visited; the 54-pass exhaustion pin still
installs `equipment-work-home-route-exhausted`.  Existing public pins retain
the Home `~9` catalogue request, atomic deposit/withdrawal provenance and wrap
proof, departure/confirmed-loadout invariants, entrance observation rules,
absorbing terminals/loop detector, and danger/escape gates.

Verification: mutation battery 5/5 with `repo_tree_untouched: true`;
test-fakery lint remains at its ratchet of 9 undeclared and 116 declared
findings; test names are 2509 versus 2508 at `840010b` (zero losses); two
consecutive full runs each passed 2509 tests with one opt-in skip.
