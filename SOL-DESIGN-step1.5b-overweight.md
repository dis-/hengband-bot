# Step 1.5b: weight overload with a full Home

Plan of record: C:\hengband\PLAN-town-stability-20261009.md 手順1.5. Base: main after step 1.5a
(equipment Home-full tombstone) lands; analysis C:\hengband\STEP1.5b-OVERWEIGHT-ANALYSIS.md.
Design only (review → implementation after 1.5a merges).

## Owner decisions (verbatim)
- 2026-09-03 (overweight-handling-policy): 1「まず、重量を原因に要求物資を緩和してはならない」 2「重量超過した場合の対処
  について。まず要求物資の過剰分を自宅に預け入れる。」 3「需要の再武装は許可する。ループしないよう留意すること。」
  4「購入側ではガードしない。必要物資は購入しなければならない。」 5「本当に預け入れに失敗するならそれは停止するべき事案で
  ある。町中で自宅への接近が不可能になるのは正常ではない。」
- 2026-10-04 (home-full-sell-surplus): Home full → sell surplus; if nothing sellable, destroy the
  auto-destroy targets → the cheapest unneeded item.
- 2026-10-10: answer 「1 ただし好ましくない状況ではあるので記録はして」 to the question about overload surplus
  when Home is full and relief cannot free space; option 1 text: 「自宅が満杯で、満杯の対処でも空けられない時に限り、
  手持ちの要求物資の余り（必要数を超えた分）を店で売って重量を下げます。どの店も買わない時だけ壊します。必要数は減らしません。」
  This overrides 09-03 #5 only in that scene; #1 and #4 stay.

## Evidence (analysis sections 1-3)
17 overweight stops since 10-02; the 10 of 10-08 all had Home 240/240 filled with protected items
(160 ego, 28 artifacts) and relief had no legal candidate. Two defects within existing decisions:
the equipment-origin Home block also blocks the weight-overload deposit (8 of 10 triggers), and relief
destroys carried stacks while the pack is not full (Identify staves destroyed, then rebought at 735 G,
re-creating the overload).

## Design (revision 2, after the fable review)
F1 Mandatory overload vs full Home (within existing decisions)
 a. `_open_home_deposit_key` (policy_home.py ~3231): read the OPEN page's `snapshot.store.stock_num` and
    `capacity` directly (not only `_home_is_full`); at stock_num >= capacity start relief before composing a
    weight-overload deposit (175411 s2 already shows 240/240 when it posts `dodi6da16`).
 b. `_defer_home_full_deposit` (policy_home.py ~73-94; only caller ~739-742) never defers a
    departure-blocking weight-overload batch.
 c. An equipment-origin Home block (`_mark_equipment_home_full_unavailable` policy_equipment.py ~1983-1988;
    and step 1.5a's tombstone) never applies to weight-overload work. Enumerate ALL direct reads of
    `STORE_HOME in blocked_stores` (review list: policy_home.py:366/407/1416, policy_shop.py:2118,
    policy_town.py:131/4613/5688, policy.py:3100/13506/14123/15023, policy_equipment.py:1980/3181/3191)
    and route them through ONE need-aware entrance (10-04 decision: one entrance, not per-site patches);
    :366/:407 must not drop the overload retry.
F2 Relief carried-discard defect: policy_home.py ~695-696 mixes carried stock in while the pack is not full and
   ~720-726 falls back to a carried destroy; use carried stacks only when the pack is full, and never destroy a
   carried stack whose removal reopens a departure-blocking shortage (Identify staff charges < 20 etc.).
F3 (10-10 decision) New producer `_overweight_surplus_sale_key` — NOT piggy-backed on relief (relief rejects
   stacks with retention > 0: `_home_full_sale_candidate` ~121, sale branch ~567-571, carried_stock ~692) and
   not `organization-sale` (whole-stack surplus only, ~4591; excludes visited stores ~4639). Register claim
   owner, family, need, item sink (item_reservation.py sink set ~283, item_sink_lint), ladder rung if called
   from `_decide`, and the manifest.
   - Trigger: Home full (open page or observation) AND relief has no legal candidate AND pack overweight.
   - Surplus = `_retention_surplus` of carried stacks (never below required counts). Sell whole surplus per
     stack via `_store_sell_key` → `_batch_sale_entry` (policy_shop.py ~3481 / ~3942), choosing stacks by the
     smallest lost sale value first until the weight is within the limit; destroy only units no shop buys.
   - Exclude from surplus the stock-out mining kit (treasure detection, digger, light, food) whenever the
     identify-staff (or other) stock-out mining remedy (10-05 decision) is pending or planned this visit — it was
     bought for that purpose (134643 s24-28: 6 treasure-detection scrolls bought for mining, then counted as
     surplus after a restart in 175411).
   - Loop bound: selling the same item signature by F3 twice in the same visit epoch (persisted with the visit
     epoch so a restart does not reset it; key = item signature, not anything the loop regenerates) is an
     observed sell/rebuy loop → immediate visible stop `town:blocked:overweight-surplus-rebuy-loop`.
   - Record every sale/destroy: reason `town:overweight-surplus-sold:home-full` /
     `town:overweight-surplus-destroyed:home-full` in the decision row and `jsonlog/overweight-surplus-disposal.jsonl`
     (time, item, count, price, Home stock, weight before/after). Add the new file to the rollback sidecar list.
   - If the surplus cannot bring the weight within the limit: `town:blocked:overweight-home-full-no-legal-relief`
     at once.
   - 090841 case (mode mine, spare Dwarf pickaxe): selling the spare is allowed only if the digging-tool
     retention keeps the standard one; record it and report.
New policy attributes (F3 ledger, F1c limit/entrance state): defaults in the restore chain; list them.

## Pins (fail on the base, pass after; substrates per analysis section 4; constructed parts declared)
P1 175411 last session: no deposit into the full page; relief first; then F3 sells the speed-potion surplus
   (Alchemist page from 134643 s25-28 reused, declared), weight ≤ limit, no stop, record written.
P2 134816 s12-s16: Home usable for weight-overload after `equipment-transaction:deposit-home-full`.
P3 090841 s691-693: overload not deferred.
P4 134200 s10439/s10441 and 134643 s6: no carried destroy with a non-full pack; no Identify-staff rebuy.
P5 134643 s24-28 shape: the mining kit is not sold as surplus; a constructed second F3 sale of the same
   signature in the same epoch stops with `overweight-surplus-rebuy-loop`.
P6 Restart version of P5 (fresh process, persisted epoch ledger).
P7 constructed: surplus insufficient → `overweight-home-full-no-legal-relief` at once.
P8 item_sink_lint covers the new sink; the record file is written and isolated in tests.
Step 1.5a pin 1 (134416/191943) expects the overweight stop; this step rewrites that expectation to the F3
outcome — state it in the report (whichever lands second updates it).
Regression: tests/test_overweight_home_hold_recorded.py, test_home_full_relief_recorded,
test_home_full_destroy_posted_confirm, step 1.5a's pins.

## Hygiene
manifest regeneration; the standard hygiene set; no full suite (merge gate).
Do not reuse luna's uncommitted bot-client-overweight-homefull-1008 work (it re-arms Home and conflicts
with 1.5a).
