# Step 1.5d: required Identify staff not bought (analysis)

Scope: read-only, PLAN-town-stability-20261009.md step 1.5d. Source: main 426eb6ea (C:\hengband\bot-client).
Data: jsonlog\autorecover.jsonl (338 captured stops since 10-02) and the LAST session of each capture
(`bot-decisions` + `bot-state-fixed`). Scripts were ad hoc in the scratchpad; no repo file other than this one touched.
Requirement (owner decisions): from 10F, 20 carried charges (Home not counted); at most 4 staves, swap the
emptiest for a fuller shelf staff; if unobtainable, mining time-pass (3 tries, then visible stop); Black Market
optional buys keep a full resupply reserve.

Two field meanings matter before reading any capture:
- `shop_selector.rejection_reason: "preempted"` is a catch-all, not "preempted by owner X": it is written whenever
  a wanted item exists on the current OR the cached page (`_shop_observation`) and this decision's key is not a buy
  (policy_shop.py:2373-2427). Walking, saving, Home trips all log "preempted".
- `"no-store-page-observed"` only means the cached page was dropped (policy_shop.py:2401-2402; dropped by the
  stop settlement at policy_observation.py:1234). It is a consequence, not a cause.

## 1. Stops (since 10-02) where identify-staff readiness failed in town

Charges = carried/20 (staves carried). Shelf = observed Magic Shop (store 5) Identify staves in the state log
(price/charges x count). BM = Black Market; it was not observed with a staff in any capture below.

| stamp (capture) | final stop | gold | charges | shelf (afford.) | what the bot did instead (evidence) | class |
| --- | --- | --- | --- | --- | --- | --- |
| 10-03 23:38 (233816) | overweight-home-unreachable | 8,189 | 17 (3) | not visited | plan [Home] only; F=teleport,cure,identify,weight; overweight Home stop owns town | other (STEP1.5 B) |
| 10-05 12:22 (122258) | departure-unsatisfiable | 16,558 | 18 (2) | 558/0, later 823/20 x2, 756/15 x2 (yes) | s15-17 withdrew a 0-charge staff from Home then re-deposited it (Home held "8x 0") ; s21 BOUGHT a 0-charge staff for 558G; s33 stockout mining (mode prepare); s53 restocked shelf 823/20, `wanted_purchase: null`, `plan_shadow_would_skip identify-staff absent:true`; s54 stop | R2, R5, R4 |
| 10-06 21:49 (214921) | owner-retired-burst | 9,312-22,832 | 19 (1) | 829/19, 748/13, 562/13 (yes) | wanted 829/19 x10; composition_refusal `shop:sell-rebuy-churn-defect` x5; IST op `home-first` x5 (Home held a 0-charge wand) | R1, R2 |
| 10-07 02:13 (021335) | departure-unsatisfiable | 15,526 | 6 -> 18 (3 -> 4) | 734/12 x2 (yes) | s8 IST bought one 734/12 (room was 1); at cap 4 with 18<20 the swap (sell a 2-charge, buy the 2nd 734/12) never ran; s16 `town:identify-staff-stockout-mining` with the 734/12 still on the shelf; s18 stop | R3, R6 |
| 10-07 09:33 (093319) | stuck-prompt (progress-invariant) | 10,821-14,398 | 11 (2-3) | 775/15 x4, 748/13 x8 (yes) | wanted 775/15; refusal `shop:home-first-before-purchase` x3 | R2 |
| 10-07 11:13 (111342) | owner-retired-burst | 7,917-10,892 | 5 (2) | 858/21 x2, 720/11 x3 (yes) | IST op `home-first` x7 at Magic; Home held 0-charge staves and a 0-charge wand | R2 |
| 10-07 17:58 (175851) | owner-retired-burst | 8,184-8,808 | 12-14 (3-4) | 715/11 x3 (yes) | wanted 715/11 x14; refusal `shop:home-first-before-purchase` x13; Home held 0-charge staves | R2, R3 |
| 10-07 18:44 (184438) | owner-retired-burst (no-actionable-claim-owner WAITs) | 4,351 -> 20,375 | 11 (3) | not on captured pages; 715/11 seen 2 min later (184633) | s11 Home-full relief withdrew "2x 0" staves (6 carried, cap 4 -> nothing wanted, s14/s21); s16/s23 one-shot sells `d..y\x1b` leave the shop; Magic stop consumed; after s89 (+15,975G sale) plan = [Temple], identify-staff had no claim, s95-117 no-actionable-claim-owner | R3, R1(no re-arm) |
| 10-07 22:45 (224534) | owner-retired-burst | 29,543-30,665 | 3 (2) | 822/19 x2, 742/13 x4 (yes) | s31-35 IST sold a 12-charge Magic Missile wand and a staff, then `in-store-done` without buying; s41 head purchase = MANA-food MM wand 394/40 (IST op `home-first`); s42 outside composition `shop:sell-rebuy-churn-defect` -> `observed_stop_settlement: shop:observed-operation-uncomposable`; s43 Magic removed from plan; s46-91 no-actionable-claim-owner | R1, R2 |
| 10-08 19:19..22:22 (191943 + 10 repeats) | equipment-transaction:home-route-repeat-terminal | 4,597 | 14 (1) | none captured | identify fails behind the equipment Home loop (STEP1.5 class A) | other |
| 10-09 01:44 / 01:47 (014408, 014739) | no-key-exhausted / owner-retired-burst | 9,119-14,355 | 0 (0) | 623/20, 830/20, 777/16 (yes) | IST op `disposal` (pending disposal) and `no_old_path_operation:false`; outside composition refused by `home:full-leave-with-surplus` x6 / `home:full-queue-surplus-withdraw` x7; plan [Home] only | R1 |
| 10-09 04:03 (040322) | no-key-exhausted | 53,792 | 3 (4) | 830/20 x2 (yes) | Home-full relief withdrew a 0-charge staff -> 4 staves -> no purchase room; at Magic s37-43 `observed-page-nothing-wanted`, inscribed the 0-charge staff, `in-store-done`, no sale | R3 |
| 10-09 04:09 (040900) | departure-unsatisfiable | 51,341 | 3 (3-4) | 830/20 x2 (yes) | s23 sold the 0-charge staff (room now 1), s24 `home:scan-leave-store` left at once; s42 IST op `disposal` -> observe-and-leave; s43 composition refused `equipment:sale-complete`; then Home, `stuck:wander` x13, no-actionable-claim-owner x6, s75 departure-unsatisfiable with town_claims [] | R3, R1 |

