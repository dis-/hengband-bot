# xbow-pref: ordinary Sling yields to a Light Crossbow

Base: f2bd447c (local main). Worktree: bot-client-xbow, branch xbow-pref.
Implementer: Opus 5.5. Commits: ed8aa833, 95d34463 (+ this report).

User decision 2026-10-02 (verbatim): 「上質以下同士の比較ならスリングよりライトクロスボウを優先。
スリングが高級品以上なら威力評価。という決定を以前したはず。」

## Step 1 (line numbers at f2bd447c unless marked "now")

Launcher comparison / selection sites:

- `equipment_optimizer.py:901-938` `_prefer`: the obtainable-ammo damage comparison
  (`launcher_damage`, :916-924) ran first; the Short Bow grade rule (:926-938) only applied
  when the damages were equal. Sling had no rule.
- `equipment_optimizer.py:1088-1106` `_stable_operational_best` pool filter: drops an ordinary
  Short Bow when any Light Crossbow is in the pool (Sling not covered), then :1108-1122 keeps
  only launchers with the best `launcher_damage`. Because `_selection_equivalence_key`
  (:1036-1059) separates loadouts by `(sval, high_grade)`, sling-vs-crossbow is decided by this
  pool filter, not `_prefer`; `_prefer` decides same-key dedupe and the `ranked` order. So the
  Short Bow rule was effective in selection (pool filter) while the Sling had none: the
  launcher_damage filter kept the sling (24 > 18 or 24 > 0).
- `equipment_optimizer.py:1214-1219` `launcher_damage` = `best_obtainable_launcher_damage`
  (launcher_damage.py:28-40) over `obtainable_ammunition`.
- What `obtainable_ammunition` contained: `policy_equipment.py:1223-1227` (and the cache
  signature :998-1003) = `(*snapshot.inventory, *self._home_knowledge_items)` ammo with
  count > 0. Carried + Home only; remembered store stock was NOT included. In the live state
  (no bolts carried or in Home) the crossbow therefore scored 0.0.
- Search-side pruning does not merge launcher kinds: `warrior_loadout_search.py:99-123`
  keeps launcher sval in the exact dominance key.
- Spare-launcher disposal: `policy_equipment.py:2692-2732` `_is_disposable_dominated_launcher`
  (callers: Home pass `policy_home.py:3755` via `policy.py:14335`, pack `policy_town.py:2391`
  via `policy.py:14366`). With the live Sling (+10,+10) equipped it returned **True** for the
  Home Light Crossbow (+4,+3) (store-ammo damage 24 vs 18, to_h 10 vs 4) - the crossbow was
  eligible for withdraw-and-dispose (pinned fail-before below).

Ammo procurement for the equipped launcher:

- Rung `tail:ammo` `policy_shop.py:2343`: buys `i.tval == launcher.ammo_tval and
  is_plain_store_ammo(i)` (ammo_carry.py:28-44) up to `_ammo_procurement_target`
  (policy_home.py:1128, weight-capped on the town floor) with `_ammo_purchase_preserves_plan`
  (2-stack carry plan, ammo_carry.py:47-77, AMMO_CARRY_TARGET 99).
- Town routing sends the "ammo" errand only to `STORE_WEAPON` (policy_town.py:2627, :2848);
  store ids printed from model.py:331-333: STORE_GENERAL = 0, STORE_WEAPON = 2.
- Recorded stock: 012442 capture row 44 store_type 0 (General) plain bolts 99 @ 3 gold;
  row 56 store_type 2 (Weapon Smith) plain bolts 99 @ 3; 042555 capture rows 116/120
  store_type 2 plain bolts 93 @ 3. (The 042555 capture has no store_type 0 page.)

After a swap:

