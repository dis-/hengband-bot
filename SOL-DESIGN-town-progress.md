# Town progress: observed effects, persistent work, bounded decisions

Design only; source base `4d864cb3`, branch `town-progress-design-1006`, 2026-10-06. Status:
progdef2 design revision; resolves the adjacent review and operator answers. The work-kind table
covers the inspected registry and additional town execution paths. The complete producer/call-site
reconciliation is **not certified**; slice 0 must finish it. No production/test changes, game/bot
execution, test runs, or push accompany this document.

## Decisions and scope

User decision, 2026-10-05 (translated): "Town errand retirement (town:blocked:owner-retired) only
records, does not stop the bot, until fixed. In parallel, rebuild the definition of progress for ALL
kinds of town work (buy, sell, Home catalogue, deposit, withdraw, equipment change, remove curse,
identify, Home-full relief, etc.): list what observed event counts as progress for each, rebuild the
counting, and switch back to stopping once retirement no longer appears on the records. Truly
non-progressing repetition is stopped by the other watchers (loop detection, town progress check)."

The 2026-10-04 decision requires enumerating every call site and routing it through one entrance.
Implement the registry and observer first; do not grow a collection of reason-specific incident
patches. Retirement remains log-only during migration; new non-progress/impossible outcomes are
independent watcher outcomes and must not be swallowed by that compatibility mode.

Operator answers for progdef2: Q1(B), replace the 600 s window in slice 1 with a visible count-based
stop on 3 distinct retirements in one town visit with no productive admitted work between them (no
observed effect or distance progress). Retirement otherwise stays log-only. Q2, row-by-row live
activation is accepted: slice 0 enumerates/certifies every call site through the single entrance;
each complete row then goes live when all its producers map and its observer lands. No elapsed-time
guards. The first live slice closes (b); the next closes (a).

## Code-derived inventory and evidence boundary

Enumeration used here: read `claim_ladder.py:_RUNGS` (lines 212-418), enumerate `@claims` decorators
with Python AST, read `_town_need_registry` (policy_town.py: 3145-3236), `_purchase_rungs`
(policy_shop.py:2345-2445), and the exact baseline `scripts/town_producer_baseline.json`. The
baseline has 652 entries: 498 pure helpers, 99 town-producer candidates, 44 delegated adapters, 11
dungeon-only. Those are baseline classifications, not 99 proven town-only producers.
`town_structure_lint.py:producer_census` follows imports, aliases, callbacks, return dependencies
and reachability from `choose_key`; it conservatively includes dungeon paths. Reading its algorithm
is not proof of census closure.

For implementation, generate a call-site manifest from that census, union it with ladder producers,
decorated producers, need/purchase registries, direct `choose_key` branches, post-decision rewrites,
and driver prompt continuations. Each entry must name caller/line, callee, possible town context,
table row, admission entrance, effect observer, and delegation. Account for all 44 adapters; a
selector is not an independently successful work operation. Fail the coverage gate for unmapped
candidates; justify dungeon-only paths from predicates. Do not accept a blanket module exclusion or
a baseline label as a proof. Future additions must fail the same gate until reviewed.

Slice 0 certification also requires a runtime fail-closed receipt at the single logical emit seam:
`_offer_execution*` (P:3371-3435) and the driver's actual send must share one validator, including
driver `LEAVE_STORE_KEY` overrides (cli.py:4381-4385), prompt clears and executor-released tails
(P:10262-10265). Any key while `in_town or store is not None` without a mapped work record emits
`town:blocked:work-contract:unmapped-producer` and is not sent. Effect observers may be shadow-only
here; work-record coverage cannot be shadow-only permission to bypass admission. Replay the
versioned recorded corpus and both captures with zero such receipts before slice 2 goes live; static
census alone is insufficient.

Source abbreviations below are files in `src/hengbot`: T=policy_town.py, H=policy_home.py,
S=policy_shop.py, E=policy_equipment.py, I=policy_identification.py, P=policy.py, Q=policy_quest.py,
F=policy_fundraising.py, C=policy_calibration.py, U=policy_supply.py, IS=policy_instore.py. Function
names identify stable references at this base.

## One admission and observation rule

Use a semantic work record, separate from a reason string or transient claim ID: `(town_visit_epoch,
root_work_id, kind, target_identity, target_revision)`. Store UI openings are child attempts, not
new town visits. Actual town change or return after completed departure/dive creates a new epoch;
an unfinished cross-town purpose retains its root record and exhausted-target set through travel.
An incidental floor transition, restart, reason rewrite, or plan rebuild cannot renew that purpose.
Checkpoint the
record; absent old checkpoint evidence, mark reconstructed state and use the first observed board as
baseline without crediting it as progress.

All town producers, nested calls and rewrites pass through `_town_producer_entry` and one final
admission/emit seam. Admission names the root, child, concrete target, expected observation, route
metric and N before offering a command. Checked item operations, staged tails, in-store operations
and prompt answers inherit that record. A detector that substitutes work must either continue the
same admitted work or close it visibly before admitting a different one. Keep requester, operator
and observer separately; accounting follows the work, not `owner_for_reason` of the rewritten label.

