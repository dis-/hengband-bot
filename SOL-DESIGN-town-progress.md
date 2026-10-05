# Town progress: observed effects, persistent work, bounded decisions

Design only; source base `4d864cb3`, branch `town-progress-design-1006`, 2026-10-06.
Status: budget-limited draft. Investigation stopped at the requested 120k-token ceiling.
The work-kind table covers the inspected registry and additional town execution paths.
The complete producer/call-site reconciliation is **not certified**; slice 0 must finish it.
No production/test changes, game/bot execution, test runs, or push accompany this document.

## Decisions and scope

User decision, 2026-10-05 (translated): "Town errand retirement
(town:blocked:owner-retired) only records, does not stop the bot, until fixed.
In parallel, rebuild the definition of progress for ALL kinds of town work
(buy, sell, Home catalogue, deposit, withdraw, equipment change, remove curse,
identify, Home-full relief, etc.): list what observed event counts as progress
for each, rebuild the counting, and switch back to stopping once retirement
no longer appears on the records. Truly non-progressing repetition is stopped
by the other watchers (loop detection, town progress check)."

The 2026-10-04 decision requires enumerating every call site and routing it
through one entrance. Implement the registry and observer first; do not grow
a collection of reason-specific incident patches. Retirement remains log-only
during migration; new non-progress/impossible outcomes are independent watcher
outcomes and must not be swallowed by that compatibility mode.

## Code-derived inventory and evidence boundary

Enumeration used here: read `claim_ladder.py:_RUNGS` (lines 227-370), enumerate
`@claims` decorators with Python AST, read `_town_need_registry` (policy_town.py:
3145-3236), `_purchase_rungs` (policy_shop.py:2345-2445), and the exact baseline
`scripts/town_producer_baseline.json`. The baseline has 652 entries: 498 pure
helpers, 99 town-producer candidates, 44 delegated adapters, 11 dungeon-only.
Those are baseline classifications, not 99 proven town-only producers.
`town_structure_lint.py:producer_census` follows imports, aliases, callbacks,
return dependencies and reachability from `choose_key`; it conservatively
includes dungeon paths. Reading its algorithm is not proof of census closure.

For implementation, generate a call-site manifest from that census, union it
with ladder producers, decorated producers, need/purchase registries, direct
`choose_key` branches, post-decision rewrites, and driver prompt continuations.
Each entry must name caller/line, callee, possible town context, table row,
admission entrance, effect observer, and delegation. Account for all 44
adapters; a selector is not an independently successful work operation.
Fail the coverage gate for unmapped candidates; justify dungeon-only paths
from predicates. Do not accept a blanket module exclusion or a baseline label
as a proof. Future additions must fail the same gate until reviewed.

Source abbreviations below are files in `src/hengbot`: T=policy_town.py,
H=policy_home.py, S=policy_shop.py, E=policy_equipment.py,
I=policy_identification.py, P=policy.py, Q=policy_quest.py,
F=policy_fundraising.py, C=policy_calibration.py, U=policy_supply.py,
IS=policy_instore.py. Function names identify stable references at this base.

## One admission and observation rule

Use a semantic work record, separate from a reason string or transient claim ID:
`(town_visit_epoch, root_work_id, kind, target_identity, target_revision)`.
Store UI openings are child attempts, not new town visits. A genuine town
change creates a new residence epoch; an unfinished cross-town purpose retains
its root record and exhausted-target set through travel. An incidental floor
transition, restart, reason rewrite, or plan rebuild cannot renew that purpose.
Checkpoint the record; absent old checkpoint evidence, mark reconstructed state
and use the first observed board as baseline without crediting it as progress.

All town producers, nested calls and rewrites pass through `_town_producer_entry`
and one final admission/emit seam. Admission names the root, child, concrete
target, expected observation, route metric and N before offering a command.
Checked item operations, staged tails, in-store operations and prompt answers
inherit that record. A detector that substitutes work must either continue the
same admitted work or close it visibly before admitting a different one.
Keep requester, operator and observer separately; accounting follows the work,
not `owner_for_reason` of the rewritten label.

