# tpstockout: stocked supplier owner failure (CORRECTION applied)

Continued from ed59a8eb on tpstockout. Work is confined to this worktree;
recorder-owned jsonlog and other worktrees are read-only. The original
empty-shelf premise is superseded by the 2026-10-02 02:55 CORRECTION:
"Do NOT build the generic empty-shelf mining remedy now."

## Step 1: cause and reconstruction

The failure is a truncated need registry, not an empty Alchemist.
`policy_supply.py:162-175` prepends Home to a supply's supplier list when Home
contains that supply. `policy_town.py:2693-2715` correctly creates both Home
and affordable remembered-shop candidates even after an attempted visit.
But the old `_town_need_registry` allocated only one teleport lookup.
`_TownNeedLookup.lookup` at `policy_town.py:36-39` selects a candidate by
occurrence, so the only lookup resolves to Home. Alchemist never becomes a
live teleport producer. `policy_town.py:1087-1124` subsequently refuses its
counterfactual purchase: its selected ware is teleport, but no departure
family for that shop is registered. The progress seam at :1304/:1319 (base
line numbers) has claims but no purchase owner and replaces stuck wandering
with WAIT. Probe movement then alternates with that WAIT.

`policy_shop.py:2096` reports `no-store-page-observed` because the current
outside snapshot has no store; it does not assert empty inventory on a
remembered shelf. Re-registration at base `policy_town.py:2690` cannot cure
loss in the following finite-occurrence registry projection.

Preserved route evidence: `tests/fixtures/tpstockout-routes-20261002.json.gz`
contains verbatim decision rows from all three captures, with source hashes.
`tests/fixtures/tpstockout-20261002.json.gz` remains unchanged and preserves
the actual board, shelf, Home/skill knowledge, calibration and stop telemetry.

| Capture | Recorded process/route facts |
| --- | --- |
| 02:17:28 | Retained rows start at sequence 5637, not process start. Final 5814 at turn 2553976 is `town:blocked:route-nonprogress:quest-request`, with an unposted store-5 approach. This is a different stop, not evidence of an empty Alchemist or the later teleport failure. |
| 02:34:27 | Retained rows start at 910. At 1068/2570072, Alchemist buys Recall with `pg2\r\r\x1b`; the shelf has 99 Teleports at 61 gold and 4 discounted Teleports at 46. At 1069 its plan has lost Alchemist; 1129/2570681 blocks with only `teleport_ready` false and a Home-only plan. |
| 02:35:56 | Fresh sequence 1/2570692 scans Home, 2 travels to Home, 3/2571133 exits `home:route-claim-unfulfilled`, 4 travels to Weapon, 5/2571460 observes/leaves, 6 travels to Black, 7/2571679 observes/leaves. No Alchemist route is registered. 8 selects the unsafe-recall fallback. At 9 the blocked/probe cycle starts; 37/2571984 blocks and 38 probes. |

All startup stderr records say `enforce_town_claims=False` and
`enforce_crossarea_fundraising=True`. The restarted route ledger at sequence
37 has Home visits 2, Weapon 1, Black 1, Home unsatisfied passes 2, no blocked
stores, live claims teleport/equipment-catalog, and only teleport readiness
false. Target and alternate are Forest (7), optimization depth 20, Home
knowledge current and Home equipment scan complete. Gold is 10903,
Teleport 4/15; 11 missing scrolls are affordable (611 gold on the recorded
mixed-price shelf). A fresh process rebuilding from remembered Home stock
hits the same registry truncation even without a remembered Alchemist page;
with the remembered page, the invariant's purchase composer also fails.

The fixture is not a serialized policy checkpoint. The acceptance attachment
reconstructs the recorded route, ledger, alternate, shelf and knowledge facts
on a freshly primed policy, with an explicit committed-expedition latch.
It does not claim to reproduce missing lifetime state before the retained
02:17/02:34 windows. R4: stop at the first different key; later historical
boards are never interpreted as effects of the changed travel command.

## Conjunct table

| Conjunct | Town supplies | Lookup defect when Home holds stock | Empty-shelf mining in base |
| --- | --- | --- | --- |
| recall_departure_ready | Home + Temple + Alchemist | 2 slots hide the third supplier | Recall-specific remedy |
| teleport_ready | Home + Alchemist | 1 slot hides Alchemist | No generic remedy |
| cure_critical_ready | Home + Temple + Alchemist | 2 slots hide the third supplier | No generic remedy |
| food_ready | Home + General (Magic for mana eaters) | 2 slots already cover both | No generic remedy |
| light_ready / oil | Home + General for oil; light has its own selection | 1 oil slot hides General | No generic remedy |
| identify_staff_ready | Home / Magic, with Black availability veto | Separate identify capacity and routing | Identify-specific remedy |