An activation ledger names each table row, complete producer manifest, observer version and
qualifying pins. A certified row uses the generic rule immediately; rows awaiting observers keep
legacy watchers and shadow effect receipts, while still obeying the unconditional emit validator. No
unmapped call site is exempt. Shared producers dispatch by admitted row; a closure cannot fall back
to a shadow alias of that same work. A live composite's required child evidence/bounds must land
with its observer. Delegating wrappers inherit the selected child's activation; they cannot turn
a shadow row live by relabeling it. Unresolved routing uses its own bounded routing contract.

**Generic rule:** after N of this work's own decisions with neither a new observed effect nor
distance progress, close it with a visible reason and tombstone its stop for the rest of the town
visit. Never re-acquire that stop in the same visit. A proven impossibility closes immediately,
before N. For cross-town roots, the same prohibition survives their travel legs until the purpose is
resolved. Other independently feasible work may continue; an unresolved mandatory prerequisite with
no admitted remedy stops the bot. An optional failure skips only that work. A typed
contract/ownership defect stops visibly regardless of whether the original errand was optional.

Count one admitted policy decision, including a selected no-step/refusal or await, once by decision
sequence. Include zero-energy decisions. Polls and duplicate observations spend nothing; prompt
segments of one decision are not extra decisions. Policy `""` while an already admitted one-shot
tail is in flight is a poll, bounded by that executor's declared finite tail length/response steps.
Tail index does not credit progress; no unbounded tail append/restart is allowed.
Exhausted/unresolved tails close visibly; an empty result without such a tail is a selected no-step
decision and is charged. Charge root/child once each. Unrelated bookkeeping or genuine safety
preemption freezes the work's counter; it does not reset it. Work resumed after preemption retains
counters and bounds. At each decision first settle the previous command against fresh observations,
then increment if no qualifying evidence appeared. Baseline creation earns zero credit. Close on the
Nth unsuccessful decision, before issuing N+1. Do not exempt all observation waits or introduce
elapsed-time guards.

Effect credit requires the named target's changed facts on a fresh, causally matched observation. A
posted key, released tail, expectation, new claim, executor phase/index, changed reason, gold
spending, store open/close, or plan index is not a business effect. Log proof even when a transport
child completes. A response may settle several claims but earns one evidence credit per work. New
shelf/catalogue evidence counts once per target revision; identical refreshes and
invalidating/revalidating one's own cache earn nothing.

Distance progress is a new **minimum observed** legal route rank for the same target and route
revision, preferably BFS remaining edges. An expected next step or any changed distance is
insufficient. Returning from rank 1 to 0 after already reaching 0 earns nothing. Freeze target
selection during the leg; route revisions require observed topology change, not another selector
result. One's own store exit/entry and inside/outside position changes are not topology changes and
cannot reset the route minimum or mint a fresh entry milestone. Unreachable routes close visibly.
Native travel can advance many edges in one decision; straight-line distance must not reject a
genuine BFS detour.

Finite child milestones (arrival, entry, page/address acquisition, exit) can complete transport
children once. Their evidence does not repeatedly reset a purchase/relief root. Keep the root's
target obligations and consumed milestones through every reopen. A composite uses a fixed finite
obligation list; observed completion removes obligations. Reversible buy/deposit, strip/restore, or
withdraw/redeposit cycles cannot replenish that list. Revised requirements need an external observed
cause and explicit old-work closure; local toggles cannot erase a tombstone. A required blocked root
must name a finite remedy or stop.

Proposed new reasons: `town:work-closed:done:<kind>`, `town:work-closed:impossible:<kind>:<cause>`,
`town:blocked:work-nonprogress:<kind>:<target>`, and `town:blocked:work-contract:<cause>`. Preserve
existing specific visible causes as aliases. Terminal/impossible declarations are resolved
immediately, never represented as another repeatable WAIT task. A safely required UI exit is a
separate bounded cleanup child; preserve the original failure and tombstone. Never discard a posted
operation's uncertain effect to open a competing visit.

## Work-kind table

This is the proposed contract, not a description of today's vector accounting. N is unsuccessful own
decisions per named child, inherited by its semantic work; successful finite obligations allow long
productive batches. `R` means the observed route rule above, `-` means no distance credit. Causes in
the impossible column are visible closure causes, including proposed new causes. Shared
selectors/dispatchers are listed after the table; their callers inherit the row selected. Source
NeedSpec departure-blocking status remains authoritative.