Resolved in-session (bought, then a different stop): 10-03 20:28 (202849, 748/13 selected x11), 10-03 23:39
(233948, 762/14 selected). Captures 10-02..10-04 with a staff shortfall but no Magic visit in the last session
(e.g. 1004-121956, 54 "preempted" rows while walking) are not listed; their last session never reached a shelf.
Observed Home pages hold 0-charge devices in 7 of 9 checked captures: 0-charge Identify staves (122258, 093319,
111342, 175851, 224534, 040900) or a 0-charge wand (214921, 111342); none in 021335, 014739, 184438. 021335's
Home-first refusal is the stale-Home-knowledge variant (`shop:home-first-yields-to-current-visit`,
policy_shop.py:1868-1884), not a 0-charge match.

## 2. Code path: "required" to "bought" (main 426eb6ea)

1. Requirement: `_identify_staff_ready` policy_supply.py:432-447 (carried charges only, `_total_identify_staff_charges`
   policy.py:13246). Departure conjunct policy_town.py:1896; need registry entry policy_town.py:3312 (departure_blocking=True) with
   suppliers from `add_identify_staff_suppliers` policy_town.py:2525-2579 (Magic, then BM; remembered worthwhile
   offer kept, 628bd90b).
2. Routing/claims: `_town_claims_active` policy_town.py:3347 drops every need whose store is in
   `nonhome_attempted_without_effect` (policy_town.py:3412-3416); the router re-opens an attempted stop only for a
   NEW category (policy_shop.py:1326-1333). With no claim left: departure branch policy_town.py:6183-6246
   (counterfactual :3602-3716, stockout gate policy.py:15017-15085 / policy_town.py:5736-5746) or :6323-6342
   -> `departure-unsatisfiable`; movement fallback -> `no-actionable-claim-owner` WAIT policy_town.py:1495-1520.
3. Selection: `_next_purchase` policy_shop.py:2236 -> `_legacy_next_purchase_unreserved` :2901. ONE item is
   returned, in rung order. Fundraising block :2961-3091 returns None without an identify-staff rung. Identify rung
   :3253-3270 requires `_identify_staff_purchase_room` (:3305-3319, cap 4, policy_constants.py:402) and picks the
   max-charge affordable staff with no `charges > 0` and no `_identify_staff_acquisition_worthwhile` check (typed rung
   :2691 same).
4. In-store (IST, `--in-store-shop-ops`): `_in_store_selection` policy_instore.py:193-283 - pending disposal wins
   (:205-207, no key), then sales, then the single purchase; a Home-first verdict gives op `home-first` with no key
   (:260-266). No key -> `_in_store_try_start` (:372-394) returns None -> `shop:observe-and-leave` (policy.py:10356-10368),
   relabelled `town-progress-invariant:continue-observed-shop` (policy_town.py:1405-1425).
