# tpstockout: evidence contradicts stock-out premise

## Step 1 — correction

The actual Alchemist page in `autorecover-20261002-023427-loop-detected.bot-state-fixed.jsonl.gz`
at turn 2570072 contains these exported items, printed by the evidence test:

| Letter | Name | Count | Price |
| --- | --- | --- | --- |
| e | テレポートの巻物 | 99 | 61 |
| f | テレポートの巻物 {25%引き} | 4 | 46 |

Decision 1068 at that turn buys Recall (`pg2\r\r\x1b`) and leaves. The later
02:35:56 decision 37 at turn 2571984 has Teleport 4/15, gold 10903 and only
`teleport_ready` false; it emits `town:blocked:no-actionable-claim-owner` (`5`),
followed by decision 38 `probe` (`8`). The missing 11 Teleports cost 611 gold
on the last recorded shelf. No supplied later Alchemist page proves stock-out.
The stopped selector reports `no-store-page-observed`, not an empty shelf.

Commit 30bf754e incorrectly accepted the prompt's stock-out description.
This report supersedes that claim. No production modification is retained.

## Code and conjunct table at ace34cd2

`policy_town.py:2690` registers attempted supply stores again if remembered
stock is affordable. At :1304 the progress invariant asks for procurement;
:1319 emits `no-actionable-claim-owner` if no producer composes despite live
claims. Recall mining starts at `policy.py:14586`; Identify mining is offered
at `policy_town.py:5299`. A fresh frozen seam with the actual shelf memory
chooses `shop:travel`, not stock-out mining. Full restart/route-state
reconstruction is needed to diagnose the live stocked supplier's missing owner.

| Conjunct | Supplier | Base empty-shelf mining |
| --- | --- | --- |
| recall_departure_ready | Temple / Alchemist | Recall-specific starter |
| identify_staff_ready | Home / Magic; Black availability veto | Identify-specific starter |
| teleport_ready | Alchemist / known Home stock | No generic remedy |
| cure_critical_ready | Temple / Alchemist / known Home stock | No generic remedy |
| food_ready | General; Magic for mana eaters; known Home stock | No generic remedy |
| light_ready (light/oil) | General / known Home stock | No generic remedy |

The supply mapping is `policy_constants.py`'s `SUPPLY_STORES`, consumed by
`policy_supply.py:116`; other supplier mappings are `policy_town.py:3895`.
HP/MP/status, pack/weight, equipment/calibration and pending transactions
are not empty-shelf supplies. Quest carries have separate rules at :2720.

## Exact decision required

D17 says **MINE ON STOCK-OUT**. Step 2 requires a mining acceptance pin on
these recordings, whose last actual supplier is stocked and affordable.
Making that pin pass as stock-out would contradict the evidence and R3/R4.
The inherited prompt says to stop when design contradicts WHAT to build.

Decide between fixing the **stocked-supplier procurement/owner failure** shown
here and providing the intended **actual empty-shelf recording** for the
generic mining remedy. No fabricated empty shelf, changed EXPECTED_FIRST,
weakened requirement, live interaction or other worktree write was used.

## Validation

`tests.test_tpstockout_recorded`: 1 evidence test passed.
`tests.test_test_fakery_lint`: 13 tests passed. This is substrate
verification, not the requested behavior acceptance pin. No completed fix,
fail-before/pass-after mining result or single revert check is claimed.

Assertion audit before each commit, base ace34cd2, verbatim:

```
No changed pre-existing assertions or forbidden test edits.
```

Changed pre-existing assertions: [].

For Claude: DO NOT RUN `scripts/test_parallel_runner.py`,
`scripts/test_timing_runner.py`, `scripts/hunk_guard.py`,
`scripts/verify_scope.py`, `scripts/mutation_battery.py`, `tests.test_cli`,
`tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`,
long tour/town/overweight replays, town producer purity parts, full-fixture
`scripts/first_divergence_s3_3.py`, full-suite/gate runners or all-matching sweeps.
Stuck/withdraw OFF+S3.3 are the explicit exception.

Explicit stockout/restock module list: `tests.test_recall_stockout_set_end_recorded`,
`tests.test_recall_stockout_surplus_pins`, `tests.test_town_restock_trajectory`.
Implementation checks were not run because no production fix remains.

{"topic":"tpstockout","implementer":"gpt-6.1-sol","status":"blocked-evidence-contradiction","base":"ace34cd2","step1_commit":"30bf754e","production_fix":false,"tests":{"tests.test_tpstockout_recorded":1,"tests.test_test_fakery_lint":13},"revert_check":"not-run-no-production-fix","changed_preexisting_assertions":[],"assertion_audit":"No changed pre-existing assertions or forbidden test edits.","blockers":["Recorded Alchemist has 99+4 affordable Teleports. Decide stocked-supplier owner fix versus actual empty-shelf capture."]}