- Old ammo: retention reservation is 0 for ammo whose tval != equipped launcher ammo
  (policy_home.py:808-817), so `_retention_surplus` (policy_home.py:1103) releases all iron
  shots and `_find_home_deposit` deposits them to Home (existing live pin
  `test_ammo_surplus.test_live_post_swap_releases_all_incompatible_ammo_to_home`, 09-10
  short-bow->crossbow swap). The 96 shots are deposited, not sold/destroyed.
- Old sling: `equipment_transaction_planner.py:225-247` deposits displaced items to Home in the
  finalize phase. It is not disposed afterwards: crossbow (+4,+3) damage 18 < sling 24, so the
  crossbow does not "dominate" the sling.
- Home launcher withdrawal: yes - `equipment_transaction_planner.py:116-123/159-167` withdraws
  target items with origin "home" (prepare phase), then takeoff, equip, finalize deposit.
  Pinned on the live items below.

## Step 2 fix

1. `equipment_optimizer.py` (now :902-946): one shared grade predicate
   `ordinary_launcher_yields_to_light_crossbow(launcher, crossbow)` (Sling sval 2 or Short Bow
   sval 12, not `launcher_is_high_grade` = ego/artifact/pseudo excellent|special) and
   `yields_to_light_crossbow(owned, owned, usable_launcher_ids)`.
   - `_prefer` (now :950-968): the grade rule runs BEFORE the launcher_damage comparison; the
     old Short-Bow-only block is removed (subsumed).
   - pool filter (now :1127-1145): covers Sling and Short Bow via the same helper, still before
     the damage filter. High-grade launchers fall through to the damage comparison.
   - `_selection_equivalence_key` uses `launcher_is_high_grade` (no duplicated predicate).
2. "Unusable crossbow" rule: `usable_launcher_ids` (now :1261-1269) = launchers with at least
   one compatible stack (count > 0) in `obtainable_ammunition`. A Light Crossbow without
   obtainable bolts never displaces a launcher that has obtainable ammunition; when neither has
   any (e.g. callers passing no ammunition) the rule applies as before (existing Short Bow pins
   unchanged).
3. Definition of "obtainable" (`policy_equipment.py` now :483-507
   `_obtainable_launcher_ammunition`): carried + Home knowledge ammo (as before) + remembered
   supplier pages `_town_supplier_stock` (written at policy.py:10058 on every non-Home store
   page; plus the currently open non-Home page, same pattern as policy_supply.py:130-132),
   filtered by `is_plain_store_ammo` = exactly what the `tail:ammo` rung buys. Used both for
   `obtainable_ammunition` (now :1249) and the optimizer cache signature (now :1028), so
   observing a store page with bolts invalidates a cached sling result. No new attribute,
   threshold or guard constant; no restored-checkpoint change needed.
4. `_is_disposable_dominated_launcher` (now :2713-2717): an ordinary Sling/Short Bow never
   marks a Light Crossbow as its dominated spare (same shared predicate).

QUEST_2.jsonc and EXPECTED_FIRST untouched.

## Pins (tests/test_light_crossbow_preference.py, fixture
tests/fixtures/xbow-pref-live-20261002-012442.json.gz, extractor
tests/extract_xbow_pref_fixture.py; rows 29/30/44/56/95 of
autorecover-20261002-012442-no-key-exhausted.bot-state-fixed.jsonl.gz; sha256 of the
LF-normalized decompressed body 182563a3...fd3d5d, checked by the test)

| test | before (revert) | after |
|---|---|---|
| live ordinary Sling (+10,+10)+shots vs Home crossbow (+4,+3)+General-store bolts -> crossbow (damage alone: 24 vs 18) | FAIL (sling) | pass |
| no obtainable bolts -> usable sling kept | pass | pass |
| high-grade sling (ego/artifact/excellent/special) -> damage decides both ways | pass | pass |
| `_prefer` pairwise: rule precedes damage; unusable crossbow loses | ERROR (no usable arg) | pass |
| ordinary Short Bow with higher ammo damage still yields; ego Short Bow kept | pass | pass |
| policy: remembered General + Weapon Smith pages -> plain bolts obtainable, enchanted shots excluded; fresh policy -> none | ERROR | pass |
| policy: open store page counts without memory | ERROR | pass |
| policy: ordinary sling never marks the Home crossbow disposable | FAIL (True) | pass |
| live swap plan: withdraw crossbow, takeoff sling, equip crossbow, deposit sling | pass | pass |

