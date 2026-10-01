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

{"topic":"xbow-pref","implementer":"opus-5.5","base":"f2bd447c","commits":["ed8aa833","95d34463"],"files":["src/hengbot/equipment_optimizer.py","src/hengbot/policy_equipment.py","tests/test_light_crossbow_preference.py","tests/extract_xbow_pref_fixture.py","tests/fixtures/xbow-pref-live-20261002-012442.json.gz"],"fail_before":{"optimizer":["test_live_ordinary_sling_yields_to_home_crossbow_with_store_bolts","test_pairwise_rule_precedes_damage_and_respects_unusable_crossbow"],"policy":["test_remembered_plain_store_bolts_are_obtainable_ammunition","test_open_store_page_counts_without_memory","test_ordinary_sling_never_marks_home_light_crossbow_disposable"]},"verified":{"test_light_crossbow_preference":10,"test_equipment_optimizer":93,"test_warrior_optimization":36,"test_warrior_equipment_evaluator":11,"test_dualwield_recorded":6,"test_policy_equipment":192,"test_ammo_surplus":4,"test_launcher_deferral":7,"test_quest_ammo_not_bought":8,"test_home_equipment_disposal":6,"test_test_fakery_lint":13},"new_attributes":[],"new_thresholds":[],"blockers":["entry-point requirement pin needs a recorded post-calibration town board with full ~9 Home list (page 52) and ~f reply"]}