**Generic rule:** after N of this work's own decisions with neither a new
observed effect nor distance progress, close it with a visible reason and
tombstone its stop for the rest of the town visit. Never re-acquire that stop
in the same visit. A proven impossibility closes immediately, before N.
For cross-town roots, the same prohibition survives their travel legs until
the purpose is resolved. Other independently feasible work may continue;
an unresolved mandatory prerequisite with no admitted remedy stops the bot.
An optional failure skips only that work. A typed contract/ownership defect
stops visibly regardless of whether the original errand was optional.

Count one admitted policy decision, including a selected no-step/refusal or
await, once by decision sequence. Include zero-energy decisions. Polls and
duplicate observations spend nothing; prompt segments of one decision are not
extra decisions. Charge delegations to their root and child exactly once each.
Unrelated bookkeeping or genuine safety preemption freezes the work's counter;
it does not reset it. Work resumed after preemption retains counters and bounds.
At each decision first settle the previous command against fresh observations,
then increment if no qualifying evidence appeared. Baseline creation earns
zero credit. Close on the Nth unsuccessful decision, before issuing N+1.
Do not exempt all observation waits or introduce elapsed-time guards.

Effect credit requires the named target's changed facts on a fresh, causally
matched observation. A posted key, released tail, expectation, new claim,
executor phase/index, changed reason, gold spending, store open/close, or plan
index is not a business effect. Log proof even when a transport child completes.
A response may settle several claims but earns one evidence credit per work.
New shelf/catalogue evidence counts once per target revision; identical refreshes
and invalidating/revalidating one's own cache earn nothing.

Distance progress is a new **minimum observed** legal route rank for the same
target and route revision, preferably BFS remaining edges. An expected next
step or any changed distance is insufficient. Returning from rank 1 to 0 after
already reaching 0 earns nothing. Freeze target selection during the leg;
route revisions require observed topology change, not another selector result.
Unreachable routes close visibly. Native travel can advance many edges in one
decision; straight-line distance must not reject a genuine BFS detour.

Finite child milestones (arrival, entry, page/address acquisition, exit) can
complete transport children once. Their evidence does not repeatedly reset a
purchase/relief root. Keep the root's target obligations and consumed milestones
through every reopen. A composite uses a fixed finite obligation list; observed
completion removes obligations. Reversible buy/deposit, strip/restore, or
withdraw/redeposit cycles cannot replenish that list. Revised requirements need
an external observed cause and explicit old-work closure; local toggles cannot
erase a tombstone. A required blocked root must name a finite remedy or stop.

Proposed new reasons: `town:work-closed:done:<kind>`,
`town:work-closed:impossible:<kind>:<cause>`,
`town:blocked:work-nonprogress:<kind>:<target>`, and
`town:blocked:work-contract:<cause>`. Preserve existing specific visible causes
as aliases. Terminal/impossible declarations are resolved immediately, never
represented as another repeatable WAIT task. A safely required UI exit is a
separate bounded cleanup child; preserve the original failure and tombstone.
Never discard a posted operation's uncertain effect to open a competing visit.

## Work-kind table

This is the proposed contract, not a description of today's vector accounting.
N is unsuccessful own decisions per named child, inherited by its semantic
work; successful finite obligations allow long productive batches. `R` means
the observed route rule above, `-` means no distance credit. Causes in the
impossible column are visible closure causes, including proposed new causes.
Shared selectors/dispatchers are listed after the table; their callers inherit
the row selected. Source NeedSpec departure-blocking status remains authoritative.

