# tpstockout

## Step 1 (base ace34cd2)

The 02:35:56 capture ends with teleport stock 4/15, gold 10903 and only
`teleport_ready` false. Decision 37 at turn 2571984 is
`town:blocked:no-actionable-claim-owner` (`5`), followed by decision 38 `probe`
(`8`). The 02:34:27 capture contains the actual Alchemist shelves at 2570058
and 2570072: no Teleport scrolls. The later capture supplies Home knowledge
and the outside deciding board. These are independent frozen seams, not a
claim to replay the intervening operations.

`policy_town.py:2690` only registers an attempted supplier again if remembered
stock is affordable. An empty shelf therefore removes its executable shopping
route while the shortage remains. `policy_town.py:5299` only installs an
Identify-staff mining remedy; `policy.py:14586` only starts recall stockout
mining. The progress invariant at `policy_town.py:1304` finds no procurement
key and replaces wandering with `no-actionable-claim-owner` at :1319.

| Conjunct / supply | Supplier evidence | Base mining time-pass |
| --- | --- | --- |
| recall_departure_ready / recall | Temple, Alchemist (`SUPPLY_STORES`) | Yes, recall-specific starter |
| identify_staff_ready | Home, Magic (Black observed availability veto) | Yes, Identify-specific starter |
| teleport_ready / teleport | Alchemist | No |
| cure_critical_ready / cure | Temple | No |
| food_ready / food | General; Magic for mana eaters | No |
| light_ready / oil or light | General | No |

The common supply ledger is `policy_supply.py:116`; local categories and
supplier mappings are `policy_town.py:3895`; shop-purchasable shortages are
enumerated at :3925. Recovery, pack space/weight, equipment, calibration and
pending transaction leaves are not empty-shelf supplies. Quest carries have
their separate decided abandonment/procurement rules (:2720 onwards).

Acceptance decisions: D17 says survival reserves may be spent, replenish in
town, **MINE ON STOCK-OUT**. Class C requires offering and genuinely failing
the decided remedy for each conjunct before declaring departure impossible.
No departure requirement or UI classifier is changed.

## Verification and implementation

Pending Step 2.
