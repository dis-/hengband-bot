# Step 1.5a: a full Home closes the equipment swap for the visit; depart with the current loadout

Plan of record: C:\hengband\PLAN-town-stability-20261009.md 手順1.5. Base: main 426eb6ea.
Analysis: STEP1.5-ANALYSIS.md (in this worktree), section 3A / 4A. Design only.

## Owner decisions (verbatim)
- 2026-10-03 21:4x: 「入れ替え失敗は今の装備で出発・記録を残し後で改善」.
- 2026-10-04 05:0x: 「装備入れ替えの失敗は正常動作ではないので記録して後に直す必要はある」 — judged by the abilities
  required at the actual destination depth (recall landing, walk-out floor, fixed quest / fundraising
  floor); departure records reason `optional-optimization-failure-confirmed-loadout`.
- 2026-10-09 01:4x (sale-no-preempt): 「入れ替えが自宅満杯で失敗したら、決定どおり今の装備で出発して記録を残します。」
- Plan P3/P5: no new town owner; scene fixes only for escalation stops; this is plan step 1.5.

## Problem (evidence in STEP1.5-ANALYSIS.md 3A)
25 of the 62 pre-sale owner-retired bursts, plus 17 `equipment-transaction:home-route-repeat-terminal`
stops, are one loop: the equipment transaction must deposit into a full Home, the game refuses, the
transaction is re-planned and walks back to Home, no progress is credited, until the burst or the
repeat terminal stops the bot. The existing "home full" latch
(`_equipment_home_full_refused_this_visit`, policy_equipment.py ~1972; set by
`_mark_equipment_home_full_unavailable` ~1983) needs Home in `blocked_stores` AND the latch site; both
are cleared by `_rearm_town_store_for_new_work(HOME, release_visit_bound=True)` (policy_shop.py ~1593;
callers: departure counterfactual policy_town.py ~3602-3611, atomic withdraw failure policy.py
~7547/7594, weight-overload re-arm policy_town.py ~3397, policy_home.py ~610/772) and by later
`_set_town_store_attempted(HOME, other site)`. The departure gate then re-opens Home for the same
equipment work because equipment-transaction is departure-blocking (policy_town.py:3325) and the
supplier counterfactual skips equipment needs only when `equipment_exhausted` or the arbiter
`_retired` set holds equipment-opt/txn (policy_town.py ~3696-3716) — and log-only mode clears
`_retired` via `forgive_retirement` (cli.py ~568 → town_arbiter.py ~364).

## Design (revision 2, after the fable review)
1. Visit tombstone for equipment Home deposits only. Key = (visit epoch, "equipment plan needs a Home
   deposit"), NOT the target loadout id (review: 134416 re-planned from target f343423f to c3c18aea in
   the same visit, so a target key would not close the loop).
   Set it when either:
   (a) an equipment transaction deposit is refused by a full Home (game message matched at
       policy.py ~7603, or the index-0 pre-check policy_equipment.py ~2168-2184), or
   (b) `_home_is_full(snapshot)` is true from an observed Home page (policy_home.py ~34-37, fed at
       ~1197-1200) and the plan's next Home action is a deposit. (b) makes it re-fire after a process
       restart (capture 191943: the refusal happened in the previous process).
   Not stored in `blocked_stores` / the Home latch; untouched by `_rearm_town_store_for_new_work(...)`,
   `_set_town_store_attempted`, `forgive_retirement`, relief completion (policy_home.py ~605-611).
   Cleared ONLY by a new town visit epoch or by an observed Home page with `stock_num < capacity`.
   Other Home owners (supplies, identification withdrawals, relief, overweight deposits) keep Home
   (5029380e tombstoned on any abandonment/stall and voided EQUIP-only plans — this design does
   neither; its live failure at 17:58 was the in-store half, fixed since by 6d3b124d/dbd97536).