| Work / registry categories | Producers | Observed effect = progress | Distance | Done | Impossible / visible cause | N |
| --- | --- | --- | --- | --- | --- | --- |
| Ordinary supply buy: birth-supplies; recall, teleport, cure-critical, oil, food, light, identify-staff | S:_shop_core, _atomic_shop_transaction_key; IS:_in_store_emit | Bound ware quantity/usable charges increases in pack, matched payment and shelf effect where available | R to supplier | Required carried target reached | stock-absent, unaffordable, pack-full, operation-unconfirmed, sell-rebuy-churn-defect | 8 |
| Mining kit buy: fundraising-kit/digger/detection/food/light/oil, mining-digger/detection | Same buy producers; F:_fundraising_key | Named kit shortage decreases by observed acquisition | R | Kit child target reached | no-compatible-digger, stock-absent, funds-insufficient | 8 |
| Quest buy: quest-throwing-items, quest-ranged-kit, quest-scrolls, quest-carry, quest-speed/healing | Same buy producers; Q:_opening_q34_town_key, _fixed_quest_key | Bound carry obligation decreases; compatible ammo/launcher retained | R | Named quest carry target reached | incompatible-ranged-plan, missing-supplier, funds-insufficient | 8 |
| Optional buy: ammo, throwing-torches, black-market, proactive restore, reserve curse/enchant stock | Same buy producers; S:_purchase_rungs / selectors | Named selected quantity/charges acquired within reserve | R | Selected finite purchase complete | reserve-refused, no-offer, sell-rebuy-churn-defect | 8 |
| All sales: book-sale, organization-sale, low-level-sale, mana-food-sale, device-sale, weapon-sale, light-sale, disposal, home-disposal-sale | S:_store_sell_key, _batch_sell_key, _batch_sale_entry; H:_home_disposal_processing_key; E:_find_weapon_sale selector | Bound surplus leaves pack with matched proceeds; batch observes actual per-target removals | R to accepting shop | Selected surplus disposed; retained stock intact | sale-refused, target-protected, no-accepting-store, sell-rebuy-churn-defect | 3 |
| Sale-tag inscription / checked address | S:_batch_sell_key, _batch_sale_entry; IS:_in_store_inscription_observed | Named item inscription/address is freshly confirmed; once per preparation obligation | - | Bound operation can execute | ambiguous-address, inscription-unconfirmed | 3 |
| Supplier browse / experience-restore-check / shelf absence | S:_shop_core; IS:_observe_shelf_evidence | First complete target shelf evidence answers live need for this revision | R | Need classified supplied/absent/refused | incomplete-page, stale-evidence, no-operation-composable | 8 |
| Store approach / native travel / entry / boxed escape | S:_shopping_approach_key, _shopping_approach_step, _stage_shopping_approach_key, _released_restock_store_key; T:_town_travel_key, _boxed_town_breakout_key, _commit_boxed_town_breakout_key | Correct target store page/landmark observed once; business root remains pending | R, no position-only credit | Named route/entry child reached | route-unavailable, entry-unconfirmed, target-exhausted | 8 |
| Store exit / pending UI cleanup | S:_shop_core, _offer_store_sale_leave; IS:_in_store_leave; H:_home_full_leave_key; P:_home_tail_leave_continuation | Matching store context absent on fresh board | - | Exit observed | exit-unconfirmed, unsafe-pending-operation | 8 |
| Home catalogue: idle-consumable-scan, equipment-catalog; scan/knowledge work | H:_home_full_knowledge_key, _home_errand_knowledge_key; P:_home_catalogue_work_key, choose_key scan branch | Complete fresh catalogue answers unresolved revision, including empty Home; unique missing page/address resolved | R to Home; unique page obligation, not cycling page number | Complete identities/addresses and fresh knowledge | catalogue-incomplete, Home-unreachable, stale-address | 8 |
| Home deposits: deposit, space-deposit, weight-overload | H:_home_deposit_key, _open_home_deposit_key, _atomic_home_deposit_dispatch_key, _compose_home_operation; T:_town_space_deposit_key; P:_observe_home_atomic_deposit_outside | Bound quantity leaves pack for Home, matched stock/merge evidence; actual slots/overload shortage improves | R | Selected deposit effect confirmed and target satisfied | home-full, deposit-refused, protected-item, confirmation-missing | 8 |
| Home withdrawal: identification-withdrawal, stored-digger/detection, ammo-home-first, quest-launcher, stored quest throwing stock, experience-potion-home, safe/combat-weapon | H:_atomic_home_withdraw_dispatch_key, _confirm_home_withdrawal_address, _home_quest_launcher_key, _probe_unobserved_home_withdrawal; Q:_morivant_home_item_key; E:_queue_standing_home_digger, _home_rearm_key; P:_observe_home_atomic_withdrawal_outside | Bound item/count enters pack; matched Home decrement/address evidence, including stack merges | R | Requested finite quantity acquired | target-absent, pack-full, stale-address, withdraw-unconfirmed | 8 |
| Home errand / visit executors | H:_file_home_errand, _prepare_home_visit_operation, _compose_home_operation; HomeErrandExecutor, HomeVisitExecutor | Row-specific scan/take/deposit evidence, not executor transition | R | All declared finite obligations observed | no-executable-step, request-conflict, unresolved-effect | 8 |
| Home-full relief / retry deposits | H:_home_full_relief_key, _home_full_skip_key, _home_full_identify_carried_key | Confirmed shelf take followed by safe sale/destruction earns a relief slot; carried-only disposal earns pack space, not Home space | R for fixed child; finite scan/take/disposal obligations | Sell surplus -> destroy cheapest unneeded if no sale remedy -> slots freed and deposit resumed; otherwise impossible -> skip optional deposit and proceed | home-full-no-sellable-surplus only after sale AND cheapest-safe-destruction remedies evidenced exhausted; protected/uncertain items cannot be destroyed | 3 for stalled orchestration; child operation uses its row N |
| Home disposal identification / dominated disposal | H:_home_disposal_home_key, _home_disposal_processing_key, _home_dominated_disposal_key | Take, knowledge gain, and sale/destruction each confirms named finite obligation; no credit for queueing | R | Named surplus disposal confirmed | protected-after-identification, sale-refused, no-safe-disposal | 3; take/scan 8 |
| Safe destruction / overflow / pack triage | H:_destroy_item_key; T:_town_destroy_key, _town_overflow_destroy_key; I:_full_pack_destroy_key, _full_pack_loot_triage_key; P:_verified_destroy_dispatch_key | Bound permitted quantity actually removed; reserved gear survives | - | Selected removal/space target observed | protected-item, ambiguous-address, destroy-unconfirmed | 3 |
| Normal/full identification: identification-source, home-disposal-identify, equipped/pack/device targets | I:_identify_carried_item_key, _carried_identify_command, _pack_pressure_identify_key; E:_town_equipped_identification_key; T:_town_device_processing_key, _town_item_processing_dispatch_key; H:_home_full_identify_carried_key | Named item's known/fully_known facts advance; source consumption alone is insufficient | R to named source/library via child | Requested knowledge level confirmed | no-reliable-source, unidentifiable-target, source-failed, full-id-unavailable | 3 |
| Device processing / mana device absorption | T:_town_device_processing_key, _town_item_processing_dispatch_key; U:_mana_food_survival_override_key | Named usable charges/knowledge/status changes toward declared objective | R via procurement child | Declared device/status target observed | unusable-device, absorption-unconfirmed, no-source | 8 |
| Remove curse: remove-curse, required-star-remove-curse, home-star-remove-curse-use/check/stock, star-remove-curse | T:_town_remove_curse_key; buy/Home children above | Named worn item's curse flags removed; first evidenced permanent-curse result closes impossible | R via named supply child | Required removable curses cleared | permanent-curse, no-usable-scroll, cannot-read-scroll, effect-unconfirmed | 8 |
| Launcher enchant | E:_town_enchant_launcher_key | Bound launcher bonus increases; consumed scroll alone is not effect | R via supply child | Fixed bonus target reached | no-scroll, enchant-failed-bound, target-changed | 8 |
| Equipment optimization / calibration / equipment-work | E:_prepare_equipment_optimization; P:_home_catalogue_work_key; C:_consume_equipped_character_sheet, _publish_character_dump | Fresh validated character facts/catalogue resolve a missing input; comparison computation is not game progress | R only for explicit information child | Verified feasible plan or evidenced no-upgrade verdict | calibration-unavailable, no-feasible-loadout, missing-knowledge | 8 for information; pure solver spends no game decisions |
| Equipment transaction / slot change / restore weapon | E:_equipment_transaction_town_owner_key, _equipment_transaction_town_key, _equipment_transaction_home_key, _town_restore_weapon_key, _equipment_wield, _equipment_takeoff, _wield_weapon_key, _wield_digging_tool_key; S:_restore_mining_combat_hand_key | Exact intended item-to-slot effect; confirmed strip/restore obligations consumed once; Home moves use corresponding rows | R for fixed Home child | Final loadout confirmed, owned items released safely | confirmation-stall-bound, cursed-slot, item-missing, no-safe-restore | 8 per operation |
| Equipment inscriptions / teleport suppression / curse marking | T:_town_random_teleport_suppression_key, _observe_town_equipment_work; P:_heavy_curse_inscription_key | Named item acquires requested inscription; observed curse classification consumes one information obligation | R via Home take | Named suppression/mark confirmed | target-missing, inscription-unconfirmed, item-reserved | 8 |
| Stat restore / experience restore / gain | S:_stat_restore_quaff_key, _experience_potion_quaff_key; P:_stat_gain_quaff_key; C:_queue_home_stat_restore selector | Named drained stat restored, experience restored/increased, or intended stat rises | R via supply/Home child | Declared recovery/gain satisfied | no-source, ineffective-consumption, restoration-impossible | 8 |
| Cross-town shopping / Morivant full-identify / Outpost return | S:_cross_town_shopping_key; Q:_morivant_full_identify_key; T:_town_teleport_key, _town_teleport_dispatch_key, procurement Outpost-return branch; P:_telmora_q2_travel_key | Actual destination town, first target supplier result, full knowledge/acquisition; new tried-town flag alone earns nothing | R to fixed Inn/library; finite town itinerary | Root shortage resolved or all permitted destinations exhausted | fare-refused, travel-route-refused, candidate-towns-exhausted, supplier-work-exhausted | 8 per leg/operation; root inherits finite itinerary |
| Rumors / travel destination unlock | T:_town_special_key rumor branches | Named destination becomes selectable / Angband recall unlock observed | R to Inn | Required unlock observed | no-funds, rumor-reads-exhausted, unlock-unconfirmed | 3 per unresolved attempt; route 8 |
| Restock remedy | T:_town_restock_wait_key; S:_retry_after_store_restock, _released_restock_store_key | Independently observed relevant shelf turnover, once; turn advance alone does not reset | R for reinspection child | New shelf resolves shortage, or fixed retry itinerary exhausted | unchanged-stock, restock-remedy-exhausted | 8 own decisions; one turnover wait/reinspection per supplier revision |
| Fundraising / stockout mining dispatch | F:_fundraising_key; T:_supply_stockout_mining_key, _supply_stockout_mining_dispatch_key; P:_identify_staff_stockout_key, _recall_restock_key | Named kit acquisition, actual gold gain/vein exhaustion from finite run, return with required funds | R for fixed departure/return legs | Fixed funds/kit target achieved | no-safe-run, exhausted-run-plan, no-light, no-entrance | Town children 8; dungeon mining keeps MINING_STALL_LIMIT=150 |
| Recovery / eat / refill / town mob / wilderness survival | T:_town_special_key, _town_kill_mob_key, _town_clear_traveler_key; U:_mana_food_survival_override_key, _mana_food_floor_pickup_key, _wilderness_survival_key; combat/supply helpers | Relevant HP/MP/status/food/fuel improves, real hostile damage/kill or safe escape observed | R to shelter/hostile/town | Declared recovery/safety state attained | no-edible, no-safe-route, no-effective-attack, recovery-unconfirmed | 8 for town maintenance; genuine combat uses existing combat bounds |
| Quest accept / preparation / bounty / reward | Q:_fixed_quest_key, _opening_q34_town_key, _fixed_quest_building_key, _fixed_quest_reward_key, _prepare_return_candidate; T:_town_order_step4_key; P:_bounty_cashout_key | Engine quest status, reward/cashout inventory/gold or specified readiness changes | R to fixed office/building | Named quest phase/reward confirmed | reward-pack-full, quest-unavailable, route-unavailable, prerequisite-impossible | 3 for service; route/effect child 8 |
| Quest entry / exit / travel | Q:_fixed_quest_enter_key, _fixed_quest_exit_key; quest_navigator:enter_from_town; P:_telmora_q2_travel_key | Actual intended quest/floor/town reached | R with declared quest destination | Destination observation matches | equipment-entry-refused, route-unavailable, entry-unconfirmed | 8 |
| Departure / recall issue, confirmation, wait, cancellation | T:_town_special_key, _read_dungeon_recall_scroll_key, _dungeon_recall_confirmation_key, _town_cancel_unsafe_recall_key, _return_to_town_key, _return_route_key; P:_entrance_travel_key; policy_navigation:_descent_step | Recall activation/cancellation or intended floor arrival confirmed; wait child credits new game-turn high-water while visible `recalling` is true | R to actual entrance; wait uses visible turns, no hidden countdown | Intended safe destination / cancellation observed | departure-unsatisfiable, guardian-bounce-no-alternate, recall-unconfirmed, recall-delay-exhausted | 8 non-improving own decisions; total wait bounded by game's maximum activation delay as a versioned rule constant, never wall time |
| Town loot / exploration / look | I:_normal_loot_key, _loot_step; P:_current_floor_item_key, _look_probe_key, _town_idle_key; navigation helpers | Bound loot acquired; unique new relevant cells/landmarks observed, never mere position changes | R to fixed loot/frontier | Target acquired/observed or finite frontier exhausted | loot-blocked, no-frontier, no-actionable-claim-owner | 8 |
| Plan routing / blocked / detectors / fallback | T:_town_procurement_decision, _town_blocked_key; P:_town_holder_wait_key, _town_idle_key, detector rewrites | Only evidence from delegated row; visible closure is a terminal result, not reusable progress | Inherit actual child's R | Finite plan obligations closed | work-nonprogress, no-executable-step, work-contract, departure-unsatisfiable | 3 unresolved routing decisions; terminal proof closes immediately |
| Bookkeeping / character knowledge / prompt cleanup | P:_skill_exp_request_key, _periodic_game_save_key, _periodic_character_dump_key, _warning_prompt_response_key; C:_complete_character_dump | Matched knowledge payload, save/dump acknowledgement, named prompt cleared; cannot credit another errand | - | Specific acknowledgement observed | acknowledgement-missing, prompt-unclassified | 8 when awaiting evidence |

