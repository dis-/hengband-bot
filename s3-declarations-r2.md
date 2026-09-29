# S3.3 producer declarations, round 2

This is a record-only change. The legacy claim reader and emitted keys remain authoritative. The audit below distinguishes an actual producer-written execution step from a family or reason inferred at claim exit. An offer binds only when its key and producer match the final claim.

## STEP 1: producer return audit

| Family | Sites inspected | Declared for every admitted return? |
| --- | --- | --- |
| home-visit | `policy_home.py` atomic Home compose/tail, direct Home-page `_home_deposit_key`; Home entry/leave in `policy_shop.py` | **Partial**. Atomic paths and direct page deposit declare. Other direct Home-page leave, withdrawal queue and no-step returns do not. |
| home-errand | Home request/withdraw and `policy_shop.py` Home page | **No**. Some atomic Home operations declare under their operation executor; filed request and other returns lack a next step. |
| home-scan | Home knowledge request and observed catalogue | **No**. A knowledge goal exists, but not all request/await/no-step returns write an execution declaration. |
| shop-buy / shop-sell | `policy_shop.py` one-shot, direct store actions, leave | **Partial**. One-shot composition offers a step; direct and no-step paths remain. |
| store-router | `policy_town.py` generic entrance travel, `policy_shop.py` store travel and page router | **Partial**. Generic route and store travel offer steps; router no-step and entry/leave paths remain. |
| equipment-opt | `policy_equipment.py` optimizer and town installation | **No**. An installed transaction has a new first-action offer, but optimizer returns are not fully declared. |
| equipment-txn | `policy.py` session installation, `policy_equipment.py` prepared action, Home operation | **Partial**. Installation and prepared action offer steps; other session exits/None returns remain. |
| calibration | `policy_calibration.py` strip, capture, restore scan, restore and deposit handoff | **Partial**. Strip, capture and restore scan offer steps; deposit/request handoff and no-step exits remain. |
| identification | Town device/equipment identification, Home source request | **No**. No complete producer return declaration. |
| curse-enchant | Town curse removal and enchant | **No**. No complete producer return declaration. |
| cross-town | Town routing and procurement | **No**. No complete producer return declaration. |
| rumor | Town rumor visit | **No**. No complete producer return declaration. |
| departure | Town departure, dungeon stair/return | **Partial**. Navigation stair offers a step, but departure and return paths do not all declare. |
| fundraising | Town and dungeon `_fundraising_key` and floor exit | **No**. The purpose ledger is separate; not every claim return declares its execution step. |
| bookkeeping | Periodic skill, save and character dump | **No**. No complete producer return declaration. |
| survival / town:kill-mob | `_town_kill_mob_key` | **No**. No complete producer return declaration. |

The remaining undeclared admitted paths are the **Partial** and **No** rows above. Zero undeclared paths has not been achieved. In particular, a generic declaration synthesized at claim exit would misstate producer intent and would not be a sound substitute for the missing producer writes. The new transport refusal transition retains the exact work ID and claim, records `posting-refused`, and leaves the state `acting` with `transport.resolve-refusal`; it never records `awaiting` for that rejected key. Other uncertain-send paths still need an explicit transport outcome audit.

## STEP 2: replay harness

`scripts/first_divergence_s3_3.py` now returns `declaration_mismatch_counts` grouped by `(family, inferred, declared)`, `missing_declaration_decisions`, `missing_declaration_by_family`, and `declaration_decisions_measured`. S3.3 and cross-area runs also include the full OFF counts in `off_declarations`. ON counts cover the reached prefix through first divergence. No full fixture was run in this round.

## STEP 3: Home torch diagnosis only

The withdrawal need is produced by `policy_shop.py:1647-1694` and `policy_supply.py:714-766`: Home-first purchase examines a torch class, obtains a current Home candidate, and computes the missing amount from quest carry, supply, or torch stock targets. The candidate filter at `policy_home.py:3415-3432` reads the current Home catalogue, deferred signatures, class, count and torch fuel. The selected Home operation at `policy_home.py:1308-1430` reads the queued signature and fresh catalogue address. At 23:45:50 and 23:52:19 the selection was `home-pending-item`, catalogue page 0 letter `n`, five 2500-turn torches.

The competing deposit predicate is `policy_home.py:967-1086` for overload, then `policy_home.py:2758-2810` and `_home_deposit_candidate` at `:1088-1209` for ordinary surplus. These read actual pack weight versus the strength-based limit, the inventory stack, retention surplus, pending/deferred identities, calibration state and whether the item is protected by another owner. Retention at `policy_home.py:649-785` can reserve zero torches when `_matching_ammo` exists; `_retention_surplus` at `:925-928` then permits the whole stack to be shed. The deposit producer chooses count from this surplus (or all during calibration). This predicate is separate from the shop's torch shortage/quest target.

In the 23:46 capture, decision 7666 withdrew five torches into a pack stack of ten; decision 7668 immediately deposited all 15 with `dh15` under `home:weight-overload-deposit`. In the 23:53 capture, decision 2178 withdrew five into an empty pack torch stack; decision 2180 deposited all five with `dk5` under `home:atomic-deposit`. Both captures later stopped at `town:blocked:home-withdraw-failed-stock-present` after the usable Home torch signatures were deferred. The first stop's Home gate reports three class matches, two deferred signatures and one fuel-zero torch; the second reports the same counts. This is the **same contradictory-predicate class** as the food and armour cases: one producer's need admits work that another producer immediately reverses on substantially unchanged facts. It is a different pair of predicates and a different resource. No Home selection policy was changed in this round.

## Verification

The focused declaration pins passed (9 tests), and the single source-revert check made the direct Home page pin fail as intended. The harness counting pin passed (1 test), and `tests.test_test_fakery_lint` passed (13 tests). A whole `tests.test_policy_calibration` run was stopped after it became slow; it is not claimed as passed. Full fixtures and gate scripts were not run under the prompt's do-not-run list.

Commits: `2a7e5399` (STEP 1 partial producer writes), `ef060639` (STEP 2 harness). This report is the STEP 3 diagnosis commit.

{"topic":"declarations-r2","implementer":"gpt-6-sol","status":"partial","record_only":true,"zero_undeclared":false,"step3_fix":false,"full_fixtures_run":false,"commits":["2a7e5399","ef060639"]}