2. Enforcement points (all must read the tombstone):
   - optimizer fresh search (policy_equipment.py ~1468-1487) and the re-arm + fresh search at
     policy.py ~15509: no plan that needs a Home deposit; a PHASE_EQUIP-only plan may still run.
   - approach `home_route_blocked` (~2502).
   - `_departure_supplier_core` (policy_town.py ~3696-3718): equipment-work / equipment-transaction
     are skipped when the tombstone is set — checked directly, not through
     `_equipment_failure_unexecutable_this_visit` (its `_home_owner_goal_pending` is conservatively
     True, policy_home.py ~4043-4048).
   - Use ONE flag: the tombstone drives the existing retire path (`_retire_actionless_equipment_failure`,
     policy.py ~15134-15155 → `_equipment_retired_worn_item_ids` → `equipment_exhausted`) rather than a
     parallel flag; state precisely how in the implementation report.
   - Restore of an open transaction: allowed (PHASE_EQUIP restores from the pack without Home,
     ~1826-1835); a withdrawn item stays in the pack (record it).
3. Departure: existing `_safe_optional_equipment_failure_departure` with required abilities at the
   actual destination depth; record `optional-optimization-failure-confirmed-loadout`. If another
   departure gate still fails (e.g. weight-overload, policy_town.py ~3272), that gate's existing
   visible stop applies (e.g. `town:blocked:overweight-home-unreachable`). Never relax conditions.
   No `equipment-transaction:home-route-repeat-terminal` for this cause; write one record
   `town:work-closed:impossible:equipment-transaction:home-full`.
4. New attributes: defaults in the restore chain (policy_state.py ~194-200 setdefault /
   restore_checkpoint); list them in the report.

## Pins (fail on 426eb6ea, pass after; substrate named; constructed parts declared)
No checkpoints exist; use the test_homefull3_recorded pattern. The last sessions of 134416 (27 rows) and
191943 (15 rows) start at process start, so replay from their s1 needs no constructed policy state;
responses after the first changed command are constructed and declared.
1. 134416 and 191943: no second equipment Home session, no `home-route-repeat-terminal`; the next stop is
   the overweight one (`town:blocked:overweight-home-unreachable`) — both are overweight with Home full.
2. Constructed non-overweight variant (declared): tombstone set → departure via the confirmed-loadout
   path with the record above.
3. 1007-044510 s9-s10 regression: after `eq:deposit-home-full` the next decision is not
   `eq:atomic-deposit` / `approach-home`.
4. Unit: tombstone survives `_rearm_town_store_for_new_work(HOME, release_visit_bound=True)`,
   `forgive_retirement()`, and relief completion; supplies/withdrawals and the overweight deposit still
   route to Home.
5. Unit: observed Home page with stock < capacity, or a new epoch, clears it.
6. Restart re-fire: fresh policy, Home observed full and the plan needs a deposit → tombstone set without
   a refusal in this process (191943 shape).
7. A PHASE_EQUIP-only plan still executes under the tombstone.
8. Constructed deeper destination with missing abilities → today's visible stop, not departure.

## Expected effect and risk
Closing equipment frees the departure gate, which then shows the next failing gate. In both recorded
captures that is the overweight stop (Home full + weight-overload deposit), i.e. step 1.5a alone turns
those two from an equipment terminal into the overweight stop; the overweight case is the next step-1.5 item. That is intended: the next stop is a different, real need (handled by
the 10-05 stock-out mining decision or the next step-1.5 item). Overweight-with-full-Home stops (10)
are not solved here.

## Hygiene
manifest regeneration; tests.test_ownership_s2b1_ladder, test_town_structure_lint, test_item_sink_lint,
test_town_work_contract, test_ownership_s2a1_closure, test_test_fakery_lint, test_town_arbiter, plus the
regression modules that broke 5029380e: tests.test_experience_potion, tests.test_unaffordable_claim_tour_recorded,
tests.test_homefull3_recorded, tests.test_magic_required_staff_homefull_recorded, and the equipment
transaction / Home-full modules touched. No full suite (the merge gate runs it).