The need registry names `equipment-transaction` as well as `equipment-work`; both use the equipment
rows. `stat-restore`, `experience-restore` and `experience-restore-check` split acquire/use/browse
rather than share a gold delta. `identification-source` splits buy/withdraw/browse; all aliases and
supplier occurrences must map individually in slice 0. Purchase rung variants include legacy
lantern/oil/ration; mandatory supplies/destruction; mining digger/detection; normal/full identify;
per-stat/proactive restore; experience restoration; quest carry/speed/healing; tail
recall/mana-food/torch/teleport/cure/ammo/identify-staff; Black Market speed/healing/stone-to-mud;
normal/required/reserve curse and enchant. Destruction acquisition uses the supply-buy row and the
usable-ability predicate.

Shared dispatchers include T:_town_item_processing_key/_town_special_key,
S:_shop/_atomic_shop_transaction_key, H:_atomic_home_withdraw_key/
_atomic_home_deposit_key/_stage_home_operation, and equipment/Home executors. Pure
`_enumerate_town_needs`, `_build_town_errand_plan`, purchase and retention selectors receive no
independent progress credit. Generic dungeon combat, quest_navigator:_sweep/_exit/decide and mining
helpers appearing in the census need explicit town-context proof or a reviewed exclusion, not
invented town work.