| Work / registry categories | Producers | Observed effect = progress | Distance | Done | Impossible / visible cause | N |
| --- | --- | --- | --- | --- | --- | --- |
| Ordinary supply buy: birth-supplies; recall, teleport, cure-critical, oil, food, light, identify-staff | S:_shop_core, _atomic_shop_transaction_key; IS:_in_store_emit | Bound ware quantity/usable charges increases in pack, matched payment and shelf effect where available | R to supplier | Required carried target reached | stock-absent, unaffordable, pack-full, operation-unconfirmed | 8 |
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
| Home-full relief / retry deposits | H:_home_full_relief_key, _home_full_skip_key, _home_full_identify_carried_key | Confirmed shelf take followed by safe sale/destruction earns a relief slot; carried-only disposal earns pack space, not Home space | R for fixed child; finite scan/take/disposal obligations | Required slots freed; original deposit handed back to its owner | home-full-no-sellable-surplus, surplus-withdraw-failed, item-protected, store-unreachable | 3 for stalled orchestration; child operation uses its row N |
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
| Departure / recall issue, confirmation, countdown, cancellation | T:_town_special_key, _read_dungeon_recall_scroll_key, _dungeon_recall_confirmation_key, _town_cancel_unsafe_recall_key, _return_to_town_key, _return_route_key; P:_entrance_travel_key; policy_navigation:_descent_step | Recall activation/cancellation or intended floor arrival confirmed; countdown decrease is a finite observation child | R to actual entrance; countdown high-water decrease | Intended safe destination / cancellation observed | departure-unsatisfiable, guardian-bounce-no-alternate, recall-unconfirmed | 8 non-improving own decisions; retain game's bounded activation-turn allowance, never wall time |
| Town loot / exploration / look | I:_normal_loot_key, _loot_step; P:_current_floor_item_key, _look_probe_key, _town_idle_key; navigation helpers | Bound loot acquired; unique new relevant cells/landmarks observed, never mere position changes | R to fixed loot/frontier | Target acquired/observed or finite frontier exhausted | loot-blocked, no-frontier, no-actionable-claim-owner | 8 |
| Plan routing / blocked / detectors / fallback | T:_town_procurement_decision, _town_blocked_key; P:_town_holder_wait_key, _town_idle_key, detector rewrites | Only evidence from delegated row; visible closure is a terminal result, not reusable progress | Inherit actual child's R | Finite plan obligations closed | work-nonprogress, no-executable-step, work-contract, departure-unsatisfiable | 3 unresolved routing decisions; terminal proof closes immediately |
| Bookkeeping / character knowledge / prompt cleanup | P:_skill_exp_request_key, _periodic_game_save_key, _periodic_character_dump_key, _warning_prompt_response_key; C:_complete_character_dump | Matched knowledge payload, save/dump acknowledgement, named prompt cleared; cannot credit another errand | - | Specific acknowledgement observed | acknowledgement-missing, prompt-unclassified | 8 when awaiting evidence |

The need registry names `equipment-transaction` as well as `equipment-work`;
both use the equipment rows. `stat-restore`, `experience-restore` and
`experience-restore-check` split acquire/use/browse rather than share a gold delta.
`identification-source` splits buy/withdraw/browse; all aliases and supplier
occurrences must map individually in slice 0. Purchase rung variants include
legacy lantern/oil/ration; mandatory supplies/destruction; mining digger/detection;
normal/full identify; per-stat/proactive restore; experience restoration;
quest carry/speed/healing; tail recall/mana-food/torch/teleport/cure/ammo/identify-staff;
Black Market speed/healing/stone-to-mud; normal/required/reserve curse and enchant.
Destruction acquisition uses the supply-buy row and the usable-ability predicate.

Shared dispatchers include T:_town_item_processing_key/_town_special_key,
S:_shop/_atomic_shop_transaction_key, H:_atomic_home_withdraw_key/
_atomic_home_deposit_key/_stage_home_operation, and equipment/Home executors.
Pure `_enumerate_town_needs`, `_build_town_errand_plan`, purchase and retention
selectors receive no independent progress credit. Generic dungeon combat,
quest_navigator:_sweep/_exit/decide and mining helpers appearing in the census
need explicit town-context proof or a reviewed exclusion, not invented town work.

Current arbiter budgets (`town_arbiter.py:_new_town_turn_arbiter`, 625-647):
router 8, buy 8, sell 3, Home visit/scan 300, Home errand 3, equipment transaction
8, optimizer 8, identify 3, town plan 3, fundraising 150, curse/enchant 8,
cross-town 8, survival 8, departure 8, detectors 2, rumor 3, quest request 3,
misc 3. Proposed Ns above replace family-wide vector resets and the 300-decision
Home stall allowance; they are design choices requiring replay qualification.
Retain useful existing stricter item/operation bounds; no bound is silently enlarged.
Equipment comparisons retain AGENTS.md depth gates, AC100 expected damage per
player turn, and required abilities; weight is not a loadout comparison criterion.

