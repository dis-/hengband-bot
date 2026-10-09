# Step 1.5 analysis: mandatory-need owner-retired bursts (pre-sale)

Scope: read-only analysis for PLAN-town-stability-20261009.md step 1.5. Source at main 0de5658d
(C:\hengband\bot-client). Data: jsonlog\autorecover-*-owner-retired-burst.* (76 files 10-06..10-09),
autorecover.jsonl, owner-retired-log-only.jsonl. "Pre-sale" = the 61 bursts before 10-08 14:00 plus
20261009-030659 (equipment_sale telemetry present but `active_store` null and no `yield-for-equipment-sale`
row in its last 60 rows). Every other burst after 10-08 22:28 has active sale rows and is excluded.
Each capture file holds several sessions; only the LAST session (after the last restart) was read.
Scripts were ad-hoc (scratchpad), no repo file touched.

## 1. Pre-sale bursts (62)

Columns: capture (MMDD-HHMMSS) | loop class (section 2) | two most-visited stores in the last 30 rows |
top two non-bookkeeping reasons in the last 30 rows (`eq:`=equipment-transaction, `tpi:`=town-progress-invariant,
`blk:`=town:blocked) | owners named in the last three arbiter retirements | observed change in the last 30 rows.
Effect column: `store_visit.operation_effect_observed` is false in EVERY row of all 62 captures, so the
only row-level evidence is pack-slot count / gold drift (a proxy, not a matched business effect).

