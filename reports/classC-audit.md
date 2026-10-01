# Class C departure audit (step 1, be0befed)

Scope: `C:\hengband\bot-client-live21`, branch `classC`. This step changes no code.
The starved fact is an executable owner for a failed departure leaf: the shop
router can install `departure-unsatisfiable` at `policy_shop.py:1292,1341`
before `_town_terminal_transitions` (`policy_town.py:4017`) or the late
Identify stockout owner (`policy_town.py:5750`) runs. `_town_special_key`
then consumes that verdict at `policy_town.py:5214` before recovery,
restock, or mining. The third verdict writer is `policy_town.py:5760`.

All references below are in `src/hengbot/` at the audit baseline. Predicate
references name the actual map entry, including duplicated recall-only leaves.
“Early verdict” means the two shop verdicts can bypass the named producer;
it does not claim every hypothetical combination was captured live.

## Decisions (quoted from the requested memory directory)

Sources are `C:\Users\user\.claude\projects\C--hengband\memory\`:

- D1 `departure-conditions-carried-only-decision-20260917.md`: 「食料に限らず、出発条件に自宅のアイテムを含めてはいけない。ダンジョンでは自宅のアイテムは使えないのだから当然である。」
- D2 `bot-home-first-procurement.md`: 「これは今回の特例ではない。店舗での購入より先に自宅からの回収を試みるべき、という原則はあらゆる場面で成立する」. Its second ruling permits purchase only on measured absence or a town without Home; internal Home failures are visible stops.
- D3 `identify-staff-20-mandatory-decision-20260917.md`: 「10F以降に潜る場合は鑑定の杖の合計チャージ20回を必須とする。調達が不可能な場合は採掘で時間経過させること。」
- D4 `overweight-handling-policy.md`: 「まず、重量を原因に要求物資を緩和してはならない」; 「重量超過した場合の対処について。まず要求物資の過剰分を自宅に預け入れる。現状の場合帰還27テレポート45は過剰。」; 「需要の再武装は許可する。ループしないよう留意すること。」; 「本当に預け入れに失敗するならそれは停止するべき事案である。町中で自宅への接近が不可能になるのは正常ではない。」
- D5 `recall-stockout-and-surplus-deposit-decision.md`: 「品切れなら採掘して待つ」; 「荷物満杯時は預け入れを最優先に行う。出発の条件とする。鑑定待ちがあっても止めない。」 (These quoted passages occur in the file's description/user-decision sections.)
- D6 `quest-ammo-stockout-decision-20260916.md`: 「待ちながら通常の潜行は行う (推奨)」. The decision limits the 99-ammo condition to quest entry.
- D7 `fundraising-food-and-empty-body-slot-decisions-20260929.md`: 「初期アイテムに食料となる杖があるため、最初の採掘で食料が問題になることはない。必要なら初回のみ条件を緩和。」; 「空いた鎧の欄は必ず埋める」.
- D8 `mining-light-mandatory.md`: 「光源なしでは採掘効率が落ちる。安価に購入可能であるため採掘時の光源確保は必須。もともとそういう指示だったはずである」.
- D9 `fundraising-shortage-persist-decision-20260918.md`: 「不足を保持し、資金稼ぎ後に必ず再判定」.
- D10 `unidentifiable-item-departure-policy.md`: 「鑑定不能品を除外して装備を選定する。鑑定不納品があっても出発は許可する。次回以降帰還時鑑定を試みる。この方針で。」
- D11 `bot-confirmed-loadout-record.md`: 「装備最適化が未完了の状態」でのダンジョンへの出発を禁止する。 The quoted rule permits the last confirmed legal worn loadout only when further progress is impossible; naked/calibration/target-not-worn departures remain forbidden.
- D12 `bot-recall-entry-invariant.md`: 「帰還ストックなしでダンジョンに潜る行動は採掘による資金回収に限定する。いかなる事情があっても許可しない。」
- D13 `black-market-optional-reserve-decision.md`: 「必需品の分を残す (推奨)」. Reserve is actual outstanding required supply cost, not a new gold threshold.
- D14 `guardian-bounce-alternate-deeper-ok-decision-20260925.md`: 「倒せない階でなければ深くても可」; no alternate: 「見える形で停止する」.
- D15 `home-claim-verdict-decision-20260919.md`: 「C→A：まず評決を必ず残す（推奨）」. An uncomposable Home request must have a named verdict.
- D16 `home-visit-executor-decision.md`: 「許可する　1」 approves the typed single Home executor and bounded failure reporting.
- D17 `teleport-reserve-paralyzer-decision-20260918.md`: 「1 ただし麻痺知らずを保持している場合には適用されない」 approves the stated option: spend survival reserves, replenish in town, mine on stockout.
- D18 `cursed-items-destroy-decision-20260918.md`: 「簡単のため呪われたアイテムは破壊する。余力のあるときに有用なものをサルベージする処理を実装するが、優先度は最低とする。」
- D19 `calibration-timing-decision.md`: 「提案を許可する。較正タイミングの指定は最適化してよい。」. Recover known invalidating factors before starting; if no recovery exists, calibration proceeds.

## Exhaustive departure leaf table

| Conjunct | Predicate file:line | Existing state-changing producer(s) | Decision | Wired before stop at baseline? |
|---|---|---|---|---|
| recall_departure_ready | policy_town.py:1618; policy.py:12687 | Home procurement; supplier buy; policy.py:14454 recall restock, :14508 one-run mining | D1,D2,D5,D12 | Town path yes; shop early verdict can bypass |
| calibration_loadout_restored | policy_town.py:1623 | policy_calibration.py:1067 restore; equipment transaction | D11,D16,D19 | Ownership continuation precedes town; typed failure remains |
| food_ready | policy_town.py:1624; policy.py:12661; policy_fundraising.py:261 | Home procurement; General/Magic buy; policy_town.py:4132 terminal restock/funds | D1,D2,D7,D9 | Early verdict can bypass terminal transition |
| light_ready | policy_town.py:1629; policy_supply.py:265 | policy.py:11042 wield/refill; Home procurement; General buy; terminal restock | D1,D2,D8,D9 | Direct wield/refill precedes; early verdict can bypass retry |
| quest_carry_ready | policy_town.py:1635 | Quest procurement and abandonment; fixed quest entry gate | D6 | Yes: constant true for normal departure, quest requirements unchanged |
| teleport_ready | policy_town.py:1636; policy.py:12768 | Home procurement, Alchemist buy, terminal restock/funds | D1,D2,D9,D17 | Early verdict can bypass retry |
| cure_critical_ready | policy_town.py:1637; policy.py:12772 | Home procurement, Temple/Alchemist buy, terminal restock/funds | D1,D2,D9 | Early verdict can bypass retry |
| identify_staff_ready | policy_town.py:1638 | Home procurement, Magic/Black buy, policy.py:14592 stockout mining | D1,D2,D3,D9 | live27 fixed on town path; shop early verdict still bypasses |
| teleport_items_safe | policy_town.py:1639 | safe-weapon Home need; equipment switch; curse/disposal | D11,D18; no specific unrecoverable random-teleport remedy found | Executable owners exist; retain stop without an owner |
| free_pack_slots_ready | policy_town.py:1643; :1693 | policy_town.py:1723 deposit route; identify/destroy/sell; :1856 overflow | D5,D15 | Yes: pack-pressure path precedes departure; retain bounded typed failures |
| inventory_weight_ready | policy_town.py:1644; policy_home.py:1110 | policy_home.py:1131 safe surplus; weight-overload need; Home deposit | D4 | live36 already fixed, rearm at policy_town.py:3019; no new threshold |
| hp_full | policy_town.py:1645 | policy_town.py:5317 town recovery; survival | No separate exhausted-recovery user decision found | Recovery exists; shop early verdict can preempt it |
| mp_full | policy_town.py:1646 | Same recovery/rest producer | No separate exhausted-recovery user decision found | Same early verdict risk |
| temporary_status_clear | policy_town.py:1647; policy.py:13626 | Same recovery; survival cures | No separate exhausted-status user decision found | Same early verdict risk; no invented cure policy |
| organization_complete | policy_town.py:1648 | organization-sale; Home deposit; item processing/overflow | D5,D10,D18 | Owners precede final departure; shop verdict based only on nonhome needs is insufficient evidence |
| equipment_departure_ready | policy_town.py:1652; policy_equipment.py:2342 | optimizer/calibration/transaction; confirmation persistence | D7,D11,D16,D19; authoritative AGENTS depth table | Yes; policy.py:13696 names exhausted equipment failures |
| home_candidate_resolved | policy_town.py:1653 | Home scan/identify/review; policy_town.py:5486 stale waiting release | D2,D10,D15,D16 | Yes while route executable; typed failure otherwise |
| home_catalog_ready | policy_town.py:1658; policy_home.py:760 | Home knowledge scan/catalogue | D2,D15,D16 | Yes; bounded unroutable catalogue follows existing predicate |
| home_pending_item_clear | policy_town.py:1662 | Home atomic withdraw; identify; stale consumed-item release :5493 | D2,D10,D15,D16 | Yes; no fabricated completion |
| home_pending_batch_clear | policy_town.py:1665 | Home batch procurement/withdraw/review | D2,D15,D16 | Yes while Home executable |
| home_batch_review_clear | policy_town.py:1668 | Home batch identification/review | D10,D15,D16 | Yes while Home executable |
| home_atomic_withdraw_clear | policy_town.py:1671 | atomic confirmation; HomeVisitExecutor.observe_outside | D15,D16 | Yes: pending operation owns before departure |
| digger_withdrawal_resolved | policy_town.py:1674 | queued Home digger withdraw; General fallback | D2,D16 | Yes: policy_shop.py:941 priority continuation; no invented retry |
| identification_need_clear | policy_town.py:1678 | identify producer; source buy; policy_town.py:4038 defer/funds/restock | D2,D10,D15 | Owner exists; early verdict can bypass terminal settlement |
| calibration_phase_complete | policy_town.py:1682 | calibration state machine | D11,D16,D19 | Yes: calibration ownership before town departure |
| calibration_restore_complete | policy_town.py:1685 | calibration restore/Home withdraw | D11,D16 | Yes while Home route executable; named failure remains |
| combat_weapon_ready | policy_town.py:1808; policy.py:15491 | policy_equipment.py:2931 carried restore; Home combat-weapon | D2,D7,D11 | Yes: weapon restore precedes departure |
| departure_home_pending_item_clear | policy_town.py:1809 | Same pending-item producers, without Home-availability exemption | D2,D10,D15,D16 | Same as home_pending_item_clear |
| departure_home_pending_batch_clear | policy_town.py:1810 | Same batch producers, without exemption | D2,D15,D16 | Same as home_pending_batch_clear |
| departure_home_batch_review_clear | policy_town.py:1811 | Same review producers, without exemption | D10,D15,D16 | Same as home_batch_review_clear |
| departure_home_atomic_withdraw_clear | policy_town.py:1812 | Same confirmation producer | D15,D16 | Same as home_atomic_withdraw_clear |
| departure_identification_need_clear | policy_town.py:1815 | Same identify/defer/fundraising producers | D2,D10,D15 | Same early settlement bypass |
| recall_landing_not_guardian_blocked | policy_town.py:5521 | guardian recall alternate/fallback at :5650 | D14 | Yes: independent destination safety gate |

The 26 ordinary entries, six additional recall entries, and guardian diagnostic
entry are the complete named map. Navigation (`policy_navigation.py:527,1003`)
and quest (`policy_quest.py:1027`) reuse it and can insert
`equipment_departure_ready` when their deeper entry gate refused. There is no
additional unnamed `departure_block` leaf at those sites. NeedSpecs at
`policy_town.py:2899-2991` are procurement owners, not extra departure leaves;
their full category list includes birth supplies, quest carries, stat restore,
curse removal, fundraising kit/digger/detection/food/light/oil, identification,
equipment/calibration, and optional sales/deposit/ammo/Black Market. D13 protects
the gold needed by their mandatory purchases.

## Step 2 rule and intended correction

Only the departure evaluator may issue the generic no-owner verdict, after
existing supplier, terminal-settlement, recovery, restock and stockout owners
have had their opportunity. A shop-plan exhaustion is evidence about shops,
not evidence that every departure remedy failed. Remove those premature
verdict writes and preserve final typed stops. No departure requirement changes.
Pins must show the real router reaches its existing transition before any stop,
and the resulting town decision selects the remedy. Recorded live27/live36 and
09-26 weight boards remain acceptance gates; no later historical board is
claimed as the effect of a changed key.

## Decisions still needed

No new policy is invented for unrecoverable HP, MP, temporary status, or a
teleport-unsafe item with no executable replacement/disposal. Existing recovery
and equipment producers are used; exhaustion keeps the typed stop. An explicit
remedy beyond those producers would require a user decision.

## Verification boundary

One module per Python process, PYTHONPATH=src;tests;scripts. Only explicitly
requested modules and new pins; stuck/withdraw OFF+s33 are the explicit
exception. Pending for Claude: test_cli, test_policy_town, test_policy_shop,
test_absorbing_states; long tour/town/overweight replays; producer-purity runs;
full first_divergence fixture sweeps; test_parallel_runner, test_timing_runner,
hunk_guard, verify_scope, mutation_battery and full-suite gates. EXPECTED_FIRST
and existing assertions stay unchanged. No UI, game, live bot, or jsonlog edits.

Assertion audit (step 1, verbatim):
```text
No changed pre-existing assertions or forbidden test edits.
```