## Recorded failures and counterfactual closures

Evidence paths below are read-only backups, outside the worktree. Line numbers
are one-based physical JSONL rows. Captures are tails, not complete sessions;
do not infer the whole reported interval or execute old commands after divergence.

| Capture | Decision-log SHA-256 | Inspected extent |
| --- | --- | --- |
| `C:\hengband-backups\state-logs\home-full-nosurplus-20261005-2356\bot-decisions.jsonl` | `4e82197f76f636d0f6c757f78ad653894edf6c53ff2337dd8fc9e5a922e6da7e` | 8,518 rows, 21:36:36-23:58:08; final restart decisions 1-27 |
| `C:\hengband-backups\state-logs\crosstown-loop-20261006-0355\bot-decisions.jsonl` | `df3a4365f98e826a34bb6e7bb44b7e18c69d7e9e4927d4c398539994583f60d6` | 629 rows, 04:01:58-04:15:13, sequences 876-1504 |

(a) Rows 8507-8518, sequences 16-27, repeatedly emit
`town:blocked:home-full-no-sellable-surplus`, key `5`, position `(46,124)`.
Turns advance 12692322 -> 12692441, but pack remains 20 used/3 free, gold 9056,
and no operation is posted. Arbiter progress is false throughout: remaining
2,1,0 at sequences 16,17,18, then repeated would-retire=true. Claim 17 retires;
later claim IDs 18-26 reappear already retired under the same blocked reason.
The visible no-candidate proof closes relief at sequence 16 immediately.
If the proof is incomplete, a three-decision unresolved-routing child closes
by sequence 18. Neither the stale store visit nor a new claim ID re-arms it.
Preserve `home-full-no-sellable-surplus` as cause, tombstone relief, and stop if
the pending mandatory deposit has no independently admitted safe remedy.

(b) All 629 captured arbiter rows say progress=true; none says would-retire.
208 `continue-observed-shop` rows have fallback `shop:sell-rebuy-churn-defect`
and no posted operation. At sequence 880 the cross-town Reach goal is `(37,119)`,
distance 13; 881 rewrites its step into a detectors terminal, and 882 exits
store 5 at `(38,106)`. Sequences 886-888 repeat that pattern. Router sequences
883-885 and 889-891 start at distance 0, step away to 1, and return to the same
store. Reaching 0 again is not a new minimum. These are local steps, not
observed arrivals in town 2; target/tried-town metadata cannot prove travel.

At 876/879 the churn refusal already proves this bound buy cannot execute:
close it immediately, preserve the refusal, and prohibit its reacquisition.
Alternatively, an evidence-only N=8 root child initialized on the open store
at 876 has no remaining entry milestone: count sequences 876,878-884 (skip
877 bookkeeping) and close at 884. Fresh catalogue/shelf evidence, if absent
from the checkpoint, can earn one initial observation milestone and shift that
bound once; it cannot earn 208 resets. Freeze the cross-town route to `(37,119)`;
the procurement rewrite must not substitute a return to store 5. The record
does not provide complete BFS ranks for every step, so this bound is for the
buy root, not a fabricated exact cross-town-distance simulation.
There is one real buy at 925 (store 6), with gold 25088 -> 16260 at 926;
credit that separate target after verifying its inventory effect. It cannot
clear store 5's tombstone. This capture is not globally effect-free.

Why the existing watchers missed these prefixes, at the inspected source base:

- CLI `_command_state_signature` includes turn, reason and key: advancing WAIT
  turns in (a), and alternating steps/pages in (b), prevent 12 identical signatures.
- `_cell_loop_guard_applies` excludes town altogether; store boards also clear
  `recent_cells`. `_update_navigation_progress` resets its dungeon invariant
  in town. These are explicit coverage exclusions, not insufficient wall time.
- Town residence stops at 1,500 decisions; (a)'s final restart has 27, (b)'s
  saved suffix has 629. It does not prove the full earlier session's count.