Revert checks: step 2a by stashing equipment_optimizer.py (2 fail/error), step 2b by
stashing src/ (3 fail/error), each once.

Requirement pin at the real entry (`choose_key`) is NOT built: no recorded board has a valid
calibration + `~f` skill list + full Home list with the crossbow at the same time (012442: level
29, decision log `result_source: calibration-required-return`, and the fresh-policy replay
raises `ProtocolSchemaError` for the missing `~f` list; 042555: Home page 52 not recorded;
live calibration file is level 30 observed at turn 2865831). Needs: a recorded town board
after calibration with the complete `~9` Home list including page 52, plus the `~f` reply.

## Verification (one module per process)

- tests.test_light_crossbow_preference: 10 OK
- tests.test_equipment_optimizer: 93 OK
- tests.test_warrior_optimization: 36 OK
- tests.test_warrior_equipment_evaluator: 11 OK
- tests.test_dualwield_recorded: 6 OK
- tests.test_policy_equipment: 192 OK (prints its existing R4 diagnostic line)
- launcher/ammo modules: tests.test_ammo_surplus 4 OK, tests.test_launcher_deferral 7 OK,
  tests.test_quest_ammo_not_bought 8 OK
- tests.test_home_equipment_disposal: 6 OK (extra, directly touches the disposal guard)
- tests.test_test_fakery_lint: 13 OK
- scripts/assertion_change_audit.py --base f2bd447c: "No changed pre-existing assertions or
  forbidden test edits."

DO-NOT-RUN (for Claude): full suite / parallel runner, tests.test_cli, tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states, long recorded replays. Most relevant to
this change in the full suite: tests.test_policy_home (Home disposal pass, sling/crossbow
retention cases :1278-1430), tests.test_policy_town, tests.test_policy_shop.

## Risks for the live bot

- Home reachability: the live stop is `town:blocked:overweight-home-unreachable`; the swap
  needs Home. Weight effect (fixture unit weights): crossbow 110 vs sling 5, iron shots 5 each,
  bolts 3 each: +10.5 lb launcher, -48.0 lb (96 shots to Home), +29.7 lb for 99 bolts
  (purchase capped by `_ammo_procurement_target`) = about -7.8 lb net.
- Q2 stays not-ready right after the swap: plain bolts give (3+0+3)x3 = 18 < 25 until the
  generic enchant (`_launcher_enchant_needed_svals`, now policy_equipment.py:3085) raises
  to_d to 6 (27). That needs 3 successful to-dam scrolls with gold above FUNDRAISING_START_GOLD.
- Restart churn window: `_town_supplier_stock` is process memory (not in the flight-recorder
  checkpoint). If the bot restarts after equipping the crossbow but before buying bolts, the
  crossbow has no obtainable bolts while the Home sling has Home shots, so the optimizer swaps
  back to the sling until a store page with bolts is seen again. Bounded per restart; no loop
  within one process (sling/shots usable + crossbow usable keeps the crossbow).
- No sling/crossbow transaction loop otherwise: after the swap the sling and shots sit in Home
  (sling still "usable"), the crossbow is usable via remembered bolts, so the grade rule keeps
  the crossbow. The ordinary sling is kept in Home (not disposed).
- Remembered plain ammo of a new name on a store page changes the optimizer signature once
  (one re-optimization).


## Round 2 (review jsonlog/REVIEW-xbow-pref-sol.md in C:/hengband/bot-client, coordinator design)