| capture | cls | stores | dominant reasons | retiring owners | pack/gold change |
| --- | --- | --- | --- | --- | --- |
| 1006-091923 | B1 | Alch/Home | tpi:defect:full-destroy-await=>same; eq:seek-home-page | detectors | inv 10-12 |
| 1006-092325 | A | Home/Magic | eq:seek-home-page; home:atomic-deposit | equipment-txn,shop-sell | inv 8-11 gold 22526-23369 |
| 1006-204140 | A | Alch/Home | shop:approach; survival:mana-absorb | equipment-txn | inv 13-14 gold 7934-10079 |
| 1006-214921 | B3 | Magic/Home | shop:approach; blk:home-full-surplus-withdraw-failed | town-plan | gold 9312-11372 |
| 1007-031234 | B1 | Alch/Home | tpi:defect:full-destroy-await=>same; shop:approach | detectors | inv 19-20 gold 18871-23076 |
| 1007-032651 | B3 | Home/Alch | no-wait:least-visited; blk:home-full-surplus-withdraw-failed | town-plan | none |
| 1007-032835 | A | Home/Wpn | policy:none-store-exit; eq:await-confirmation | equipment-txn,misc | inv 20-21 |
| 1007-033045 | A | Home/Wpn | eq:travel-home:await-entry; home:atomic-deposit | equipment-txn,misc | inv 20-21 |
| 1007-033136 | A | Home/Wpn | eq:travel-home:await-entry; policy:none-store-exit | equipment-txn,misc | none |
| 1007-033227 | A | Home/Wpn | eq:travel-home:await-entry; policy:none-store-exit | equipment-txn,misc | none |
| 1007-035901 | A | Home/Wpn | eq:catalogue-request-knowledge; eq:travel-home:await-entry | equipment-txn,misc | none |
| 1007-040004 | A | Home/Wpn | eq:catalogue-request-knowledge; eq:travel-home:await-entry | equipment-txn,misc | none |
| 1007-040135 | A | Home/Wpn | eq:catalogue-request-knowledge; eq:travel-home:await-entry | equipment-txn,misc | none |
| 1007-044510 | A | Home/Wpn | eq:approach-home; eq:await-confirmation | equipment-txn,misc | none |
| 1007-044654 | A | Home | eq:approach-home; eq:await-confirmation | equipment-txn,misc | none |
| 1007-044827 | A | Home/Wpn | eq:await-confirmation; eq:approach-home | equipment-txn,misc | inv 20-21 |
| 1007-073331 | A | Home/Wpn | eq:approach-home; eq:await-confirmation | equipment-txn,misc | none |
| 1007-073505 | A | Home/Wpn | eq:await-confirmation; eq:approach-home | equipment-txn,misc | inv 20-21 |
| 1007-073628 | A | Home/Wpn | eq:approach-home; eq:await-confirmation | equipment-txn,misc | none |
| 1007-093545 | B3 | Magic/Home | blk:home-full-deposit-retry-unreachable; shop:approach | town-plan | inv 13-16 gold 10803-11875 |
| 1007-111342 | C | Magic/Home | shop:one-shot-buy; tpi:continue-observed-shop | store-router | inv 16-17 gold 7917-9693 |
| 1007-113809 | B3 | Home/Magic | blk:home-full-deposit-retry-unreachable; shop:one-shot-buy | town-plan | inv 17-20 gold 7129-8785 |
| 1007-121740 | A | Home/Magic | eq:approach-home; policy:none-store-exit | equipment-txn,misc | inv 17-18 |
| 1007-122255 | A | Home/Magic | policy:none-store-exit; shop:approach | equipment-txn,store-router | inv 18-19 gold 2253-28713 |
| 1007-123402 | A | Home/Alch | policy:none-store-exit; eq:approach-home | equipment-txn,misc | inv 17-19 gold 14209-16354 |
| 1007-130228 | B3 | Magic/Home | blk:home-full-deposit-retry-unreachable; shop:approach | town-plan | inv 14-17 gold 7532-8396 |
| 1007-140504 | A | Home/BM | eq:approach-home; policy:none-store-exit | equipment-txn,misc | inv 14-16 gold 1252-4567 |
| 1007-155645 | C | Magic/Alch | shop:approach; tpi:continue-observed-shop | detectors,store-router | inv 18-19 gold 7812-8352 |
| 1007-161624 | A | Home/Wpn | eq:travel-home:await-entry; policy:none-store-exit | equipment-txn,misc | inv 19-21 gold 10259-13685 |
| 1007-174859 | B4 | Home/Magic | shop:approach; home:full-queue-surplus-withdraw | home-errand,home-visit | inv 13-14 gold 5929-6644 |
| 1007-175851 | A | Home/Magic | policy:none-store-exit; eq:approach-home | equipment-txn,misc | inv 17-19 |
| 1007-180645 | D | Home | no-wait:flee; melee | misc | none |
| 1007-184438 | B3 |  | town:kill-mob-approach; blk:no-actionable-claim-owner | town-plan | gold 20326-20375 |
| 1007-205437 | B1 | Alch/Home | shop:approach; tpi:defect:full-destroy-await=>same | detectors,home-visit | inv 20-21 |
| 1007-210411 | B2 |  | home:full-destroy-await-effect; blk:owner-retired-burst | misc | none |
| 1007-213625 | B1 | Alch/Wpn | tpi:defect:full-destroy-await=>same; shop:approach | detectors,home-visit | inv 20-21 gold 6407-9263 |
| 1007-220810 | B1 | Alch/Home | tpi:defect:full-destroy-await=>same; home:atomic-deposit- | detectors,home-visit | inv 18-20 |
| 1007-223915 | A | Home/Wpn | policy:none-store-exit; eq:approach-home | equipment-txn | inv 22-23 |
| 1007-224534 | B3 | Home/Magic | blk:no-actionable-claim-owner; probe | town-plan | none |
| 1007-230439 | B4 | Home/Magic | home-errand:stopped:target-unobserved; shop:approach | home-errand,misc | inv 19-21 gold 17275-18133 |
| 1007-230649 | C | Home/Magic | shop:approach; home:full-queue-surplus-withdraw | home-visit,store-router | none |
| 1008-015858 | B3 | Home | blk:home-full-no-sellable-surplus; home-errand:atomic-withdraw:full-home-discard | town-plan | inv 19-22 |
| 1008-020115 | X | Home/Alch | tpi:continue-observed-shop; eq:atomic-deposit | detectors,home-scan,store-router | inv 13-16 gold 39754-40393 |
| 1008-030326 | B3 | Home | blk:home-full-no-sellable-surplus; home:full-destroy-surplus | town-plan | inv 14-21 |
| 1008-030924 | B3 | Home | blk:home-full-no-sellable-surplus; eq:await-confirmation | town-plan | inv 11-15 |
| 1008-031646 | B3 | Home | blk:home-full-no-sellable-surplus; shop:approach | town-plan | none |
| 1008-043614 | B3 | Home | blk:home-full-no-sellable-surplus; shop:approach | town-plan | none |
| 1008-044025 | B3 | Home | blk:home-full-no-sellable-surplus; shop:approach | town-plan | none |
| 1008-044652 | B3 | Home | blk:home-full-no-sellable-surplus; shop:approach | town-plan | none |
| 1008-051620 | C | Magic/Home | shop:approach; tpi:continue-observed-shop | detectors,store-router | none |
| 1008-051803 | C | Magic/Home | shop:approach; tpi:continue-observed-shop | detectors,store-router | none |
| 1008-051936 | C | Magic/Home | shop:approach; tpi:continue-observed-shop | detectors,store-router | none |
| 1008-071605 | A | Home | eq:approach-home; home:atomic-deposit-await-confirmation | equipment-txn,misc | inv 21-22 |
| 1008-073313 | A | Home | eq:approach-home; home:atomic-deposit-await-confirmation | equipment-txn,misc | none |
| 1008-073530 | A | Home | eq:approach-home; home:atomic-deposit-await-confirmation | equipment-txn,misc | none |
| 1008-090014 | B2 |  | home:full-destroy-await-effect; blk:owner-retired-burst | home-visit | none |
| 1008-091324 | E | Gen/Home | stuck:wander; fundraise:seek-upstairs | detectors | inv 11-14 gold 305-388 |
| 1008-091507 | E | Home | stuck:wander; eq:travel-home | detectors | none |
| 1008-123805 | B2 |  | home:full-destroy-await-effect; blk:owner-retired-burst | home-visit | none |
| 1008-124736 | B2 |  | home:full-destroy-await-effect; blk:owner-retired-burst | home-visit | none |
| 1008-125706 | B2 |  | home:full-destroy-await-effect; blk:owner-retired-burst | home-visit | none |
| 1009-030659 | C | Wpn/Home | shop:approach; shop:observe-and-leave | shop-buy,store-router | inv 19-20 |