5. Outside composition: `_atomic_shop_transaction_key` policy_shop.py:5521 runs `_shop` once on the saved page.
   Before any buy `_shop` can return a leave for: pending disposal `equipment:sale-complete` (:4192-4206),
   sell-rebuy churn of the HEAD item (:4741-4750; exception only `_identify_staff_swap_purchase` :3892),
   Home-first (:4751-4772), Home-full relief keys. A non-buy result settles the stop
   (:5728-5765 -> `_resolve_observed_uncomposable_stop` policy_observation.py:1139-1240, marks
   `nonhome_attempted_without_effect` :1229-1233, plan cursor advances).
6. Home-first gate: `_purchase_has_fresh_home_absence` policy_shop.py:1840 / `_evaluate_purchase_home_gate` :2080.
   Exception `_is_required_identify_staff_purchase` :2028-2056 applies only with Home-full retry deposits (ec69be10).
   Otherwise `_home_procurement_candidate` policy_home.py:4074-4088 uses `_procurement_class_matches`
   policy_supply.py:1005-1006: for a staff purchase ANY Home wand or staff matches, charges not checked; its
   `_procurement_missing_amount` falls to the default 1 (policy_supply.py:1096) -> HOME_FIRST (policy_shop.py:2196).
7. Cap swap: release plan policy_supply.py:742-790 (sell emptiest when an affordable fuller shelf staff exists),
   sold through the ordinary sale path; the purchase only becomes wanted after that sale on a later decision.

Why each recorded case did not buy: see the "instead" column; mapped to code: 224534 = step 5 churn on the head
(MANA-food wand) + step 2 claim drop; 040900 = step 4/5 disposal + step 7 (home-scan leave after the sale) + step 2;
014408/014739 = step 4/5 (disposal, Home-full relief refusal); 122258 = step 6 (0-charge Home staff), step 3
(0-charge buy, then fundraising block); 021335/175851/093319/111342 = step 6 and step 7; 184438/040322 = step 7
(cap held by 0-charge staves withdrawn by Home-full relief) then step 2.

## 3. Root-cause classes (ranked by stops affected)

| rank | class | stops | status on main |
| --- | --- | --- | --- |
| R1 | Single-headed purchase + settle: a non-buy result on a Magic page (disposal, churn guard on another item, Home-full relief, Home-first on another item) ends the visit; the stop is settled/attempted and the identify-staff need loses its claim (no retry) | 224534, 040900, 014408, 014739, 214921, 184438 | LIVE. The 040900 disposal came from sale code reverted by 0de5658d (10-09 17:32), but main still sets `_pending_disposal_item` (policy.py:14770 dominated launcher, policy_home.py:3943 dominated armour) and keeps the churn guard, the relief keys and the claim drop unchanged |
| R2 | Home-first treats any Home wand/staff (0 charges included) as Identify-staff stock -> HOME_FIRST, a Home round trip, a useless 0-charge withdrawal | 122258, 214921, 021335, 093319, 111342, 175851 (+224534 for its head device) | LIVE (ec69be10 fixed only the Home-full exception path) |
| R3 | Cap-4 swap is not one transaction: 0-charge staves (often withdrawn by Home-full relief to be sold) fill the cap, the staff is unwanted until a sale, and the producer after the sale leaves the shop (one-shot `\x1b`, `home:scan-leave-store`, `in-store-done`) | 184438, 021335, 175851, 040322, 040900 | LIVE |
| R4 | Fundraising/stockout mode suppresses the purchase: selector fundraising block returns None (policy_shop.py:2961-3091) even when a restocked worthwhile staff is on the page | 122258 (s53) | LIVE in code. a0bbfb46 (10-08 15:49) routes to the supplier during fundraising but did not touch the selector; no post-a0bbfb46 capture |
| R5 | Rung buys a 0-charge staff (no charges/worthwhile check) | 122258 (s21, 558G) | LIVE |
| R6 | Stockout predicate declared "impossible" once Magic was attempted | 021335 (and 224534 pre-fix) | FIXED by 628bd90b (10-08 01:39) + 92dc3f5a (06:24); both captures predate them. 224534 is pinned by tests/test_identify_staff_stockout_recorded.py (asserts a live owner only, not the purchase) |

Note: every capture predates 0de5658d; captures before 10-08 01:39 also predate 628bd90b/92dc3f5a/ec69be10.
R1-R5 are visible on main in the cited code; only 040900 post-dates the supplier fixes and it still stopped.

## 4. Minimal fixes (one per class, in this order), pins, fail-before/pass-after

F1 (R2, smallest, removes most bursts). In `_evaluate_purchase_home_gate` / `_purchase_has_fresh_home_absence`
(policy_shop.py:2080, :1840) treat an Identify-staff purchase like policy.py:9002/9105 do for Home staves: Home stock
counts only if `tval==STAFF and sval==IDENTIFY and charges>0 and _identify_staff_acquisition_worthwhile(...)`.
Keep the `is_wand_staff` equivalence for MANA-food devices. Decision basis: carried-only (09-17), swap (10-03).
Pins: 175851 Magic page (715/11, Home only 0-charge staves): today HOME_FIRST / `shop:home-first-before-purchase`,
after: ALLOW_PURCHASE. 122258 s15-17: no 0-charge Home withdrawal. Fail-before on 426eb6ea, pass-after, then revert
only the new predicate and expect failure.