Commits: 4b23df1e (P1), 2bf665b1 (P2+P3). No new policy instance attribute (the supplier tuple
`LAUNCHER_AMMO_SUPPLIERS` is a class attribute), so no restored-checkpoint normalisation.

- P1 hysteresis (`equipment_optimizer.py:930-951`, `yields_to_light_crossbow`): the
  missing-bolts exception only blocks swapping INTO a Light Crossbow. `crossbow.origin ==
  "equipped"` (:948) keeps the grade rule regardless of ammunition evidence, so zero bolts or a
  supplier page forgotten after a restart never swap back to an ordinary Sling/Short Bow. Bolts
  are then procured as usual (or the bot departs with what it has, USER DECISION 2026-09-14/16).
  A high-grade Sling/Short Bow is still compared by damage (user rule), unchanged.
- P2 one supplier selection (`policy_equipment.py:486-574`):
  `LAUNCHER_AMMO_SUPPLIERS = (STORE_WEAPON, STORE_GENERAL)`;
  `_current_town_supplier_page` (open page, or remembered page observed in this town and younger
  than STORE_RESTOCK_WAIT_TURNS, the same test as policy_town.py:3159-3168 / policy_quest.py
  :842-850); `_launcher_ammo_offers` (plain = `is_plain_store_ammo`, affordable = count > 0 and
  price <= gold, i.e. a positive purchasable quantity); `_launcher_ammo_errand_store` (first
  supplier not attempted this visit and not observed this visit without offers; unobserved is
  tried). Users:
  - swap-in eligibility `_obtainable_launcher_ammunition` (offers only);
  - ordinary ammo errand `policy_town.py:2621-2629` and `:2845-2855` (was `STORE_WEAPON` only at
    :2627/:2848): Weapon Smith first, General Store when the Weapon Smith was attempted or shows no
    affordable plain ammo; still bounded by `_town_store_attempted`;
  - quest carry suppliers `policy_quest.py:807-830` (was static `(STORE_WEAPON,)` at :802-803):
    for `QUEST_LAUNCHER_AMMO_CARRIES` (:407) the errand store; once every supplier is exhausted
    the declared supplier stays the Weapon Smith, so the existing exhaustion/abandon path is
    unchanged. Callers pass the snapshot (policy_town.py:2773, :2798; policy_quest.py:844).
  - Probe on the recorded General Store board (row 44): `_next_purchase` selects the plain iron
    shots via rung `tail:ammo` (shortage 51), so the General Store purchase path exists.
- P3 freshness: only current-town, non-expired pages (above). Recorded turns show it matters:
  the General Store page (2320759) is expired at the surface board (2321880, gap 1121 >= 1000)
  but current at the Weapon Smith board (2321048).

Round-2 pins (tests/test_light_crossbow_preference.py, 16 tests):

| test | revert | after |
|---|---|---|
| equipped crossbow, zero bolts, empty supplier memory, ordinary sling in Home -> crossbow kept | FAIL (P1 line -> False) | pass |
| sling equipped, no bolts obtainable anywhere -> swap-in blocked | pass | pass |
| ammo errand: Weapon Smith stocked -> Weapon Smith; Weapon Smith stock-out (derived page) -> General Store; Weapon Smith attempted -> General Store; both attempted -> none | FAIL | pass |
| bolts remembered in another town -> sling kept; same town -> crossbow | FAIL | pass |
| other-town and expired pages are no evidence | FAIL | pass |
| unaffordable store ammo is no offer | ERROR | pass |

(`test_remembered_plain_store_bolts_are_obtainable_ammunition`, added in round 1, now records
observations the way policy.py:10058-10062 does and evaluates on the Weapon Smith board where both
pages are current.) Derived inputs, stated in the tests: the shot stack cut from 99 to the 48
recorded at rows 29-56 so the ordinary ammo errand is live, and the row-56 Weapon Smith page with
its plain shots removed (stock-out). Revert checks: P1 by replacing the equipped clause with False
(1 fail), P2/P3 by stashing the three policy files (3 fail, 1 error).

