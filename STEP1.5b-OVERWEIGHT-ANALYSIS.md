# Step 1.5b analysis: `town:blocked:overweight-home-unreachable` (overweight with a full Home)

Scope: read-only. Repo C:\hengband\bot-client main 426eb6ea (code refs are on 426eb6ea). Evidence:
jsonlog\autorecover.jsonl + jsonlog\autorecover-*overweight* captures (decisions/state gz). Weight is in 0.1 lb,
computed from the state rows as the bot does (`_inventory_weight` policy_helpers.py:290, limit
`ADJ_STR_WEIGHT_LIMIT[str.index]*50` policy_home.py:1773-1782). Home stock = `store.stock_num` of the last Home
page (capacity 240 where logged); Home contents from the last `~9` knowledge row. Scratch scripts only.

## 1. Every overweight stop since 10-02 (17 = 14 restarts + 3 escalations; one more on 10-01 22:24, pre-window)

| capture (autorecover-…) | Home | weight/limit | tried to deposit | remedies seen | why it stopped |
| --- | --- | --- | --- | --- | --- |
| 20261002-001021 | 73 | 1752/1750 (+2) | nothing composed: Home page -> `home:route-claim-unfulfilled` ESC (s12336, s12366) | none | s12367 stop after 2nd empty Home pass |
| 20261002-010548 | 80 | 1749/1750 at last row* | same (s5371) | `town:destroy-overflow` (pack slot, s5372) | s5373 |
| 20261002-015704 | 87 | 1753/1750 (+3) | same (s8609, s8619) | none | s8620 |
| 20261002-042555 | 89 | 1757/1750 (+7) | same (s8858, s8873) | none | s8874 |
| 20261002-055645 | 96 | 1751/1750 (+1) | same (s1371, s1386) | none | s1387 |
| 20261003-233816 | 240 | 1959/1800 (+159) | `dn28\rdk` = 28 arrows + 理力の首切りソード (s22674), refused x2 | none existed (relief came 10-04 05:57, 329a6b92) | s22682 |
| 20261003-233948 | 240 | 2019/1800 (+219) | `dn28\rdk` s3, `dk` s42, `dm` s54: 4 refusals | none; bought recall + Identify staff 762G meanwhile | s62 |
| 20261008-090841 | 240 | 1909/1900 (+9) | none at s692 (`policy:none-store-exit`); weight-deposit candidates skipped as `item-reserved:weight-deposit:home-full-retry` | earlier relief destroys (s656 7 recall scrolls, s658 Identify staff 16ch); swap put axe in Home; then bought Identify staff 18ch 810G (s689) -> over | s693 |
| 20261008-134200 | 240 | 1999/1950 (+49) | s10420 `home:weight-overload-deposit` key `5`, nothing posted (home-full-retry reservation) | relief skips `identified-item-protected` s10413, `identification-source-unavailable` s10414-15; carried destroys of Identify staffs 5ch/6ch s10439/s10441 -> 1949/1950 (cleared!); s10444 buys staff 13ch 735G (need 14/20) -> 1999 | s10448 after Home `none-store-exit` s10447 |
| 20261008-134643 | 240 | 1979/1950 (+29) | (session start 13:44:21) | s6 destroys staff 13ch (1999->1949, cleared); s19 equipment deposit refused (`deposit-home-full`); s28 buys 6 treasure-detection for stock-out mining -> 1979 | s32 after Home `none-store-exit` s31 |
| 134816(esc), 135145, 135307, 135441(esc), 175125, 175248, 175411(esc) (all 20261008) | 240 | 1979/1950 (+29), gold 4597, identical | s2 posts `dodi6\rda16\r` = Dwarf pickaxe(200) + 6 treasure-detection + 16 speed potions into the 240/240 page: 3 refusals, `await-confirmation` x4 | no relief row; s12 `equipment-transaction:deposit-home-full` | s15 Home `none-store-exit`, s16 stop (17-row sessions from process start) |