HP/MP/status, pack/weight, equipment/calibration, quest carries and pending
operations are separate owners, not ordinary empty-shelf supply conjuncts.
The fix adds lookup coverage, without lowering any requirement or inventing
a mining action. D17 "survival reserves may be spent; replenish in town;
MINE ON STOCK-OUT" remains intact: these stocked boards replenish in town.
Class C's "remedy ... offered and genuinely failed" now permits the stocked
supplier's remedy to actually be produced.

## Step 2: fix and completed verification

Reserve lookup coverage for Home plus every ordinary supplier: Recall 3,
Teleport 2, Critical Cure 3, Oil 2; Food remains 2. Preserve an already
selected Home batch's continuation before the invariant tries another shop.
No new runtime attribute, threshold, UI classifier or departure gate.

Initial failure before: the new public `choose_key` acceptance pin returns
`5`, `town:blocked:no-actionable-claim-owner`, both fresh and checkpoint
restored. With lookup coverage it returns `\x1b`n%.`, `shop:travel`, store 4.
Printed source mapping: `model.py:335` says `STORE_ALCHEMIST = 4`;
`policy_constants.py:74` says
`TOWN_TRAVEL_STORE_SYMBOLS = ("!", '"', "#", "$", "%", "&", "'", "(")`.
The pin asserts travel, not an unobserved future purchase result.

One module per Python process; explicit requested list only:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_tpstockout_restart_recorded | 2 | pass; fresh + checkpoint public entry |
| tests.test_tpstockout_recorded | 1 | pass; original shelf evidence unchanged |
| tests.test_identify_staff_live27_recorded | 1 | pass; first divergence remains 104, mining plan 1 |
| tests.test_classC_departure_remedies | 5 | pass |
| tests.test_classC2_departure_recorded | 9 | pass |
| tests.test_live36_weight | 7 | pass |
| tests.test_town_progress_invariant | 22 | pass |
| tests.test_recall_stockout_set_end_recorded | 5 | pass |
| tests.test_recall_stockout_surplus_pins | 8 | pass |
| tests.test_town_restock_trajectory | 21 | pass |
| tests.test_test_fakery_lint | 13 | pass |

Total: 94 tests. Explicit stockout/restock module list is the two tpstockout
modules plus the two recall_stockout modules and town_restock_trajectory above.
No discovery/all-matching sweep was run.

The first live27 run exposed an early divergence at 35: a pending Home batch
handoff was redirected to the newly registered supplier. The fix preserves
that selected batch before trying another shop; the unchanged pin then
reproduces the prefix to 104 and chooses the intended one-run mining action.
The initial lint run found UTF-8 BOMs in newly created Python files; removing
the BOMs made all 13 lint tests pass without changing lint expectations.

Single final production-file revert check against ed59a8eb: new module exits
1 with six failing subcases (four missing supplier lookups, fresh blocked,
restored blocked). Both public-entry cases print the actual recorded
`5 / town:blocked:no-actionable-claim-owner`. After restoring the final code,
the same module passes, both printing `\x1b`n%. / shop:travel`.

Explicitly authorized stuck/withdraw runs of first_divergence_s3_3.py:

| Case/mode | Rows | OFF hash / designed first divergence | Result |
| --- | ---: | --- | --- |
| stuck/off | 4 | c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | matching |
| stuck/s33 | 4 | none | trajectory_defect null |
| withdraw/off | 34 | a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | matching |
| withdraw/s33 | 4 | index 3, sequence 3, ESC / equipment-transaction:catalogue-leave-for-scan | trajectory_defect null |

Step-1 commit: bce3c16a. Implementation commit is recorded below after git
creates it. The original evidence/assertions and EXPECTED_FIRST are unchanged.
No live game/bot interaction, generic mining remedy, publishing or other
worktree write was performed.

For Claude, DO NOT RUN: `scripts/test_parallel_runner.py`,
`scripts/test_timing_runner.py`, `scripts/hunk_guard.py`,
`scripts/verify_scope.py`, `scripts/mutation_battery.py`, `tests.test_cli`,
`tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`,
long tour/town/overweight replays, town producer purity parts, full-fixture
`scripts/first_divergence_s3_3.py`, full-suite/gate runners or all-matching
sweeps. Explicit exception: stuck/withdraw OFF+S3.3.

Assertion audit before step-1 commit, base ed59a8eb, verbatim:

```
No changed pre-existing assertions or forbidden test edits.
```

Changed pre-existing assertions: []. EXPECTED_FIRST is unchanged.

Assertion audit before step-2 commit, base ed59a8eb, verbatim:

```
No changed pre-existing assertions or forbidden test edits.
```