Round-2 risks:
- Observations are cleared on every fresh town visit, so swap-in needs a supplier page observed
  in this visit; if Home is visited before the Weapon Smith the swap waits for a later Home trip
  in the same visit (the optimizer signature changes when the page is observed).
- With the Weapon Smith attempted and ammo still below target (stock limit, weight cap, or the
  two-stack rule refusing a merge) the errand now adds one General Store trip; bounded by
  `_town_store_attempted`.
- Quest launcher ammo can now be routed to the General Store after the Weapon Smith is exhausted;
  `_quest_carry_obtainability` then treats the untried General Store as obtainable instead of
  abandoning the carry immediately.
- Not run here (DO-NOT-RUN): tests.test_policy_town and tests.test_policy_shop exercise the
  changed errand/quest routing most directly; tests.test_policy_home as before.

Round-2 verification (one module per process, at 2bf665b1): test_light_crossbow_preference 16 OK,
test_equipment_optimizer 93 OK, test_policy_equipment 192 OK, test_warrior_optimization 36 OK,
test_ammo_surplus 4 OK, test_launcher_deferral 7 OK, test_quest_ammo_not_bought 8 OK,
test_home_equipment_disposal 6 OK, test_town_restock_trajectory 21 OK, test_test_fakery_lint 13 OK.
assertion_change_audit --base f2bd447c: no changed pre-existing assertions.

{"topic":"xbow-pref","implementer":"opus-5.5","round":2,"base":"f2bd447c","commits":["ed8aa833","95d34463","4b23df1e","2bf665b1"],"review_items":{"P1":"equipped Light Crossbow keeps the grade rule regardless of ammo evidence (equipment_optimizer.py:948)","P2":"one supplier selection LAUNCHER_AMMO_SUPPLIERS=(Weapon Smith, General Store) for swap-in eligibility, ordinary ammo errand (policy_town.py:2621-2629,2845-2855) and quest launcher-ammo suppliers (policy_quest.py:807-830); affordable plain offers only","P3":"only pages observed in the current town and younger than STORE_RESTOCK_WAIT_TURNS"},"new_attributes":[],"new_thresholds":[],"verified":{"test_light_crossbow_preference":16,"test_equipment_optimizer":93,"test_policy_equipment":192,"test_warrior_optimization":36,"test_ammo_surplus":4,"test_launcher_deferral":7,"test_quest_ammo_not_bought":8,"test_home_equipment_disposal":6,"test_town_restock_trajectory":21,"test_test_fakery_lint":13},"not_run":["test_policy_town","test_policy_shop","test_policy_home","test_cli","test_absorbing_states","full suite"],"blockers":["entry-point requirement pin still needs a recorded post-calibration town board with full ~9 Home list (page 52) and ~f reply"]}

## Round 3 (merged-main full suite regressions, coordinator design) - commit cd9c8574 on 5afa8525

Changes:
- `_launcher_ammo_errand_store` (policy_equipment.py:553-572): the Weapon Smith exactly as before
  (unless attempted). The General Store only when the current-town Weapon Smith page shows no
  affordable plain ammo of the type AND the General Store was not attempted this visit AND its page
  (current or remembered, like `_quest_carry_remembered_affordable`) shows an affordable plain stack.
  "Weapon Smith attempted" alone adds no General Store stop.
- Quest carry: `_quest_carry_suppliers(name)` is the original static method again (tests call it);
  the new `_quest_carry_supplier_stores(snapshot, name)` returns `(STORE_GENERAL,)` only in the case
  above, else the original suppliers (callers: policy_town.py:2773, :2798; policy_quest.py:844).