Repeated identical states across restarts (P1 evidence): 1007-032835..1007-073628 (13 bursts in 4h, gold 6430,
pack 20-21, same Home deposit refused each time) and 1008-030924..1008-051936 (8 bursts, gold 13695, pack 11).
Home stock observed in state logs at those times: `store.stock_num` 240 on every Home page (1007-044510,
1008-031646, 1008-051620), i.e. the Home is at capacity.

## 2. Loop classes (ranked)

| rank | class | n | producers that alternate | mandatory need (registry, policy_town.py:3250-3333) |
| --- | --- | --- | --- | --- |
| 1 | A eq-txn vs full Home | 25 | equipment-txn (`approach-home`/`travel-home:await-entry`/`await-confirmation`) <-> idle `policy:none-store-exit` (misc) or home-visit `store-context-exit` | equipment-transaction / equipment-work, departure_blocking=True (:3324-3325) |
| 2 | B3 typed block as repeated WAIT | 14 | town-plan alone: `town:blocked:<cause>` WAIT every decision, arbiter retires town-plan each 3 | Home deposit behind full-Home relief (12: home-full-no-sellable-surplus 7, deposit-retry-unreachable 3, surplus-withdraw-failed 2); no-actionable-claim-owner 2 |
| 3 | B1+B2 Home-full relief destroy | 10 | B1: home-visit `home:full-destroy-await-effect` vs detectors rewrite `tpi:defect:...=>shop:approach` (Alchemist); B2: home-visit await alone, 27 WAITs on one tile | relief for a blocked Home deposit (Home full) |
| 4 | C observed-shelf leave/re-approach | 7 | detectors `tpi:continue-observed-shop` (ESC) <-> store-router `shop:approach` (step off/on) | identify-staff: 4 (Magic Shop, `wanted_purchase` affordable 837-851G, `rejection_reason: preempted`); 1 Stone-to-Mud rebuy (1007-111342); 2 unclear |
| 5 | B4 Home sale target unobserved | 2 | home-errand `stopped:target-unobserved` <-> home-visit `full-queue-surplus-withdraw` | Home-full relief sale |
| - | E stuck:wander (fundraise, gold 305) 2; D town melee/flee 1; X 1 (1008-020115) | 4 | detectors / misc | - |