\* 010548: the last state row is 1749/1750 after the s5372 destroy; the stop reason was set on the previous decision
(CrossDecisionLatch `_town_blocked_reason`, policy.py:2176-2190) — inferred, the setter is not logged.
Home contents 10-08 (090841 and 175411 `~9`, identical): 240 rows = 231 equipment (160 ego, 27-28 artifacts, 39 not
fully known) + 4 stacks of speed potions (99+99+99+98) + 5 restore-potion rows. Still 240/240 (230 equipment) at the
last capture 20261009-040900. The same character state (gold 4597-4717, 1979-1999/1950) also ends the equipment
captures 20261008-134416 and 191943…222632 (11 `home-route-repeat-terminal`), which start with the same refused
`home:weight-overload-deposit` at s1-s3.

## 2. Code path from "overweight" to the stop
- Need: `_inventory_overweight` (policy_home.py:1784) and `_find_home_deposit` != None (policy_home.py:3419; the
  overload candidate `_overweight_home_deposit` :1962 from `_weight_deposit_candidates` :1856-1960, filtered by
  `item_available(..., "weight-deposit")` :1959) add `weight-overload` at Home (policy_town.py:2728-2734).
- Gate: registry `("weight-overload", "home-first", 1, True)` (policy_town.py:3272) = departure-blocking. 09-03
  decision 5 kept it in the departure conjunction ("残す").
- Stop A (claims pass, `_town_claims_active` policy_town.py:3347): when Home is blocked "under the applicable
  bound" (:4169-4176; a block with no recorded limit applies to all Home work) or approach fails >= limit, the
  weight-overload need sets `_town_blocked_reason = "overweight-home-unreachable"` (:3438-3455). A re-arm for a new
  overload signature exists (:3376-3402, signature stored at :4120-4127).
- Stop B (liveness, :1456-1520, set at :1511): stuck:wander/novel with a weight-overload claim, Home attempted or
  `_overweight_home_bound_exhausted` (:4156-4167). 10-02 class used B (OVERWEIGHT-HOME-REPORT.md); 10-08 used A
  (row field `home_route_projection.home_blocked=true`, `home_unsatisfied_passes` 3-4 >= limit 3).
- Emission: `_town_blocked_key` (:5294) -> final stop (policy_constants.py:315; cli.py:601 banner).
- What blocks Home in the 10-08 scenes:
  - `_mark_equipment_home_full_unavailable` (policy_equipment.py:1983-1988) adds Home to `blocked_stores` with no
    `blocked_store_limits` entry -> authority None -> blocks the overload too (8 of 10: 134643 s19, 7x s12).
  - `_defer_home_full_deposit` (policy_home.py:73-96; called at :738-742 when relief has no legal candidate) parks
    the batch in `_home_full_retry_deposits`, blocks Home (limit 1), advances the plan. The retry then returns None
    while Home is blocked (:364-369) and its reservation denies the `weight-deposit` sink (item_reservation.py:252-260
    exempts only sink `deposit`) — 090841 s692-693, 134200 s10419-10421.
- Remedies that exist for an overload when Home is full:
  - Home-full relief (policy_home.py:357-770): begun on refusal/observed full (policy.py:7598-7605, 7670-7680;
    policy_home.py:3229-3234). It sells or destroys Home stock to free a slot, then deposits. Equipment on the shelf
    is eligible only if it is a burnt-out torch, a spare lantern or dominated armour (`_home_full_equipment_surplus`
    :172-185, used by sale :132 and destroy). With the 10-08 Home (231 equipment rows, speed potions protected as
    a purchase rung `speed`, see the BM buy below) it finds no legal candidate -> defer -> stop.
  - Carried fallback: when no shelf candidate exists, relief destroys a carried stack with retention 0 even though
    the pack is not full (:686-713, `pack_only` :750-760; pack_only never decrements `remaining`, so it frees no
    Home slot). Observed: Identify staffs 5/6/13ch destroyed, then rebought by the 20-charge gate.
  - Selling or destroying the carried overload itself: no code path; no owner decision orders it.