- `_obtainable_launcher_ammunition`: store offers are added only for the ammo type of an owned
  launcher (worn, carried or Home) that has no owned stack of that type. Launchers with owned ammo
  are ranked by it exactly as before, so optimizer inputs are unchanged unless store evidence makes
  an otherwise unusable launcher usable.
- no_live_state_artifact: the pin module docstring named the live state log; now it points to the
  extractor only.

Results (one module per process): test_light_crossbow_preference 16 OK, test_no_live_state_artifact
1 OK, test_policy_supply 202 OK, test_overweight_home_unreachable_recorded 12 OK,
test_classC_departure_remedies 5 OK, test_recall_stockout_set_end_recorded 5 OK, test_declarations_r14
2 OK, test_unaffordable_claim_tour_recorded 7 OK, test_town_approach_retired_recorded 8 OK,
test_policy_town 598 OK (incl. test_unobtainable_q22_ammo_defers_to_fundraising_departure),
test_test_fakery_lint 13 OK.

STOPPED - remaining failures are the intended behaviour change (user decision 2026-10-02); no
assertion was edited:
- test_tpstockout_restart_recorded::test_recorded_restart_and_checkpoint_travel_to_stocked_alchemist
  (both subtests), line 93 `assertEqual(key, '\x1b`n%.')` / line 94 `shop:travel`. New: key
  '\x1b`n(.' reason `equipment-transaction:travel-home`. Probe: target bow = Home
  "ライト・クロスボウ (x3) (0.75turn) (+4,+3)"; plan withdraw crossbow, takeoff Sling (+10,+10), equip
  crossbow, deposit sling; evidence = the recorded current-town Weapon Smith shelf with plain bolts
  83 @ 3 gold. With store evidence suppressed the old key/reason come back.
- test_classC2_departure_recorded (4 tests: any_remaining_safe_surplus_goes_home_before_guardian_switch,
  no_alternate_keeps_visible_stop_and_weight_requirement,
  public_stop_board_offers_deeper_guardian_remedy_after_restore,
  recorded_public_board_routes_ammo_home_before_departure): "uncaptured optimizer input: classC2
  8548c6b9.../c95c43b9...". Board turn 1493887: Sling (+7,+7) + Home Light Crossbow (+4,+3), no
  bolts owned, current-town shelf plain bolts 99 @ 3. With store evidence suppressed all 9 pass.
- test_identify_staff_live27_recorded::test_recorded_shortfall_enters_one_run_mining: "uncaptured
  optimizer input: live27 dc581429...". Boards turns 688808 and 689594-689975: Sling (+3,+2) + Home
  Light Crossbow (+4,+3), shelf plain bolts 98 / 49 @ 3. With store evidence suppressed it passes.
These three fixtures freeze capture-time optimizer outputs (tests/recorded_equipment_decisions.py,
fail closed on a new input signature); the new input is exactly the bolts evidence that lets the user
rule pick the crossbow. Decision needed: re-capture/extend those optimizer fixtures (or accept the
new first divergence in tpstockout), which edits recorded expectations and is outside my mandate.

{"topic":"xbow-pref","implementer":"opus-5.5","round":3,"base":"5afa8525","commits":["cd9c8574"],"passing":{"test_light_crossbow_preference":16,"test_no_live_state_artifact":1,"test_policy_supply":202,"test_overweight_home_unreachable_recorded":12,"test_classC_departure_remedies":5,"test_recall_stockout_set_end_recorded":5,"test_declarations_r14":2,"test_unaffordable_claim_tour_recorded":7,"test_town_approach_retired_recorded":8,"test_policy_town":598,"test_test_fakery_lint":13},"intended_change_failures":{"test_tpstockout_restart_recorded":2,"test_classC2_departure_recorded":4,"test_identify_staff_live27_recorded":1},"assertions_edited":0,"new_attributes":[],"decision_needed":"re-capture classC2/live27 frozen optimizer fixtures and accept tpstockout first divergence (crossbow swap) or not"}