Root grouping: 51 of 62 involve a full Home (A: Home-full refusal message in 20/25 files; B1-B4: home-full relief rows in all 26 files). This
matches the review's "Home ~45". The review's "Alchemist ~8" is B1 (relief sales routed to the Alchemist), and
"Magic Shop ~9" is C plus B3 rows whose plan pointed at the Magic Shop.

Status on main (commit timeline vs capture times; no build id is logged, see section 5):
- A in-store half fixed by 6d3b124d (10-08 08:28, "equipment transaction owns its Home page") and dbd97536
  (13:45). No A burst after 07:35. The residual is a visible stop instead:
  `equipment-transaction:home-route-repeat-terminal` x17 and `town:blocked:overweight-home-unreachable` x10
  (10-06..10-09), all with "我が家にはもう置く場所がない" from 10-08 13:44 on (e.g. 1008-191943, no sale telemetry).
- B3 reasons removed one by one: ff5ee7ed/728cc6e2 (deposit-retry-unreachable), 40b310a5 (surplus-withdraw),
  3790eb0e 10-08 05:12 (no-sellable -> `_defer_home_full_deposit`). The generic mechanism remains (section 3B).
- B1 fixed by b75db5e9 (10-08 00:06), B2 by db2d2578 (10-08 12:57). No burst of either after.
- C: 1008-0516..0519 appeared minutes after 3790eb0e (merged 05:14) deferred Home; 92b020c1/b99308c0 (06:26) followed.
- Every fix converted the loop into the next stop on the same full Home: B3 deferral -> C (05:16, same state
  gold 13695/pack 11); A fix -> home-route-repeat-terminal; B2 fix -> overweight-home-unreachable (13:42).

## 3. Mechanisms of the top 3 classes

### 3A. Equipment transaction vs full Home (25)
Evidence 1007-044510 (last session s8-s32) and 1007-033045 (s12-s20):
- s9 `eq:deposit-home-full` -> `_mark_equipment_home_full_unavailable` (policy_equipment.py:2168-2185, 1983-1988)
  adds Home to `blocked_stores` and sets latch site `equipment-transaction-home-full`.
- s10 a NEW session (`equipment-session:10`) composes the same deposit at the entrance
  (`eq:atomic-deposit`, key `dr`), refused again; s12-s17 `await-confirmation` x6, s18
  `confirmation-stall-bound` (budget 8, `transaction_last_failure`).
- s20-s31 the re-planned 1-action session walks onto the Home entrance (`approach-home`, keys 9/1/4), the Home
  page opens, no equipment offer is made on that page (town_work shows only `_low_hp_walk_gate`), the idle
  fallback posts ESC (`policy:none-store-exit`, policy.py:9242-9250); repeat until 3 retirements.
- Why progress is never credited: the deposit is refused by the game, the store page open/close is not an
  effect (cli.py:448-459 credits only `operation_effect_observed` / done execution receipts), and the route
  minimum to the entrance is 0..1 already, so walking back gives no new minimum (cli.py:480-489).
