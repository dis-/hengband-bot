# Step 1.5d (first part): identify-staff purchase is not blocked by empty Home staves; fundraising can buy it

Plan: plans\PLAN-town-stability-20261009.md 手順1.5. Analysis: plans\STEP1.5d-IDENTIFY-STAFF-ANALYSIS.md
(R2, R4, R5 → fixes F1 and F4). F2 (selector skip instead of stop) and F3 (swap inside one store entry) are
larger and follow as a separate item after this one lands. Base: main after 1.5a/1.5b. Design only.

## Owner decisions (verbatim/summarized with source)
- 09-17 identify-staff-20-mandatory: 「10F以降は鑑定の杖20回分が必須・調達不可なら採掘」.
- 09-17 departure-conditions-carried-only: 出発条件に自宅のアイテムを含めない（自宅は調達可能性の判断にだけ使う）.
- 10-03 identify-staff-max-four: 鑑定の杖は4本以内・少ない杖から手放し回数の多い杖に買い替え（20回分は維持）.
- 10-05 stockout-mining-timepass: 品切れだけで出発できない時は採掘で時間を潰して再挑戦（3回で停止）.
- 10-08 black-market reserve: 闇市の任意購入は必需品1回分の補充代を常に残す.
- 08-18 home-first procurement.

## Problem (analysis R2, R4, R5)
- R2: for an identify-staff purchase the Home-first gate counts ANY staff/wand at Home as stock, including
  0-charge ones (policy_supply.py ~1005 → policy_home.py ~4074; `_evaluate_purchase_home_gate` /
  `_purchase_has_fresh_home_absence` policy_shop.py ~2080/~1840). The bot routes Home and withdraws an empty
  staff instead of buying the affordable one on the Magic Shop shelf. 7 of 9 observed Home pages had 0-charge
  staves/wands. ec69be10 fixed only the Home-full exception path.
- R4: in fundraising / stock-out mining mode the selector's fundraising block (policy_shop.py ~2961-3091) never
  returns the identify-staff rung (10-05 12:22: stopped in front of a restocked 823G/20 staff).
- R5: the rung can buy a 0-charge staff (558G in 122258 s19-21).

## Design (revision 2, after the fable review)
F1 Home stock for wand/staff needs counts only charged devices: put `charges > 0` into the static
   `_procurement_class_matches` wand/staff branch (policy_supply.py ~998-1013, equivalence at ~1005-1006) so
   the candidate (`_home_procurement_candidate` policy_home.py ~4074), the viable counters
   (`_home_procurement_viable_class_matches` / `_home_procurement_viable_item` ~4172/~4183), the gate
   telemetry (`_record_home_gate`) and `_queue_home_procurement_batch` all agree. Otherwise a 0-charge staff at
   Home makes the gate BLOCKED (`all_viable_deferred`, policy_shop.py ~2176-2185 → WAIT ~4753-4755) instead of
   ALLOW. Applies to every wand/staff class match (the MANA-food wand/staff equivalence stays; only 0-charge
   devices are excluded — a zombie cannot absorb a 0-charge device and `_procurement_missing_amount` already
   counts food only with pval > 0, policy_supply.py ~1080-1086).
   `_identify_staff_acquisition_worthwhile(snapshot, charges)` (policy_supply.py ~698, needs a snapshot) is used
   only inside the gate, after a candidate is found, as an ALLOW_PURCHASE override
   ("evaluate-home-stock-not-worthwhile"); never to filter candidates.
F4 The fundraising block (policy_shop.py ~2961-3091) returns the identify-staff rung item when
   `_fundraising_identify_staff_only_block` or the identify mining plan is active; the rung (~3256-3272) and the
   typed rung (~2691) require charges > 0 and `_identify_staff_acquisition_worthwhile`. On a successful
   identify-staff purchase that makes identify ready, drop `_identify_staff_mining_plan` (otherwise a needless
   mining trip happens when gold < 15,000; policy_town.py ~4388-4410). A 0-charge staff is never bought.
Out of scope, record as an issue: the MANA-food rung bought three 0-charge wands (1,287G) in 111342 s158/167/171
(`_mana_food_purchase` policy_supply.py ~910 has no charge condition).

## Pins (fail on the base, pass after; substrates)
- 175851 s1999 (Magic 715/11; Home page 1 has only 0-charge identify staves): HOME_FIRST → ALLOW_PURCHASE
  ("evaluate-no-candidate"). Do not pin the refusal-carrying later rows.
- 122258 2nd session s15-17 (state rows 15/18/19, 8 0-charge staves at Home): no 0-charge Home withdrawal.
- 122258 s19-21 (rows 27/30/31, Magic 558/0): nothing wanted.
- 122258 s53 (row 78, Telmora, j=823/20, carried 18+0): the 823/20 staff wanted; `rejection_reason != "reserved"`.
- 214921 s50 (IST shadow home-first caused by a 0-charge wand at Home): in-store buy.
- 224534 s41 (existing fixture tests/fixtures/identify-staff-stockout-20261007.json.gz rows 68/69): MANA-food
  394/40 no longer home-first on the 0-charge staff.
- Unit: purchase success drops the mining plan.
- Revert each predicate alone → its pin fails again.
Expected on the record: 5 of the 13 stops become purchases (+1 partial); the rest are R1 (disposal / full-Home
relief) and R3 (swap inside one entry) → next item F2/F3.

## Expected effect / risk
Turns the R2/R4/R5 cases into purchases. With Home still full, the next stop may be the Home-full
equipment/overweight one (1.5a/1.5b). 0-charge staves stay at Home (relief may destroy them later per 10-04).

## Hygiene
Standard set + the shop/supply/home modules touched. No full suite (merge gate).