- The blocked fuse needs 30; (a) has 12 blocked decisions in the final restart.
  The named-block report's EXTENDED_STUCK_WINDOW cadence is a separate terminal
  path; the saved rows have no town_stall_report. (b) is relabeled rather than
  a named blocked streak. Both counters are broader than a three-decision failure.
- `_town_result_makes_progress` positively accepts several command shapes and
  postings, while `_town_procurement_decision` labels affordable observed shops
  `continue-observed-shop` without proving the operation can be composed. Its
  `_town_observed_purchase_is_composable` checks selection/quantity/reserve,
  not the later sell/rebuy refusal. Relabeling an Escape does not purchase anything.
- The arbiter compares whole per-family vectors, not strictly decreasing route
  minima or operation-specific effects. Store context, pending state, and plan
  fingerprints can change them. It sees rewritten producers as fresh budgets.
  (a) demonstrates retirement is recorded while a differently labeled block
  continues; (b) never reaches retirement at all. Log-only cannot fix either.
- The current log-only path additionally calls `forgive_retirement`, clearing
  counters/recurrences, and has a 3-retirements/600-second exception. This time
  guard conflicts with the quoted decision and is not the proposed solution.
  Do not claim it ran in these captures: (a) emits another block label, (b) no
  retirement. Town cycle signature limits and early-rung scheduling need full
  replay to establish their exact missed trigger; that analysis remains pending.

## Recorded acceptance gate and issue #2

Add observer receipts: schema/version, epoch/root/child/work kind, requester/
operator, target/revision, sequence, charged decision count, unsuccessful count,
N, metric/high-water before/after, evidence event/source sequence, before/after
target facts, close status/cause, tombstone and admission refusal. Retain raw
proposed reason/key and rewritten reason/key. Unknown evidence fails closed;
do not manufacture progress from unavailable aggregate inventory details.

Before reverting log-only, pin a finite versioned qualification corpus covering
every table kind and producer mapping: productive, impossible, no-effect and
interleaved/preempted trajectories. Measure zero unmapped admissions, zero
double credits, zero successful-work false closures, zero reopened tombstones,
and every no-effect case closed within its declared N own decisions. For (a)/(b),
pin first closure and the proposed re-acquisition refusal. Prove safety/restore
work and long productive Home batches finish without unjustified retirement.
Archived historical retirement rows remain evidence; do not delete them to
meet the criterion. New-version successful qualification records must contain
zero `town:blocked:owner-retired` and zero unexplained would-retire/retired flags.
Intentional dead-work negative controls must produce the new specific closure,
not depend on retirement. Any unexpected retirement blocks graduation.

Only after those receipts pass, remove the log-only reset/exception path and
restore owner-retired as a visible last-resort stop. Retain legacy flag parsing
only as an explicit deprecation/error or documented no-op that cannot disable
the stop; update launch/config documentation in the implementation slice.
No automatic expiry, no timer, no "zero retirements" inference from short runs.
Live qualification requires separate authorization; this design task provides
no permission to launch the bot. Until live evidence is available, report that
gate as pending rather than declaring a universal absence of retirements.

Issue #2 (`--enforce-town-claims` always ON) is complementary: ownership decides
who may execute; progress decides what evidence renews its budget. Current CLI
default is off and policy `_town_claim_bar_enforced` initializes false. Make the
single entrance/observer invariant unconditional; retain the flag as compatible
ON syntax and eliminate the operational OFF path after mapping qualification.
Offline shadow comparisons may remain available as diagnostics. Test constructor,
CLI, restored checkpoints and nested/driver continuations so no path accidentally
reverts to off. Always-ON alone does not repair progress=true on an empty visit.
Neither setting may bypass depth/readiness gates to escape a failed town errand.

## Migration slices, each below approximately 150k implementation tokens

Budgets below are planning caps, not evidence that tests passed; no tests were
run for this document. Stop each slice at a reviewable commit with replay receipts.