- Why closing does not hold (code-proven CAN, not observed DID; the rows do not log the latch):
  `_equipment_home_full_refused_this_visit` (policy_equipment.py:1972-1981) requires BOTH Home in
  `blocked_stores` AND latch site == home-full. Any `_rearm_town_store_for_new_work(HOME,
  release_visit_bound=True)` (policy_shop.py:1570-1597, discard at :1593) erases the first; any later
  `_set_town_store_attempted(HOME, other site)` (policy_shop.py:1824-1838) overwrites the second. Callers with
  release_visit_bound=True include the departure counterfactual (policy_town.py:3602-3611), atomic-withdraw
  failure (policy.py:7547/7594), weight-overload re-arm (policy_town.py:3397-3402), policy_home.py:610/772.
  The counterfactual skips equipment needs only when `equipment_exhausted` or the arbiter `_retired` set holds
  equipment-opt/txn (policy_town.py:3696-3716); log-only mode calls `forgive_retirement`
  (cli.py:568-569 -> town_arbiter.py:364-378) which clears `_retired`, so after every forgiven retirement the
  departure gate may re-arm Home for the same equipment work.
- Residual on main: after the in-store fix the same state ends in `home-route-repeat-terminal`
  (policy_equipment.py:1643-1663 sets it when an identical target_loadout_id is abandoned twice with an
  identical board; :1814-1820/:1837-1843 make it a final stop, policy_constants.py:293-298). 1008-191943 s10-s15:
  `home-route-unavailable` -> `abandon-blocked` -> re-plan -> `abandon-blocked` -> terminal stop.
  User decisions 10-03 21:4x and 10-09 01:4x say: swap fails on a full Home -> depart with the current
  equipment + record. 5029380e (stop re-planning after any failure) did exactly this but was reverted by
  44087efb: it blocked other owners' Home withdrawals and "did not stop the cycle live (17:58)".
- Design (#1) rows: "Equipment transaction" (impossible causes include confirmation-stall-bound; N=8 per
  operation; "Home moves use corresponding rows") and "Home deposits" (impossible: home-full, deposit-refused;
  N=8). Generic rule: impossible closes immediately, tombstone for the visit, never re-acquire. CONFLICT: the
  design says "Source NeedSpec departure-blocking status remains authoritative" and equipment-transaction is
  departure_blocking=True, which turns this closure into a mandatory stop; the user decision makes it a
  confirmed-current-loadout departure. The design must encode the user decision explicitly.

### 3B. Typed town block expressed as a repeated WAIT (14)
Evidence 1008-031646 s6-s16: `home:full-skip:identified-item-protected` (relief has no legal candidate), then
`town:blocked:home-full-no-sellable-surplus` key `5` nine times; arbiter retires town-plan at s10/s13/s16
(budget 3), log-only forgives twice, burst on the third. No other producer participates, so it is not an
alternation; it is a terminal declared as a WAIT task.
- `_town_blocked_key` (policy_town.py:5294-5303): "Other blocked reasons remain visible terminal waits."
  Only reasons listed in POLICY_FINAL_STOP_REASONS (policy_constants.py:304-327) stop; `home-full-*` and
  `no-actionable-claim-owner` (policy_town.py:1495-1501) are not listed, so they become WAIT forever and only
  the owner-retired watcher stops them.
- Design rows: "Plan routing / blocked" (terminal proof closes immediately; N=3 for unresolved routing) and
  "Home-full relief" (remedies: sell surplus -> destroy cheapest unneeded -> else skip optional deposit;
  mandatory deposit with no safe remedy stops visibly). Also: "Terminal/impossible declarations are resolved
  immediately, never represented as another repeatable WAIT task."
- On main the three home-full causes were replaced by skips/deferrals (commits above); no-actionable-claim-owner
  and `retired-equipment-transaction-failed` (policy_town.py:1495-1501) still use the WAIT path.