F2 (R1). Make the selector skip, not stop: (a) sell-rebuy churn on item X (policy_shop.py:4741-4750) excludes X for
this visit and continues to the next wanted rung instead of `LEAVE`; (b) `equipment:sale-complete`
(:4196-4206) returns None (continue) when a departure-blocking purchase is wanted on the page; (c) in
`_atomic_shop_transaction_key` (:5728-5765) do not settle the stop as uncomposable while the page still has an
affordable departure-blocking purchase (identify-staff) - compose that buy. Pins: 224534 s41-42 (fixture rows
already in tests/fixtures/identify-staff-stockout-20261007.json.gz): today composition_refusal
`shop:sell-rebuy-churn-defect` + settlement, after: a `p` key for the 822/19 staff (or the device then the staff);
040900 s42-43 with `_pending_disposal_item` set through the main dominated-launcher path: today ESC
`equipment:sale-complete`, after: buy `l`. 014739 s27-28 (relief refusal) as a third pin.

F3 (R3). Keep the swap inside one store entry: while an IST entry at Magic has a release sale done and a worthwhile
staff on the page, `_in_store_entry_key` continues to the buy, and `_home_full_knowledge_key(leave_foreign_store)`
(policy_home.py:793-806) may not leave an open ordinary-store entry that still has a departure-blocking operation.
Also: Home-full relief must not withdraw an Identify staff when that raises carried staves to the cap while
identify is not ready (sell/destroy it from Home relief instead, per 10-04 home-full decision). Pins: 040900 s24
(3 staves, shelf 830/20 x2, gold 53,565): today `home:scan-leave-store`, after: `p` buy; 040322 s37-43: today
nothing wanted at 4 staves, after: sell the 0-charge staff then buy in the same entry; 184438 s11 (relief withdraw
of "2x 0" while identify not ready): after, not queued.

F4 (R4+R5). In the fundraising block (policy_shop.py:2961-3091) return the identify-staff rung item when
`_fundraising_identify_staff_only_block` or the identify mining plan is active; add `charges>0` and
`_identify_staff_acquisition_worthwhile` to the rung (:3253-3270) and the typed rung (:2691). Pins: 122258 s53
(fundraising prepare, shelf 823/20): today `wanted_purchase: null`, after: 823/20 wanted; 122258 s19-21: today buys
the 0-charge 558G staff, after: nothing wanted.

Re-loop risks:
- F2(a) removes a churn stop; cap the skip per (store, item signature) per visit so the same sell->rebuy pair cannot
  alternate (sale side stays guarded by the existing reserve, 31b024a3/b3fbdcbe).
- F1 makes the Magic buy happen while 0-charge staves stay at Home: Home stays full (STEP1.5 class A/B). Not worse,
  but expect the next stop to be the Home-full equipment/overweight one.
- F3 relief change could leave the Home full longer; the 10-04 decision allows destroying the cheapest unneeded
  item, which covers 0-charge staves.
- Swap churn: the cap release must sell only staves emptier than the shelf offer (already in
  `_identify_staff_release_plan`), and the 4-staff cap must still hold after the buy.
- Black Market: identify staff is in the reserve set (policy_fundraising/policy_shop reserve at policy_shop.py:2412-2425);
  F2/F4 must not let a BM optional buy spend the staff's reserve (10-08 decision). No capture shows BM involvement.
- Stockout mining (10-05 decision) must still trigger when no shelf has a worthwhile staff; F4 must not mark the
  mining plan satisfied by a 0-charge purchase.

## 5. Data not available
1. Which build ran each capture (no commit in rows); "status on main" is by merge time vs capture time.
2. `nonhome_attempted_without_effect`, `_town_store_attempted`, `satisfied_needs` are not logged: for 040900 s75
   the branch that dropped the identify-staff claim (claim filter vs counterfactual) cannot be named, only that
   `town_claims` was [] and no shelf-evidence skip was recorded at that decision.
3. 021335: why the stockout predicate returned True with a worthwhile 734/12 on the remembered page is not
   determinable (supplier-stock dict and Home-knowledge flag are not logged); the predicate tail changed in 628bd90b.
4. Home catalogue contents are visible only on Home pages present in the state log (page 1); devices on other pages
   are unknown. 184438 has no Magic page in its state log.
5. Captures keep only the last session; the decision that first queued a 0-charge withdrawal is often earlier.
6. IST notes (`shadow`, `start`) are logged; why an IST entry ended (`in-store-done`) is not (224534 s35, 040322 s38).