| Slice / cap | Concrete scope | Required tests and pins | Replay risks |
| --- | --- | --- | --- |
| 0 / 50k | Finish generated call-site manifest and reconcile every need/purchase variant, decorator, adapter and direct branch; close pending cycle analysis | town_structure_lint, ownership_claim_lint; test_town_structure_lint, test_policy_structure, test_ownership_s2b1_ladder; manifest coverage pins | Conservative census includes dungeon/helpers; exclusions must not hide town paths |
| 1 / 90k | Versioned work record, single admission/observation seam, decision deduplication, persistence, attribution and shadow receipts | test_ownership_claims, test_town_producer_purity_part1-6, test_town_emit_ownership_recorded, test_town_acquire_bypass_recorded; generated call-site coverage; preemption/duplicate-board controls | Old pickles lack root/evidence state; reconstructed baselines cannot claim historical success |
| 2 / 100k | Strict route high-water, finite entry/exit/shelf milestones; bind cross-town purpose and rewrites; block exhausted reacquisition | New (b) raw-line/provenance pin; test_town_approach_retired_recorded, test_q2travel_progress_recorded, test_reward_approach_progress, test_quest_building_approach_progress, test_quest_enter_approach_progress | Legitimate detours/native multi-edge travel must remain productive; detector reason and command trajectories change |
| 3 / 110k | Buy/sell/inscription effect observers; shared legacy atomic/in-store evidence; stable target obligations; enforce impossible closures | test_policy_town, test_town_restock_trajectory, test_town_blackmarket_stall_recorded, test_town_cure_supplier_recorded, test_buy_deposit_loop_recorded, test_town_loot_store_20260926_recorded; no-payment/no-pack-effect controls | Batch stack merges, staff exchanges, reservations and home-first gates; aggregate logs alone cannot prove quantities |
| 4 / 120k | Home scan/take/deposit/disposal/relief observers; immediate visible no-surplus proof; equipment-owned item handoffs | New (a) final restart pin; test_home_relief_progress_recorded, test_home_equip_enter_leave_loop_recorded, test_town_home_candidate_stall_recorded, test_town_overflow_recorded; scan duplicates/empty Home/partial stacks | Existing relief pin has reconstructed owner state, not a checkpoint replay; productive slot relief must not retire; protected items stay protected |
| 5 / 120k | Equipment/calibration/identify/curse/enchant observers; exact item effects and safe restoration; optional failure closure | Equipment transaction/mutation/calibration and identification suites; test_equipment_swap_loop_incident; equip-alternation/home-route fixtures; failed-device/consumed-scroll controls | Strip/restore is non-discardable; uncertain effects must not release owned gear; no weight-based loadout comparison |
| 6 / 100k | Remaining quest/bounty/rumor/fundraising/recovery/loot/exploration/departure/bookkeeping paths; reconcile all manifest entries | Quest/travel/recall/survival/fundraising suites; test_newchar_town_wander_recorded, test_unaffordable_claim_tour_recorded, test_town_plan_exhausted_wander, test_town_loot_supplier_alternation_recorded; all table-row negative controls | Rumor randomness, recall countdown, quest prerequisites and safe stockout remedies; no forced unsafe descent |
| 7 / 70k | Activate generic watcher after complete coverage; unify blocked/cycle diagnostics around receipts; graduate always-ON and restore retirement stop after qualification | test_town_progress_invariant, test_town_stall, test_cli_town_claim_switch, test_town_arbiter/suppression; versioned all-kind corpus and driver no-send terminal pins | Recorded expected reasons/claim IDs and stop timing change; old incident snapshots are not observations of changed commands |

Extract minimal immutable evidence in later implementation work with hashes,
source physical rows and boundary/checkpoint provenance. Prefixes before changed
commands may be replayed; after first changed command use captured-observation
observer tests or explicitly constructed response controls. Never describe those
as a full historical replay. Keep productive relief and the store-6 purchase
as positive controls beside the two dead-loop controls.

Open work at budget stop: certify exhaustive call-site-to-row mapping; inspect
full state-tail item effects and town IDs; establish town-cycle history/reset
behavior for both incidents; qualify proposed N values across the complete
recorded corpus. These are implementation/design completion gates, not hidden
claims of validation already performed.