### 3C. Home-full relief destroy (B1 5 + B2 5)
- B2 1008-123805 s156-s237: relief picked `home-full-destroy:('鑑定の杖 (17回分)',55,5)` and emitted
  `home:full-destroy-await-effect` WAIT 27 times on one tile; no destroy command in the captured session (no game
  message, pack 13 constant). Fixed on main by db2d2578 ("await only posted Home-full destroys").
- B1 1007-220810 s7788-s7796: detectors rewrite the relief await into Alchemist approach
  (`tpi:defect:home:full-destroy-await-effect=>home:full-destroy-await-effect`, keys 1/3), home-visit then
  leaves (`home:full-leave-with-surplus`); progress never credited. Fixed by b75db5e9.
- Design row "Home-full relief": N=3 for stalled orchestration; credit only a confirmed shelf take + sale/
  destruction; exhausted/protected candidates not requeued; an unresolved posted effect gets bounded settlement.

## 4. Minimal fix proposals (one per class, in this order)

### 4A. Equipment work closed by an observed full-Home refusal (first; 25 bursts + 17 repeat-terminal stops)
- Where: policy_equipment.py (`_mark_equipment_home_full_unavailable` :1983, `_equipment_home_full_refused_this_visit`
  :1972, route-abandonment seam :1643-1663, terminals :1814-1820/:1837-1843); policy_town.py
  `_departure_supplier_core` :3696-3716 and departure readiness for categories equipment-work /
  equipment-transaction; policy_home.py `_atomic_home_deposit_dispatch_key` :2986.
- What: on an observed refusal with the Home-full message (or `_home_is_full`), record a visit-ledger
  tombstone `(visit, "equipment", target_loadout_id)` that is NOT kept in `blocked_stores` or the Home latch,
  so `_rearm_town_store_for_new_work(release_visit_bound=True)` and `forgive_retirement` cannot clear it
  (clear only on a new town visit, or on an observed Home `stock_num` below capacity = external cause).
  While set: the optimizer may not open a Home-context session for that target; both equipment NeedSpecs
  report "closed: current loadout confirmed" to departure readiness and to the supplier counterfactual
  (instead of the `_retired` check); write one visible record
  `town:work-closed:impossible:equipment-transaction:home-full`; no `home-route-repeat-terminal` stop for it.
  Scope it to equipment work only; other Home owners keep Home (why 5029380e was reverted).
- Pins: (1) 1008-191943 last session s10-s15 (no sale reason or sale telemetry in its rows, but it ran after
  the 17:47 sale merges; 1008-134416 is the same stop, with the Home-full message, from before any sale merge): today ends in
  `equipment-transaction:home-route-repeat-terminal` at s15; after the fix no second equipment Home session
  is opened and no equipment final stop is raised. (2) 1007-044510 s9-s10: after `eq:deposit-home-full` the
  next decision must not be `eq:atomic-deposit` / `approach-home` (probably already passes on main because of
  6d3b124d/dbd97536; keep as regression pin). (3) unit pin: tombstone set, then
  `_rearm_town_store_for_new_work(HOME, release_visit_bound=True)` and `arbiter.forgive_retirement()` ->
  equipment still closed. Fail-before/pass-after: run on 0de5658d (expect 1 and 3 to fail), apply, rerun,
  then revert only the tombstone check (expect failure again).
- Re-loop risk: closing equipment frees the departure gate, which then picks the next failing gate. In
  1008-191943 that is identify-staff (6 charges missing, Magic Shop skip-latched, gold 4597): expect the stop to
  move to identify-staff (stockout mining per 10-05) or to class C. The overweight stops (10) are the same full
  Home with a mandatory weight-overload deposit and are NOT solved by this (luna task overweight-homefull-1008).

### 4B. No typed `town:blocked:*` reason may be a repeatable WAIT (14 bursts)
- Where: policy_town.py `_town_blocked_key` :5294-5303 and the liveness block :1495-1520;
  policy_constants.py POLICY_FINAL_STOP_REASONS :304-327.