- Decisions: 09-03 #2 deposit the surplus at Home; #4 no purchase-side guard; #5 a deposit that really fails is a
  stop. 10-04: full Home -> sell Home surplus, else destroy the cheapest unneeded Home item (autodestroy kinds
  first), then deposit; Home equipment that is a loadout candidate is protected. 10-01: ammo surplus may be
  deposited. 09-17: departure counts carried items only. 09-18: diggers go Home on normal dives (lowest
  priority); cursed items are destroyed. 10-08 J-D sale + top-10/20 rule (the only rule that frees equipment
  shelf slots) was reverted 10-09 12:4x; instead the sale candidates are to be sold once by hand.

## 3. Root-cause classes (ranked by stops, then by what they unblock)
1. Home-space impossibility (10/10 on 10-08; also the 2 on 10-03 before relief existed). Home is 240/240 with
   230-231 protected equipment rows; relief has no legal sale/destroy, and no decision allows removing the carried
   overload another way. Decision gap, not a code bug: once the sale was reverted, every overload on that Home
   ends in a stop (09-03 #5).
2. The equipment refusal's Home block covers the overload (8/10). It sets when the stop fires, and it skips
   whatever relief could still do that visit (luna, uncommitted, C:\hengband\bot-client-overweight-homefull-1008).
3. Relief churn that recreates the overload (134200, 134643): the carried `pack_only` destroy drops Identify staves
   below the 20-charge gate (`procurement_requirements` current 14/target 20 at s10444), the gate rebuys (735G x2)
   and the overload returns. The staves' 0 retention likely comes from `_identify_staff_release_plan`
   (policy_home.py:1533-1544); that is CAN, the rows do not log it.
4. A mandatory deposit gets deferred like an optional one (090841, 134200): `_defer_home_full_deposit` plus the
   home-full-retry reservation keep the departure-blocking overload unserved for the rest of the visit.
5. After a restart the overload is posted into a page that already shows 240/240, before relief (7 sessions,
   s2). It costs one Home pass and 4 await decisions per restart. Cause not proven (the capacity observation may
   be recorded after composition).
6. Purchases after the Home pass push the weight back over the limit: Identify staff 810G/735G, 6 speed potions
   for 7902G at the Black Market (134200 s10435, category `speed`) while Home holds 395, treasure detection x6.
   Allowed by 09-03 #4; harmful only because of 1-4.
7. 10-02 class (5 stops, Home not full): the cross-area hold kept the arrived Reach claim as holder, so the
   deposit never composed. Fixed 10-02 by 2b50c90c/81e314e8/bd7f1856 (OVERWEIGHT-HOME-REPORT.md); no recurrence.

## 4. Minimal fix proposal
Within existing decisions (no owner question needed):
- F1 Mandatory overload vs full Home (classes 2, 4, 5). (a) In `_open_home_deposit_key`, when the open page shows
  stock_num >= capacity, start relief before composing any weight-overload deposit. (b) `_defer_home_full_deposit`
  never defers a departure-blocking (weight-overload) batch. If relief has no legal candidate, close at first
  proof with a named final stop, e.g. `town:blocked:overweight-home-full-no-legal-relief`, logging the candidate
  stacks and the skip reasons (09-03 #5, 10-04; design #1 "mandatory deposit with no safe remedy stops
  visibly"). (c) An equipment-origin Home block (`_mark_equipment_home_full_unavailable`) does not apply to
  weight-overload work: record a limit/owner for it, so `_town_store_blocked_under_applicable_bound` returns False
  for this need.
  Effect: the same 10 scenes still stop, but at the first Home page, before 735G rebuys and Black Market buys,
  and with the true cause. It does not reduce the stop count by itself.
- F2 Relief carried-discard defect (class 3). Use carried stacks only when the pack is full (as the comment at
  :686 says). Never destroy a carried stack whose removal, on the probe inventory, reopens a departure-blocking
  shortage (Identify staff charges < 20, etc.).
Needs an owner decision (question for the owner):
- F3 "When Home is 240/240 and the 10-04 rules find no Home item to sell or destroy, may the bot resolve the
  weight overload by selling the carried overload surplus itself at a shop (the stacks it would have deposited,
  e.g. 16 speed potions while Home holds 395, a spare Dwarf pickaxe, 6 treasure-detection scrolls; destroying
  them only if no shop buys them), instead of the visible stop that 09-03 #5 orders now?" Option 2: keep the stop
  until the equipment sale returns (plan step 5) or the one-time manual sale (10-09) frees slots. In 175411, the
  excess is +29; selling the 16 speed potions (64) alone clears it.
Pins (base 426eb6ea plus step 1.5a if it merged first; say which):
- P1 175411 last session (17 rows, starts at process start, so no constructed policy state): today s2 posts
  `dodi6\rda16\r\x1b` into 240/240 and s16 stops. After F1: no deposit into the full page and relief starts at
  s2. With no legal candidate it gives the named stop before any equipment detour (the reason and index change).
  After F3: a shop sale of the surplus, then weight <= 1950 and no stop. Responses after the first changed command
  are constructed (declare them). The other six identical sessions (134816…175248) only repeat this pin.
- P2 134816 s12-s16: after `equipment-transaction:deposit-home-full`, Home is not blocked for weight-overload
  (F1c). It fails today, because `home_blocked` becomes true at s11-12.
- P3 090841 s691-693 (mid-session; the retry batch and Home block are constructed, declare them): no deferral of
  the overload. `item_reservation_shadow` must not show `weight-deposit:home-full-retry`.
- P4 134200 s10439/s10441 and 134643 s6 (relief state constructed): today `01kk`/`01kj` destroy Identify staves
  with the pack at 16-18/23; after F2 there is no carried destroy and no s10444 staff purchase.
- Regression: tests/test_overweight_home_hold_recorded.py (10-02 class), 233816 refusal -> relief begins,
  tests.test_home_full_relief_recorded, test_home_full_destroy_posted_confirm.
- Fail-before on the base; pass-after; revert each of F1a/F1b/F1c/F2 alone and its pin fails again.

## 5. Interactions
- Step 1.5a (SOL-DESIGN-step1.5a-equipment-homefull.md): its pins 134416/191943 expect the overweight stop next,
  and they are the same scene as P1. Land 1.5a first, then rerun P1/P2 on top, and add 134416/191943 tails as
  overweight pins. The design keeps the tombstone out of `blocked_stores`. It does not say that
  `_mark_equipment_home_full_unavailable` stops adding Home to `blocked_stores`; if that call stays, F1c is still
  needed. Closing the equipment session also lifts the relief's yield to `_equipment_transaction_owned_items`
  (policy_home.py:362). Expect the departure gate to show the overload, then identify-staff stock-out mining
  (10-05).
- Luna's uncommitted handoff (overweight-homefull-1008, policy_equipment.py diff) starts relief from the equipment
  refusal and calls `_rearm_town_store_for_new_work(HOME, release_visit_bound=True)`. 1.5a lists that same re-arm
  as one of the things that undo equipment closure, and it already moved an asserted index in
  tests.test_town_approach_retired_recorded. Do not merge it; F1c after 1.5a replaces it.
- Reverted sale: it was the only legal way to free equipment shelf slots. Without it, class 1 makes every
  full-Home overload a stop (F1 only names it earlier). The 10-09 one-time manual sale, if done, frees slots
  (P1 needs 1-3). If the sale returns, it must not destroy or sell supplies the departure gate rebuys
  (the F2 rule).

## 6. Data not available
1. Relief internals per row (`_home_full_relief`, its skip reasons, `_home_full_retry_deposits`,
   `_home_rejected_deposits`, `blocked_stores`/`blocked_store_limits`). Inferred from reasons,
   `item_reservation_shadow` and `home_route_projection`.
2. Which stop site (:1511 or :3454) fired. Inferred from home_blocked/passes.
3. Why the Identify staves had 0 retention (release plan vs other). Why the 7 restart sessions show no relief row
   after the refusal (yield to the equipment session vs no candidate).
4. Build per capture (inferred from merge times). The 10-02/10-03 code is no longer on main and cannot be
   replayed.
5. Home state after 10-09 04:09, and whether the 10-09 manual sale was done. How many slots J-D would free
   (SOL-TASK-A numbers not in captures).
6. Weights of shop wares (0 outside Home, overweight-handling-policy), so the weight a purchase adds is known only
   after the buy.