Tombstones are inputs to EVERY selector/dispatcher above, including pure need, plan, purchase and
retention selectors, and specifically T:_town_procurement_progress_key,
T:_town_observed_purchase_is_composable, S:_next_purchase_unreserved and the T:1540-1575 detector
rewrite. A tombstoned `(store, target_identity)` is unavailable for the rest of the visit; shared
aliases and fresh claim/reason/target revisions cannot revive it. Persist root exhaustion across
cross-town legs. Recheck at rewrite and final admission: refuse a substitute targeting a tombstone,
record the refusal and retain the original proposal subject to its own admission/safety checks.
Never execute the refused replacement. Churn composition refusal closes the bound buy impossible
immediately; shelf affordability cannot override it. Select a different feasible remedy or stop a
mandatory unmet need; optional work skips. This is the row's generic contract.

Home relief uses a fixed candidate list from fresh catalogue/retention evidence: try sellable
surplus, then the cheapest safely unneeded item by known value (stable identity tie-break). Resolve
missing knowledge once under identification's bound; protect required/reserved/uncertain items.
Exhausted/protected candidates are not requeued. An unresolved posted effect gets bounded
settlement/cleanup, never a competing destruction. Only evidenced exhaustion of both remedies proves
impossible; a no-sellable label alone does not. Optional deposit is then skipped; mandatory deposit
with no independently admitted safe remedy stops visibly. Recall's snapshot exposes only `recalling:
bool` (model.py:359,1087): pin the game's maximum activation-delay rule and turn units in
implementation, starting at the confirmed activation observation. Repeated boards, reissue/cancel
and local plan rebuilds cannot renew the wait allowance. Delay exhaustion closes even if turns
advance.

Current arbiter budgets (`town_arbiter.py:_new_town_turn_arbiter`, starts at 624): router 8, buy 8,
sell 3, Home visit/scan 300, Home errand 3, equipment transaction 8, optimizer 8, identify 3, town
plan 3, fundraising 150, curse/enchant 8, cross-town 8, survival 8, departure 8, detectors 2, rumor
3, quest request 3, misc 3. Proposed Ns above replace family-wide vector resets and the 300-decision
Home stall allowance; they are design choices requiring replay qualification. Retain useful existing
stricter item/operation bounds; no bound is silently enlarged. Equipment comparisons retain
AGENTS.md depth gates, AC100 expected damage per player turn, and required abilities; weight is not
a loadout comparison criterion.

## Recorded failures and counterfactual closures

Evidence paths below are read-only backups, outside the worktree. Line numbers are one-based
physical JSONL rows. Captures are tails, not complete sessions; do not infer the whole reported
interval or execute old commands after divergence.

| Capture | Decision-log SHA-256 | Inspected extent |
| --- | --- | --- |
| `C:\hengband-backups\state-logs\home-full-nosurplus-20261005-2356\bot-decisions.jsonl` | `4e82197f76f636d0f6c757f78ad653894edf6c53ff2337dd8fc9e5a922e6da7e` | 8,518 rows, 21:36:36-23:58:08; final restart decisions 1-27 |
| `C:\hengband-backups\state-logs\crosstown-loop-20261006-0355\bot-decisions.jsonl` | `df3a4365f98e826a34bb6e7bb44b7e18c69d7e9e4927d4c398539994583f60d6` | 629 rows, 04:01:58-04:15:13, sequences 876-1504 |

(a) Rows 8507-8518, sequences 16-27, repeatedly emit `town:blocked:home-full-no-sellable-surplus`,
key `5`, position `(46,124)`. Turns advance 12692322 -> 12692441, but pack remains 20 used/3 free,
gold 9056, and no operation is posted. Arbiter progress is false throughout; top-level
`arbiter.remaining` is null. Claim 17 retires; later claim IDs
18-26 reappear already retired under the same blocked reason. Rows 8495-8505 already show the remedy
ladder: `atomic-withdraw:full-home-discard`, `full-skip:identified-item-protected`,
`identify:normal`, then `full-skip:identification-effect-unresolved`. The counterfactual pin treats
this deposit as optional (20/23 pack slots used, no evidenced mandatory space need): relief closes
impossible, is tombstoned, deposit skipped, next admitted work is departure or another errand,
subject to readiness gates. It must not stop on the optional deposit or repeat key `5`. Preserve
`home-full-no-sellable-surplus` as cause. Pin sale/destruction exhaustion and effect settlement as
well as that outcome; the unresolved-identification label is not itself proof. If capture state
cannot prove the exhaustion, use explicit constructed completion controls and label them as such.
Incomplete routing closes within 3 own decisions, without inventing proof.

(b) All 629 captured arbiter rows say progress=true; none says would-retire. 208
`continue-observed-shop` rows have fallback `shop:sell-rebuy-churn-defect` and no posted operation.
At sequence 880 the cross-town Reach goal is `(37,119)`, distance 13; 881 rewrites its step into a
detectors terminal, and 882 exits store 5 at `(38,106)`. Sequences 886-888 repeat that pattern.
Router sequences 883-885 and 889-891 start at distance 0, step away to 1, and return to the same
store. Reaching 0 again is not a new minimum. These are local steps, not observed arrivals in town
2; target/tried-town metadata cannot prove travel.

At sequence 880 the explicit composition refusal proves this bound buy cannot execute: close it
immediately, preserve the refusal, and prohibit its reacquisition. Alternatively, an evidence-only
N=8 root child initialized on the open store at 876 has no remaining entry milestone: count
sequences 876,878-884 (skip 877 bookkeeping) and close at 884. Fresh catalogue/shelf evidence, if
absent from the checkpoint, can earn one initial observation milestone and shift that bound once; it
cannot earn 208 resets. Freeze the cross-town route to `(37,119)`; the procurement rewrite must not
substitute a return to store 5. The record does not provide complete BFS ranks for every step, so
this bound is for the buy root, not a fabricated exact cross-town-distance simulation. There is one
real buy at 925 (store 6), with gold 25088 -> 16260 at 926; credit that separate target after
verifying its inventory effect. It cannot clear store 5's tombstone. This capture is not globally
effect-free. Separate implementation issue, staff-swap churn: the 10-03 decision wants
staff swaps to succeed; S:_identify_staff_swap_purchase (3631-3646) requires a strictly fuller staff
while this visit sold staffs then wanted 2x12 back (734G). Repair/qualify that transaction
separately; the 19,618G cross-town full-identify source must not become the only remedy merely
because the watcher closes churn.

Why the existing watchers missed these prefixes, at the inspected source base:

- CLI `_command_state_signature` includes turn, reason and key: advancing WAIT turns in (a), and
  alternating steps/pages in (b), prevent 12 identical signatures.
- `_cell_loop_guard_applies` excludes town altogether; store boards also clear `recent_cells`.
  `_update_navigation_progress` resets its dungeon invariant in town. These are explicit coverage
  exclusions, not insufficient wall time.
- Town residence stops at 1,500 decisions; (a)'s final restart has 27, (b)'s saved suffix has 629.
  It does not prove the full earlier session's count.
- The blocked fuse needs 30; (a) has 12 blocked decisions in the final restart. The named-block
  report's EXTENDED_STUCK_WINDOW cadence is a separate terminal path; the saved rows have no
  town_stall_report. (b) is relabeled rather than a named blocked streak. Both counters are broader
  than a three-decision failure.
- `_town_result_makes_progress` positively accepts several command shapes and postings, while
  `_town_procurement_decision` labels affordable observed shops `continue-observed-shop` without
  proving the operation can be composed. Its `_town_observed_purchase_is_composable` checks
  selection/quantity/reserve, not the later sell/rebuy refusal. Relabeling an Escape does not
  purchase anything.
- The arbiter compares whole per-family vectors, not strictly decreasing route minima or
  operation-specific effects. Store context, pending state, and plan fingerprints can change them.
  It sees rewritten producers as fresh budgets. (a) demonstrates retirement is recorded while a
  differently labeled block continues; (b) never reaches retirement at all. Log-only cannot fix
  either.
- The current log-only path calls `forgive_retirement`, clearing counters, and has a
  3-retirements/600-second exception. In (a), rows 8480/8484/8488 record three retirements within
  about 8 s and 8490 a restart: the old guard already stopped an earlier segment. It did not fire in
  the final restart's differently labeled blocks; (b) has no retirement. Slice 1 replaces the clock
  guard below. Cycle history/reset and early-rung scheduling still need full prefix analysis.

## Retirement migration, acceptance gate and issue #2

Slice 1 deletes `time.monotonic`/600 s retirement-window logic (cli.py:411-427). Keep log-only
forgiveness for legacy accounting until graduation, but it cannot clear semantic counters,
tombstones or the independent retirement-burst ledger. Count distinct transitions into retirement
(including internal retired events hidden by another reason), deduplicated by decision/event
identity. Settle fresh evidence before counting retirements in that decision. Repeated
`retired: true` polls count once. At the third retirement in the same town visit
without productive admitted work between, stop visibly with
`town:blocked:retirement-burst-no-progress`. Merely admitting/posting/refusing work, changing
owner/reason, or bookkeeping cannot reset the count. Only causal observed effect/distance progress
of admitted work resets it; new genuine visit starts a new ledger. Checkpoint it; restart/store
reopen/forgiveness cannot renew it. This independent watcher implements Q1(B), not automatic
owner-retired stopping.

Receipts include schema/observer version, activation row, epoch/root/child/kind, requester/operator,
target/revision, sequence, charged/unsuccessful count/N, route minimum before/after, evidence/source
sequence and target facts before/after, closure/cause, tombstone, selector/rewrite/admission
refusal, and burst-ledger events. Retain raw and rewritten reason/key. Unknown item evidence earns
no effect credit.

Graduation requires a versioned all-row/all-producer corpus with productive, impossible, no-effect,
preempted, executor-tail and duplicate-observation controls: zero unmapped admissions, double
credits, successful-work false closures or reopened tombstones; all no-effect cases close within N
own decisions. Pin (a)/(b) first closure/reacquisition refusal and productive relief/store-6
purchase controls. New-version successful-work qualification has zero owner-retired and zero unexplained
would_retire/retired flags; intentional dead work uses specific closures. Retain historical
retirement evidence. Unexpected retirement blocks graduation. Live criterion: K=20 consecutive
completed town visits across at least 3 dives on the qualification version, with zero
`town:blocked:owner-retired` and zero unexplained `would_retire`/retired in bot-decisions.jsonl;
persist visit/dive counts across restarts, no cherry-picking or time expiry. Any violation restarts
qualification. Live qualification needs separate authorization and remains pending in this task.
Only after offline AND live gates pass, remove log-only forgiveness/compatibility and its migration
burst ledger; restore owner-retired as a visible last-resort stop. Retain legacy parsing only as
explicit error/deprecation or a documented no-op that cannot disable stopping; update launch/config
documentation. No timer remains.

Issue #2: replay ALL recorded corpus fixtures with `--enforce-town-claims` ON before deleting OFF:
zero `ownership:*` stops and zero new blocked reasons versus approved fixture expectations
(intentional new watcher negative-control closures must be pinned explicitly, never silently
accepted as ON regressions). Currently CLI defaults OFF and `_town_claim_bar_enforced` initializes
false. Remove operational OFF branches including P:5810-5830 `preserve_home_hold` exceptions and
`token_would_admit` deferred-list observe-only fallthrough; retain useful diagnostics without
permitting execution. Make ownership unconditional, keep compatible ON syntax, and pin
constructor/CLI/checkpoint/nested/driver paths. Single-seam coverage is unconditional from slice 0;
issue #2 graduation cannot bypass readiness/depth gates.

## Migration slices (implementation caps <=150k tokens each)

These are future implementation/validation budgets, not tests run in this task. Each slice ends at a
reviewable commit with receipts; every activated row requires ALL producers mapped and observer/pins
qualified. New pins/modules below are planned.

| Slice / cap | Live behaviour change and complete row scope | Required pins / validation | Risks |
| --- | --- | --- | --- |
| 0 / 60k | Enumerate/certify every site; work-record validator refuses unmapped town sends; effect accounting remains shadow/legacy | Generated manifest, town_structure_lint, ownership_claim_lint; test_town_structure_lint, test_policy_structure, test_ownership_s2b1_ladder; corpus + (a)/(b) zero unmapped receipts; new driver override/prompt/tail no-send controls | Census exclusions need town-context proof; driver must share the seam |
| 1 / 100k | Persist/deduplicate semantic work and shadow observers; delete 600 s window; 3 no-progress retirements/visit now stop visibly | test_ownership_claims, test_town_producer_purity_part1-6, test_town_emit_ownership_recorded, test_town_acquire_bypass_recorded; new 2/3-retirement, productive reset, no-effect admission, hidden-retirement, restart, preemption and finite-tail controls | Reconstructed baselines earn no credit; forgiveness must not reset independent state |
| 2 / 150k FIRST LIVE ROWS: (b) | Activate all four buy rows, sales, sale-address, browse, store approach/exit, cross-town shopping and plan-routing rows; land their effect observers, finite milestones and route high-water; churn closes impossible immediately; selector/rewrite tombstones refuse store-5 reacquisition and original cross-town proposal survives | New (b) raw/provenance pin incl sequence 880; test_policy_town, test_town_restock_trajectory, test_town_blackmarket_stall_recorded, test_town_cure_supplier_recorded, test_buy_deposit_loop_recorded, test_town_loot_store_20260926_recorded, test_town_approach_retired_recorded, test_q2travel_progress_recorded; no-effect/merge/staff/route-detour/own-exit controls | Must include every buy alias and shared dispatcher; no fabricated inventory or BFS proof; separate staff-swap issue |
| 3 / 150k NEXT LIVE ROWS: (a) | Activate Home catalogue/deposit/withdraw/errand/relief/disposal, destruction/overflow and normal/full identification rows; sell -> cheapest safe destruction -> impossible; optional deposit skipped and another errand/departure admitted; mandatory unresolved remedy stops | New (a) final-restart/exhaustion/next-work pin; test_home_relief_progress_recorded, test_town_home_candidate_stall_recorded, test_town_overflow_recorded; NEW test_home_equip_enter_leave_loop_recorded (existing extractor only); empty/duplicate catalogue, protected/uncertain cheapest, partial stacks, productive relief and in-flight-tail controls | Catalogue/identification must settle protection before destruction; old relief fixture has reconstructed owner, not checkpoint proof |
| 4 / 130k | Activate equipment optimization/transaction/inscriptions, device processing, curse and enchant rows; exact effects close operations, safe restoration retains obligations | Equipment transaction/mutation/calibration and identification suites; test_equipment_swap_loop_incident; equip-alternation/home-route, failed-device/consumed-scroll and restoration pins | Strip/restore cannot discard owned gear or uncertain effects; retain AGENTS.md loadout gates |
| 5 / 140k | Activate stat recovery, rumors, restock, fundraising, survival, quest service/entry, recall/departure, loot/exploration and bookkeeping rows; visible-turn recall wait gets finite game-rule allowance; all rows now live | Quest/travel/recall/survival/fundraising suites; test_newchar_town_wander_recorded, test_unaffordable_claim_tour_recorded, test_town_plan_exhausted_wander; NEW test_town_loot_supplier_alternation_recorded (existing extractor only); recall true/false, duplicate-turn/max-delay and every-row negative pins | No hidden recall countdown, unsafe descent or unbounded rumor/restock wait; reconcile entire activation ledger |
| 6 / 80k | Unify blocked/cycle diagnostics; after ON replay and offline/live graduation gates, delete operational OFF and log-only paths and restore retirement stop; generic watcher already live since slice 2 | test_town_progress_invariant, test_town_stall, test_cli_town_claim_switch, test_town_arbiter/suppression; all-kind ON corpus, driver no-send and K=20/3-dives receipts | Until authorized live evidence exists graduation stays pending; stop timing/claim IDs change |

Extract immutable pins with hashes, physical rows and boundary/checkpoint provenance. Replay
prefixes only until the first changed command; later captured-observation observer tests/constructed
responses are not full historical replays. Pending implementation gates: full manifest/runtime
certification, item/town-state proof, cycle-prefix analysis, versioned recall rule and N
qualification. No code, game/BOT, tests or push are authorized by this document revision.