- What: enumerate every value `_town_blocked_reason` can take (set in policy_town.py, policy_home.py,
  policy.py:13672). For each: optional work (NeedSpec departure_blocking=False) -> close + tombstone the WORK
  for the visit (not the store) and return None so the plan advances; mandatory -> add to
  POLICY_FINAL_STOP_REASONS so the first emission is the visible stop (design: terminal proof closes
  immediately). Add a lint test: every emitted `town:blocked:` reason is either a final stop or in an explicit
  skip table.
- Pins: 1007-184438 and 1007-224534 (`no-actionable-claim-owner`, still a WAIT on main): after the fix the
  first such row is a final stop (or a skip, per the table), not the 9th WAIT. 1008-031646 and 1007-130228 are
  regression pins for the home-full causes already converted.
- Re-loop risk: the skip branch is exactly what produced class C at 05:16 after 3790eb0e (Home deferred ->
  router went to the Magic Shop and looped on the same state). Skips must not be re-armed (tombstone the work
  identity and make `_rearm_town_store_for_new_work` respect it); mandatory ones must stop, not skip.

### 4C. Home-full relief await bound (10 bursts, already fixed per scene)
- Where: policy_home.py `_home_full_relief_key` :357 ff. (destroy/await branch near :520-540) and the detector
  rewrite in policy_town.py `_town_procurement_decision` :1293 ff.
- What: give the relief orchestration its design bound (3 own decisions with no confirmed take/sale/destroy ->
  close `impossible:destroy-unconfirmed`, add the candidate to `skipped`, never requeue) and refuse a detector
  rewrite of the relief's own await (design: a detector continues the same admitted work or closes it visibly).
- Pins: 1008-123805 s156-s237 and 1007-220810 s7788-s7796; both should already pass on main (db2d2578,
  b75db5e9): use as regression pins; reverting each commit must make them fail.
- Re-loop risk: closing relief leaves the deposit unserved -> 4B (`no-sellable`), 4A, or the overweight stop.
  Order of work: 4A, then 4B; 4C only if a new relief burst appears.

Next by count (not top 3): C, identify-staff wanted and affordable but `preempted` (4 bursts). On main
`town-progress-invariant:continue-observed-shop` (policy_town.py:1405-1415) still forces the leave and relies on
the outside one-shot composition; pin 1008-051620 s10-s22.

## 5. Data NOT available (the design must not rely on it)
1. Which build produced a capture: no commit/version in decision rows, stdout or stderr logs. "Status on main"
   is inferred from main merge times vs capture times (assumes the live bot runs the main checkout and a
   restart picks up new code).
2. Who re-armed a store: `_rearm_town_store_for_new_work` calls, `blocked_stores`, `_town_store_attempted` and the
   Home latch are not logged per row (`home_latch` only in shop-selector diagnostic rows, e.g. 1007-044510 s5).
   The re-arm path in 3A is code-proven possible, not observed.
3. Effect receipts: `store_visit.operation_effect_observed` is false in every row of all 62 captures; the
   execution `no_steps` receipts (cli.py:455-458) and `_owner_retired_no_progress_count` are not logged.
   Progress must be rebuilt from the state log (pack/equipment/gold deltas, store pages).
4. The failing departure gate: no row field lists the departure-blocking NeedSpecs currently unsatisfied.
   "Mandatory need" above is inferred from reasons, town_work producers and `procurement_requirements`
   (supply shortages only; no equipment/Home needs).
5. Home occupancy: only `store.stock_num` on boards where the Home page is open (state log, 240 = full). The
   state log has fewer rows than the decision log (1007-044510: 74 vs 125); no capacity field outside.
6. owner-retired-log-only.jsonl has time/turn but no decision_sequence; joining to rows is by turn only.
7. Captures are tails of the last session after a restart (17-25 rows for repeated restarts); the decision
   that first armed the loop is often in an earlier session that the restart wiped (R3 itself).
8. Keys without a town_work record cannot be traced to a producer (c3788570 not on main).
