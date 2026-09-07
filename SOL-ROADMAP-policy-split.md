# SOL-ROADMAP-policy-split.md

Split roadmap for `src/hengbot/policy.py` (38,239 lines / 1.67 MB).
Drafted 2026-09-06. Status: **APPROVED (user 2026-09-06, decisions in §9); Phases 0-2 landed.**

Execution model: **sol implements one phase per commit; Claude reviews each phase before the next
is dispatched.** Phases are strictly sequential (single-writer discipline). No phase may begin while
the previous one is unreviewed.

---

## 0. Measured baseline

All numbers below come from AST analysis of the current working tree
(`ast.parse` over `policy.py`, `tests/test_policy.py`, `scripts/mutation_battery.py`), not estimates.

| Quantity | Measured |
| --- | ---: |
| `policy.py` total lines | 38,239 |
| module-level region (before `class HengbotPolicy`) | 1,367 lines |
| `class HengbotPolicy(TownArbiterMixin)` span | lines 1368–38,235 (36,868) |
| methods on `HengbotPolicy` | 790 |
| total method LOC | 36,033 |
| distinct `self.<attr>` names written anywhere | 549 |
| module-level constants | 260 |
| module-level functions/classes outside `HengbotPolicy` | 8 |
| `tests/test_policy.py` | 61,405 lines, 102 top-level test classes |

Three methods are the spine and **never move**:

| Method | LOC | Role |
| --- | ---: | --- |
| `_decide` | 1,475 | the decision ladder; calls into every cluster |
| `__init__` | 1,042 | seeds all 549 state attributes |
| `prime` | 121 | pre-run seeding |

`__init__` is the sole exclusive writer of 136 attributes and a shared writer of 413 more. It is
the reason no cluster can own its state: every attribute is born in one constructor.

---

## 1. Cluster map (measured)

Clusters were derived by regex classification over method names, then validated against the
call graph and the `self._x` read/write sets. `out`/`in` are cross-cluster `self.<method>()` call
edges. `ownW` counts attributes written **only** by that cluster (excluding `__init__`, which writes
everything); `shW` counts attributes it shares with at least one other cluster.

| # | Cluster | Target module | LOC | Methods | ownW | shW | out | in |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | quest | `policy_quest.py` | 4,312 | 94 | 16 | 32 | 160 | 122 |
| 2 | town | `policy_town.py` | 4,263 | 82 | 12 | 53 | 329 | 146 |
| 3 | shop_store | `policy_shop.py` | 4,114 | 72 | 9 | 58 | 230 | 108 |
| 4 | combat_danger | `policy_combat.py` | 3,518 | 85 | 20 | 21 | 134 | 118 |
| 5 | equipment | `policy_equipment.py` | 2,967 | 84 | 19 | 38 | 87 | 160 |
| 6 | input_compose | (stays / partly reassigned) | 2,930 | 28 | 31 | 97 | 103 | 63 |
| 7 | **core** (`_decide`/`__init__`/`prime`) | **stays in `policy.py`** | 2,638 | 3 | 136 | 413 | 184 | 1 |
| 8 | navigation | `policy_navigation.py` | 2,596 | 79 | 25 | 36 | 88 | 242 |
| 9 | home | `policy_home.py` | 2,419 | 65 | 7 | 49 | 128 | 122 |
| 10 | consumables/supply | `policy_supply.py` | 1,576 | 77 | 6 | 12 | 80 | 252 |
| 11 | mining/fundraise | `policy_fundraising.py` | 1,165 | 35 | 2 | 27 | 63 | 69 |
| 12 | identification/loot | `policy_identification.py` | 1,153 | 29 | 1 | 17 | 48 | 55 |
| 13 | snapshot_parse (`_observe`) | `policy_observation.py` | 989 | 7 | 39 | 133 | 24 | 17 |
| 14 | calibration | `policy_calibration.py` | 798 | 20 | 10 | 14 | 21 | 20 |
| 15 | misc helpers | `policy_helpers.py` | 382 | 25 | 2 | 3 | 9 | 192 |
| 16 | procurement / telemetry / checkpoint stubs | folded into neighbours | 213 | 5 | 0 | 0 | 9 | 10 |

### Method-name prefixes per cluster (use these verbatim in fixer prompts)

- **quest** — `_quest_execute*` (1,097), `_fixed_quest*` (572), `_evaluate_fixed*` (254),
  `_quest_carry*` (207), `_morivant_home*` (179), `_unique_combat*` (149), `_morivant_full*` (118),
  `_opening_q34*` (115), `_quest_strategy*` (109), `_derived_home*` (102), `_kill_quest*` (84),
  `_guardian_fight*` (77), `_q31_opening*` (77), `_request_priority*` (70).
  **Plus manual reassignments** (the classifier files these elsewhere by name, but they are quest
  strategy code): `_q2_phase_key` (724), `_q2_encounter*` (32), `_q2_ranged*` (117),
  `_q2_breach_key` (81) — ≈954 extra lines.
- **town** — `_town_need*` (740, incl. `_town_need_candidates` at 601), `_town_special*` (374),
  `_town_procurement*` (202), `_town_blocked*` (197), `_return_to*` (170), `_town_terminal*` (148),
  `_town_item*` (142), `_cross_town*` (140), `_report_town*` (121), `_town_result*` (117),
  `_town_arbiter*` (111), `_town_departure*` (97), `_break_town*` (95), `_should_start*` (95).
- **shop_store** — `_shop` (842), `_next_required*` (427), `_next_purchase*` (361),
  `_shopping_approach*` (314), `_batch_sell*` (162), `_atomic_shop*` (115), `_store_sell*` (112),
  `_purchase_has*` (105), `_record_shop*` (99), `_evaluate_purchase*` (97), `_restore_mining*` (86),
  `_purchase_quantity*` (75), `_enumerate_live*` (73).
- **combat_danger** — `_emergency_item` (420), `threat_prediction` (244), `_breeder_breakthrough*`
  (179), `_melee_swarm*` (164), `_ranged_attack*` (156), `_update_combat*` (153),
  `_choke_engagement*` (146), `_forbid_wait*` (121), `_hunt_step*` (106), `_flee_sustain*` (92),
  `_ranged_scroll*` (77), `_refresh_paralyzer*` (71), `_is_descent*` (70).
- **equipment** — `_prepare_equipment*` (664, incl. `_prepare_equipment_optimization` at 650),
  `_equipment_transaction*` (382), `_equipment_optimization*` (232), `_abandon_blocked*` (159),
  `_wield_digging*` (110), `_home_rearm*` (101), `_equipment_departure*` (80), `_town_restore*` (79),
  `_is_disposable*` (75), `_town_equipped*` (53), `_equipment_slot*` (49), `_launcher_enchant*` (45),
  `_find_weapon*` (43), `_town_enchant*` (39).
- **navigation** — `_descent_step*` (191), `_step_toward` (151), `_break_positional*` (143),
  `_explore_step*` (98), `_window_edge*` (82), `_disengage_move*` (81), `_global_frontier*` (80),
  `_build_grid*` (78), `_navigation_livelock*` (76), `_dark_locomotion*` (68), `_plan_explore*` (65),
  `_descent_is*` (63), `_dungeon_entry*` (62).
- **home** — `_atomic_home*` (477, incl. `_atomic_home_withdraw_key` at 321 and
  `_atomic_home_deposit_key` at 156), `_retention_reservation*` (271), `_home_deposit*` (161),
  `_find_home*` (150), `_overweight_home*` (115), `_record_home*` (109), `_prepare_home*` (90),
  `_home_disposal*` (90), `_queue_home*` (84), `_bind_catalogued*` (63), `_confirm_home*` (55),
  `_has_actionable*` (49), `_home_dominated*` (48), `_observe_withdrawal*` (43).
- **consumables/supply** — `_mana_food*` (170), `procurement_requirements` (140),
  `_supply_ledger` (98), `_unseen_retreat*` (94), `_find_surplus*` (76), `_survival_gate*` (65),
  `_nearest_goal*` (63), `_find_edible` (48), `_carry_procurement*` (45), `_count_mana*` (43),
  `_procurement_missing*` (42), `_wilderness_survival*` (42), `_light_refill*` (34),
  `_identify_staff*` (34).
- **mining/fundraise** — `_fundraising_key` (402), `_leave_fundraising*` (92), `_mining_closure*`
  (83), `_dig_reachable*` (57), `_dig_to*` (49), `_mining_tapped*` (42), `_secret_wall*` (38),
  `_fundraising_kit*` (34), `_affordable_star*` (29), `_record_mining*` (29), `_tunnel_step*` (28),
  `_mining_sweep*` (28), `_mining_tunnel*` (27), `_update_mining*` (25).
- **identification/loot** — `_chest_processing*` (265), `_full_pack*` (79), `_find_identification*`
  (68), `_normal_loot*` (68), `_probe_unknown*` (64), `_identification_source*` (60), `_loot_step`
  (59), `_pack_pressure*` (52), `_carried_identify*` (50), `_identification_need*` (47),
  `_identification_deadlock*` (47), `_outstanding_identification*` (41), `_loot_state` (36),
  `_bind_identification*` (31).
- **calibration** — `_calibration_redress*` (211), `_calibration_observe` (135),
  `_calibration_town*` (96), `_install_calibration*` (76), `_legacy_calibration*` (52),
  `_calibration_entry*` (46), `_calibration_restore*` (34), `_capture_character*` (28),
  `_abort_character*` (27), `_validated_character*` (24), `_restore_calibration*` (24),
  `_begin_character*` (15), `_calibration_preconditions*` (10), `_calibration_removable*` (8),
  `_persist_calibration_redress_obligation` (22).
- **snapshot_parse** — `_observe` (832), `_resolve_observed*` (63), `observe_character_snapshot`
  (28), `_refresh_warning*` (27), `_strategy_force*` (20), `_current_pinned*` (10),
  `_missing_required*` (9).
- **misc helpers** — `_pick_alternate_dungeon` (65), `_transaction_retain_identities` (51),
  `_refuse_no_progress_cycle` (47), `_is_disposable_item` (40), `_periodic_filler_is_safe` (36),
  `_find_disposable_item` (21), `consume_look` (18), `_has_destruction_method` (11),
  `_profile_resistance_name` (10), plus 16 small predicates.

### Load-bearing tangles (late phases only)

The attribute-sharing hubs, measured by how many non-core clusters write them:

| Attribute | Writing clusters |
| --- | --- |
| `last_reason` | 14 (every cluster) |
| `_returning_to_town` | 8 |
| `_home_pending_item` | 8 |
| `_home_candidate_waiting` | 8 |
| `_town_blocked_reason` | 7 |
| `_equipment_optimization_signature` | 7 |
| `_identification_need` | 6 |
| `_home_pending_slot` | 6 |
| `_fundraising_mode` | 6 |
| `_equipment_optimization_preparation` | 6 |
| `_town_travel_state` / `_town_travel_fallback` / `_town_errand_plan` | 5 each |
| `_home_atomic_withdraw_pending` / `_home_pending_quantity` / `_identification_candidate` | 5 each |

These identify the three tangles the roadmap deliberately schedules **last**:

1. **Town procurement / retention / keep-set** — `_town_need_candidates` (601 lines) plus the
   `_home_pending_*` family shared across 8 clusters.
2. **Equipment transaction session** — `_equipment_optimization_signature` /
   `_equipment_optimization_preparation` written by 6–7 clusters including `calibration`,
   `snapshot_parse` and `input_compose`.
3. **Arbiter interplay** — `TownArbiterMixin` already owns `_store_visit` behind a property; the
   `_town_travel_*`, `_store_entry_wait_*` and `_town_restock_*` families straddle
   `town`/`shop_store`/`navigation`/`input_compose`/`snapshot_parse`.

---

## 2. Chosen pattern: **mixin classes, composed into `HengbotPolicy`**

```python
# src/hengbot/policy.py
from .policy_calibration import CalibrationMixin
from .policy_identification import IdentificationMixin
...
class HengbotPolicy(
    CalibrationMixin,
    IdentificationMixin,
    ...,
    TownArbiterMixin,
):
    def __init__(self, ...): ...   # unchanged, still seeds all 549 attributes
    def _decide(self, ...): ...    # unchanged
```

Each `policy_<x>.py` contains exactly one `class <X>Mixin:` with no `__init__`, no base class, and
no state of its own. Methods are cut and pasted verbatim, with only import-line adjustments.
Future phases must import shared constants from `policy_constants.py`; they must not duplicate
constant definitions in a mixin module.

### Why mixins, not delegate objects — the pickle argument

**The checkpoint payload is a plain attribute dict, not the policy object.**
`latch_onset_capture.checkpoint()` (line 38) does:

```python
state = {name: value for name, value in vars(policy).items()
         if name not in _CAPTURE_STATE_NAMES}
return base64.b64encode(pickle.dumps(state, protocol=5)).decode("ascii")
```

and `restore_checkpoint()` (line 48) does `policy_type.__new__(policy_type)` followed by
`restored.__dict__.update(pickle.loads(...))`.

Consequences, in order of force:

1. **Class layout is not in the payload.** Nothing about the method table, the MRO, or which module
   a method lives in is serialized. Moving methods to mixins changes zero checkpoint bytes.
2. **Attribute names are the entire contract.** `restore_checkpoint` writes names straight into
   `__dict__`. Mixins keep every attribute on the one `HengbotPolicy` instance, so the contract is
   untouched. Delegates would move attributes onto sub-objects, and `__dict__.update` would then
   resurrect the old names as dead siblings of the live delegate state — a silent, replay-invisible
   corruption.
3. **`home_entry_capture.STATE_FIELDS` is 30 `getattr(policy, name)` reads** (lines 22–52, consumed
   at line 81). With mixins these keep resolving. With delegates each of the 30 would need a proxy
   property, and `_home_owned()` (lines 84–96) reads nine more attributes by `getattr` on top.
4. **`policy.py` defines no `__getstate__`, `__setstate__` or `__reduce__`.** Pickling is the
   default `vars()` path. A delegate split would eventually need one of those hooks, and adding one
   is itself a checkpoint-format change.
5. **No cluster owns its state.** Measured best case is `snapshot_parse` at 39 exclusive vs 133
   shared attributes; `town` is 12 vs 53, `shop_store` 9 vs 58, `home` 7 vs 49. There is no clean
   partition to delegate to. A delegate split would need hundreds of proxy properties.

### The existing delegates prove the cost, not the case

Two extracted modules already use the delegate shape and both paid for it:

- `town_arbiter.TownArbiterMixin` (town_arbiter.py:348–380) is itself a **mixin**, and the one piece
  of state it did relocate — `_store_visit` moving into `_town_turn_arbiter` — required a
  property/setter pair plus a `_store_visit_before_arbiter` `__dict__` migration shim that is still
  in the tree. That is the per-attribute price. We have 549 attributes.
- `restore_checkpoint` already carries 12+ `setdefault` upgrade hooks and two value-normalization
  blocks (`_town_blocked_reason_value`, `_cross_decision_latches`) accumulated from past state
  changes. Every delegate move would add another.

`equipment_optimizer.py`, `warrior_optimization.py`, `monster_ranged_evaluator.py` and
`equipment_transaction_planner.py` are pure-function/value modules — they take arguments and return
results, and hold no policy state. That is the other legitimate extraction shape, and it is what a
later, separately-approved refactor could aim at. It is **out of scope** for this roadmap, which is
behavior-preserving moves only.

### Pickle caveat that IS real: module-level classes

Instances of classes defined at module level in `policy.py` **are** pickled by reference
(`hengbot.policy.<Name>`). Four are stored on policy attributes:

- `ExplorationGoalKind` (line 1315), `ExplorationPathOutcome` (1321),
  `ExplorationGoalIdentity` (1329), `ProcurementHomeGate` (1335)

`_explore_goal_identity` and `_explore_path_outcome` are live written attributes, so old checkpoints
contain `hengbot.policy.ExplorationGoalIdentity` references. **If any phase moves these four, it
must leave a re-export alias in `policy.py`** so `pickle.loads` on an existing checkpoint still
resolves. The recommendation is simpler: **do not move them at all.** They are 19 lines total.

---

## 3. Phase list

Each numbered phase is exactly one sol commit. Every phase carries the same gate (§4) plus the
phase-specific modules named in its row.

Ordering rationale: with mixins the *mechanical* risk of a move is constant (it is a cut-and-paste
into a class body with no base class), so the ordering is driven by **test separability** and
**blast radius on review**, not by call-graph coupling. Phases 1–5 are the state-light, cleanly
tested clusters (a combined `ownW/shW` ratio far better than average and self-contained test
classes). Phases 9–12 are the three tangles named in §1.

### Phase 0 — preparation (no `policy.py` change)

- Record fresh baselines: `tests/replay_key_equality.py equip-swap` and `no-actionable`
  (400 / 300 decisions), `scripts/decision_equivalence.py`, one clean
  `scripts/test_parallel_runner.py` run. Save the outputs as the phase-comparison reference.
- **Fix two already-stale mutation anchors.** `scripts/mutation_battery.py:480`
  (`drop-evaporated-home-claim-charge`) and `:620` (`route-only-addressed-digger-withdrawal`) have
  `text.count(edit.old) == 0` against the current `policy.py` — they are broken *before* the split
  and would otherwise be blamed on it. Retarget or retire them.
- Add two guard tests to `tests/test_policy_structure.py` (new file):
  1. **No mixin method-name collisions** — assert that the mixin classes composed into
     `HengbotPolicy` have pairwise-disjoint method-name sets, so no phase can silently shadow a
     method through the MRO.
  2. **Checkpoint round-trip identity** — `checkpoint(p)` then `restore_checkpoint(HengbotPolicy, s)`
     yields an identical `vars()` dict, run against a fixture policy that has been driven through
     the equip-swap capture.
- Expected delta: `policy.py` +0. New file ≈ 80 lines.

### Phase 1 — calibration → `src/hengbot/policy_calibration.py`

- Move: `_calibration_*`, `_install_calibration*`, `_legacy_calibration*`, `_restore_calibration*`,
  `_capture_character*`, `_abort_character*`, `_validated_character*`, `_begin_character*`,
  `_persist_calibration_redress_obligation`. 20 methods.
- Class name: `CalibrationMixin`.
- Expected delta: `policy.py` −798, new module +830.
- Focused modules for the gate: `tests.test_policy_calibration`, `tests.test_policy`.
- Test split: move `CharacterCalibrationPhaseTest` (1,471 lines) → `tests/test_policy_calibration.py`.
  No external importers.
- Mutation anchors to retarget: **none** (no `replacement("policy.py", ...)` anchor lands in this
  cluster).

### Phase 2 — identification / loot / chest → `src/hengbot/policy_identification.py`

- Move: `_chest_*`, `_loot_*`, `_full_pack*`, `_probe_unknown*`, `_identification_*`,
  `_find_identification*`, `_normal_loot*`, `_pack_pressure*`, `_carried_identify*`,
  `_outstanding_identification*`, `_bind_identification*`. 29 methods.
- Class name: `IdentificationMixin`.
- Expected delta: `policy.py` −1,153, new module +1,190.
- Test split: `PickupTest` (461), `ChestProcessingTest` (379), `IdentifyPurchaseBatchingTest` (190)
  → `tests/test_policy_identification.py`. No external importers.
- Mutation anchors: none.

### Phase 3 — mining / fundraising → `src/hengbot/policy_fundraising.py`

- Move: `_fundraising_*`, `_mining_*`, `_leave_fundraising*`, `_dig_reachable*`, `_dig_to*`,
  `_secret_wall*`, `_tunnel_step*`, `_affordable_star*`, `_record_mining*`, `_update_mining*`.
  35 methods.
- Class name: `FundraisingMixin`.
- Expected delta: `policy.py` −1,165, new module +1,200.
- Test split: `FundraisingStuckEscapeTest` (853), `MiningReachableTreasureClosureTest` (376),
  `IdleItemDepositTest` (191) → `tests/test_policy_fundraising.py`. No external importers.
- Mutation anchors: none.
- Landmine: `mining-light-mandatory` is a LOCKED user rule. This phase must not touch any light
  precondition, only relocate it.

### Phase 4 — consumables / supply / survival → `src/hengbot/policy_supply.py`

- Move: `_mana_food*`, `procurement_requirements`, `_procurement_*`, `_supply_ledger*`,
  `_unseen_retreat*`, `_unseen_*`, `_find_surplus*`, `_survival_gate*`, `_nearest_goal*`,
  `_find_edible`, `_carry_procurement*`, `_count_mana*`, `_wilderness_survival*`, `_light_refill*`,
  `_identify_staff*`, `_light_ready`, `_owns_usable_permanent_light`, `_expedition_light_ready`.
  77 methods.
- Class name: `SupplyMixin`.
- Expected delta: `policy.py` −1,576, new module +1,620.
- Test split: `HiddenInfoFallbackTest` (697), `QuestCarryVisitAbandonmentTest` (691),
  `IdentifyStaffTest` (675), `ShoppingTest` (661), `WieldLightTest` (554),
  `SupplyLedgerInvariantTest` (216), `TownRestockTest` (96), `DeepKitTest` (69), `StatGainTest` (37)
  → `tests/test_policy_supply.py`. No external importers.
- Mutation anchors to retarget: `mutation_battery.py:135` (`_mana_food_survival_override_key`).
- Landmines: the Zombie MANA food rule and the LOCKED fuel-0 torch decision both live here. Verbatim
  move only.

### Phase 5 — navigation / exploration / descent → `src/hengbot/policy_navigation.py`

- Move: `_descent_*`, `_step_toward`, `_break_positional*`, `_explore_*`, `_window_edge*`,
  `_disengage_move*`, `_global_frontier*`, `_build_grid*`, `_navigation_livelock*`,
  `_dark_locomotion*`, `_dark_*`, `_plan_explore*`, `_dungeon_entry*`, `_frontier_*`,
  `_open_neighbor_count`, `_undersearched_walls`, `_cell_readable_if_stood`, `_is_oscillating`,
  `_suppress_pending_stair_command`, `_remember_stair_command`. 79 methods.
  **Excluding** `_q2_breach_key` (81 lines), which is reserved for Phase 8.
- Class name: `NavigationMixin`.
- **Do NOT move** `ExplorationGoalKind`, `ExplorationPathOutcome`, `ExplorationGoalIdentity` — they
  stay at module level in `policy.py` for pickle-by-reference compatibility (§2 caveat).
- Expected delta: `policy.py` −2,515, new module +2,560.
- Test split: `UnseenAttackerTest` (746), `DescendTest` (326), `WarningGridAvoidanceTest` (318),
  `ProbeTest` (249), `TownNightNavigationTest` (221), `SummonerMeleeTest` (211),
  `TownTravelerCombatPriorityTest` (206), `SearchTest` (146), `RememberedFrontierTest` (85),
  `DescentBlockCooldownTest` (68), `TownFrontierTest` (43), `ExplorationTest` (170),
  `RubbleTest` (28), `AntiStuckTest` (17) → `tests/test_policy_navigation.py`.
  **Name collision:** `tests/test_navigation.py` already exists (for `navigation.py`). Use
  `tests/test_policy_navigation.py`; do not merge into the existing file.
- Mutation anchors to retarget: `mutation_battery.py:349`, `:392` (`_step_toward`), `:605`
  (`_dungeon_entry_allowed`), `:658` (`_suppress_pending_stair_command`). **4 anchors.**
- Importer repoint: `tests/test_navigation.py` imports `FOOD, SCROLL, grid, hostile, item, player`
  from `test_policy` — these are fixture helpers, **not** moved. Leave that import alone.

### Phase 6 — combat / danger → `src/hengbot/policy_combat.py`

- Move: `_emergency_*`, `threat_prediction`, `_threat_*`, `_breeder_*`, `_melee_*`, `_ranged_*`,
  `_update_combat*`, `_choke_*`, `_forbid_wait*`, `_hunt_*`, `_flee_*`, `_refresh_paralyzer*`,
  `_paralyz*`, `_swarm_*`, `_engagement_*`, `_fruitless_fight*`, `_guarded_paralyzers`,
  `_has_line_of_fire`, `_offset_fire_aim`, `_predicted_damage`, `_strategic_hostiles`,
  `_perceived_hostiles`, `_remember_swarm_distances`, `_has_state_based_free_action`. 85 methods.
  **Excluding** `_q2_ranged*` (117 lines), reserved for Phase 8.
- Class name: `CombatMixin`.
- Expected delta: `policy.py` −3,400, new module +3,450.
- Test split: `CombatTest` (4,311), `PredictiveEscapeTest` (1,596), `UniqueCombatConsumableTest`
  (1,197), `EmergencyRecallEscapeTest` (441), `DetectedMonsterChannelTest` (205),
  `NoWaitUnderFireTest` (203), `ConsumableTest` (110), `EmergencyHealBeforeFleeTest` (106),
  `AggregateRangedCacheTest` (102), `ThreatPredictionMemoTest` (38) →
  `tests/test_policy_combat.py`. No external importers.
- Mutation anchors to retarget: `mutation_battery.py:418`, `:428` (`_hunt_step`), `:372`
  (`_paralyzer_prevention_key`), `:359` (`_paralyzing_monsters`), `:323`, `:337`
  (`_refresh_paralyzer_avoidance`), `:313` (`_has_state_based_free_action`). **7 anchors.**
- Landmine: the summoner ranged-kill priority rule and the `recall-entry-invariant` live here.
  Verbatim move only.

### Phase 7 — misc helpers → `src/hengbot/policy_helpers.py`

- Move the 25 small predicates: `_pick_alternate_dungeon`, `_transaction_retain_identities`,
  `_refuse_no_progress_cycle`, `_is_disposable_item`, `_periodic_filler_is_safe`,
  `_find_disposable_item`, `consume_look`, `_has_destruction_method`, `_profile_resistance_name`,
  `_is_completed_forgetting_maze`, `_inventory_signature_count`, `_weakest`, `_speed_energy`,
  `_latch_warning_refusal`, `_inventory_weight`, `_curse_unremovable`, `_first_item`,
  `_is_active_dungeon_entrance`, `_evaluate_cross_decision_latches`, plus the remaining 6.
- Class name: `PolicyHelpersMixin`.
- Expected delta: `policy.py` −382, new module +420.
- These have 192 inbound call edges from 8 clusters and 9 outbound — the highest fan-in per line in
  the file. That is harmless under mixins and is precisely why they belong in a shared module rather
  than being scattered into the cluster modules.
- Test split: `FullPackDisposalTest` (131), `StoreSellGateTest` (75), `HighValueBookSaleTest` (63),
  `ItemShedListTest` (45) → `tests/test_policy_helpers.py`.
- Mutation anchors to retarget: `mutation_battery.py:646` (`_transaction_retain_identities`).
  **1 anchor.**

### Phase 8 — quest strategies → `src/hengbot/policy_quest.py`

- Move: `_quest_*`, `_fixed_quest*`, `_evaluate_fixed*`, `_morivant_*`, `_unique_*`, `_opening_q*`,
  `_derived_home*`, `_kill_quest*`, `_guardian_fight*`, `_q31_*`, `_q34_*`, `_request_priority*`,
  `_conquest_*`, plus the reassignments `_q2_phase_key`, `_q2_encounter*`, `_q2_ranged*`,
  `_q2_breach_key`. 94 + 4 methods.
- Class name: `QuestMixin`.
- Expected delta: `policy.py` −5,266, new module +5,320.
- Test split: `ApprovedQuestStrategyExecutionTest` (5,583), `FixedQuestTest` (1,811),
  `Q22Q31StrategyExecutionTest` (1,199), `DungeonConquestTest` (536),
  `WarningGridComposedWalkTest` (132) → `tests/test_policy_quest.py`.
- **Importer repoint (same commit):** `tests/test_golden_trajectory.py` references
  `fixture.ApprovedQuestStrategyExecutionTest`. Repoint it to
  `from test_policy_quest import ApprovedQuestStrategyExecutionTest`. **Do not re-export from
  `test_policy.py`** (see §5).
- Mutation anchors: none currently land in this cluster.
- Landmine: `post-rework-quest-strategy-watch` is a standing user rule — after this phase, watch a
  live run for quest-acceptance and strategy-route breakage even though the gate is green.

### Phase 9 — equipment (tangle 2) → `src/hengbot/policy_equipment.py`

- Move: `_prepare_equipment*`, `_equipment_*`, `_abandon_blocked*`, `_wield_*`, `_home_rearm*`,
  `_town_restore*`, `_town_equipped*`, `_town_enchant*`, `_launcher_*`, `_find_weapon*`,
  `_normal_sub_hand*`, `_normal_weapon*`, `_main_hand_dps`, `_sub_hand_dps`,
  `_queue_standing_home_digger`, `_withdrawable_digging_tool_count`,
  `_is_disposable_dominated_launcher`, `_retained_ammo_slots`, `_is_wanted_jewelry`. 84 methods.
- Class name: `EquipmentMixin`.
- Expected delta: `policy.py` −2,967, new module +3,010.
- This is tangle 2. `_equipment_optimization_signature` and `_equipment_optimization_preparation`
  are written by 6–7 clusters (including `calibration`, moved in Phase 1, and `snapshot_parse`,
  moved in Phase 12). Under mixins those writes keep working untouched — but the review must
  confirm no write site changed, not merely that the tests pass.
- Test split: `GlobalEquipmentOptimizationOwnershipTest` (1,753),
  `EquipmentQuarantineInvariantTest` (825), `EquipmentTransactionOwnershipRegressionTest` (779),
  `ConfirmedLoadoutPublicPathPinTest` (639), `OverflowDisposalTest` (447), `EntranceTravelTest`
  (254), `WeaponSaleTest` (239), `EquipmentTransactionQuarantineInvariantTest` (147),
  `LauncherEnchantTest` (143), `EquipmentOptimizationDestructionWiringTest` (112),
  `JewelryKeepingTest` (34), `ArmorDominanceTest` (9), `WieldHandSuffixTest` (102) →
  `tests/test_policy_equipment.py`.
- **Importer repoint:** `tests/absorbing_state_catalog.py` references
  `fixture.EquipmentTransactionOwnershipRegressionTest`.
- Mutation anchors to retarget: `mutation_battery.py:634` (`_prepare_equipment_optimization`),
  `:442`, `:593` (`_queue_standing_home_digger`), `:268` (`_rearm_town_store_for_new_work`), `:213`
  (`_set_equipment_transaction_session`). **5 anchors.**

### Phase 10 — home (tangle 1a) → `src/hengbot/policy_home.py`

- Move: `_atomic_home*`, `_home_*`, `_retention_*`, `_find_home*`, `_overweight_*`, `_record_home*`,
  `_prepare_home*`, `_queue_home*`, `_bind_catalogued*`, `_confirm_home*`, `_has_actionable*`,
  `_observe_withdrawal*`, `_deferred_home*`, `_can_add_item_without_overweight`,
  `_inventory_weight_limit`, `_destroy_*`. 65 methods.
- Class name: `HomeMixin`.
- Expected delta: `policy.py` −2,419, new module +2,460.
- **Highest-risk phase for checkpoint compatibility.** All 30 names in
  `home_entry_capture.STATE_FIELDS` are read from the policy by `getattr` and 20 of them belong to
  this cluster. Under mixins they stay on `HengbotPolicy.__dict__` and nothing changes — but this is
  the phase where a careless "tidy the attribute name" would be fatal. Zero renames (§6).
- Test split: `HomeOneOperationPerEntryTest` (2,338), `WeightOverloadTownTest` (501),
  `RetentionAuthorityTest` (333), `RearmAndBreakoutRegressionTest` (227), `HomeVisitOwnershipTest`
  (205), `UnknownTargetLoadoutSurplusTest` (186), `TownDepartureConvenienceDepositTest` (88),
  `HomeFullLatchTest` (66), `MiningGearHomeStorageTest` (27), `HomePageAdvanceCurrencyTest` (97) →
  `tests/test_policy_home.py`.
- **Importer repoint (two files):** `tests/absorbing_state_catalog.py` and
  `tests/test_home_entry_capture.py` both reference `HomeOneOperationPerEntryTest`.
- Mutation anchors to retarget: `mutation_battery.py:511`, `:521` (`_atomic_home_withdraw_key`),
  `:279`, `:531` (`_confirm_home_withdrawal_address`), `:169` (`_home_mana_food_candidate`), `:254`,
  `:258` (`_prepare_home_visit_operation`), `:199` (`_withdrawable_digging_tool_count`).
  **8 anchors** — the largest single-phase anchor load.
- Landmine: `bot-home-first-procurement` is an absolute rule. Any change to the Home-before-store
  ordering is a behavior edit and must not appear in this commit.

### Phase 11 — shop / store (tangle 1b) → `src/hengbot/policy_shop.py`

- Move: `_shop*`, `_shopping_*`, `_next_required*`, `_next_purchase*`, `_batch_sell*`,
  `_atomic_shop*`, `_store_*`, `_purchase_*`, `_record_shop*`, `_evaluate_purchase*`,
  `_restore_mining*`, `_enumerate_live*`, `_cross_town_shopping*`, `_sale_retains_digging_tool`,
  `_find_low_level_sale`, `_find_light_sale`, `_find_book_sale`, `_cheapest_exchange_item`,
  `_batch_sale_entry`. 72 methods.
- Class name: `ShopMixin`.
- Expected delta: `policy.py` −4,114, new module +4,160.
- Test split — **this phase needs a class split first.** `TownAndFundraisingPolicyTest` is a single
  10,588-line class. Split it in two steps:
  - **Phase 11a (test-only commit):** split `TownAndFundraisingPolicyTest` into
    `TownAndFundraisingPolicyTest` (town-plan methods) and `ShopPurchaseSellPolicyTest` (shop/sell
    methods) inside `tests/test_policy.py`, moving method bodies verbatim with no edits.
    `absorbing_state_catalog.py` references the original class name — keep that name on the
    town half so the importer keeps resolving.
  - **Phase 11b (the move):** move `ShopPurchaseSellPolicyTest`, `TownErrandPlanTest` (2,865),
    `ProbePurityIncidentPinsTest` (350), `OptionalBlackMarketPotionTest` (162),
    `StoreTravelRetryTest` (118), `StatRestoreTest` (82), `ScavengeStoreLatchTest` (38),
    `StoreAttemptExpiryTest` (63) → `tests/test_policy_shop.py`.
  - **Importer repoint:** `absorbing_state_catalog.py` references `fixture.TownErrandPlanTest`.
- Mutation anchors to retarget: `mutation_battery.py:179` (`_sale_retains_digging_tool`), `:125`,
  `:145`, `:157`, `:189` (`_shop`), `:244` (`_shopping_approach_step`). **6 anchors.**
- Landmine: `_shop` is a single 842-line method and four separate anchors index into it. All four
  snippets must remain byte-identical.

### Phase 12 — town (tangle 1c + tangle 3) → `src/hengbot/policy_town.py`

- Move: `_town_*` (excluding the `_town_restore*`/`_town_equipped*`/`_town_enchant*` already moved
  in Phase 9 and the `_town_plan_projection_telemetry` writes owned by shop), `_return_to*`,
  `_report_town*`, `_break_town*`, `_should_start*`, `_cross_town*` (non-shop half),
  `_dungeon_recall_issue_watch` handlers, `_errand_*`, `_departure_*`, `_visit_*`, `_approach_*`.
  82 methods.
- Class name: `TownMixin`. Composed **adjacent to** `TownArbiterMixin`; do not merge the two.
- Expected delta: `policy.py` −4,263, new module +4,310.
- `_town_need_candidates` (601 lines) is the single largest non-spine method and the heart of
  tangle 1. It moves whole, unedited.
- Test split: `TownRecallReturnTest` (1,547), `TownCycleDetectorTest` (1,513),
  `NoSafeRecallDestinationTest` (974), `ReturnToTownTest` (827), `RangedAttackTest` (805),
  `RemoveCurseTest` (653), `WildernessSafetyTest` (244),
  `RecallShortageBehaviorRestrictionTest` (163), `TownWanderCircuitBreakerTest` (149),
  `ResistanceGapReturnTest` (47), `TownAndFundraisingPolicyTest` (post-11a town half),
  `TownMapNightRoutingTest` (49), `TownTravelProgressTest` (43) → `tests/test_policy_town.py`.
- **Importer repoint (two files):** `absorbing_state_catalog.py` references
  `fixture.NoSafeRecallDestinationTest` and `fixture.TownAndFundraisingPolicyTest`;
  `tests/test_latch_onset_capture.py` references `NoSafeRecallDestinationTest`.
- Mutation anchors to retarget: `mutation_battery.py:541`, `:555` (`_town_departure_conjuncts`).
  **2 anchors.**
- Landmines: `town-liveness-invariant`, `bot-town-count-retirement` (state-based, not counts) and
  the `store-visit-leak` defect class all live here. Verbatim move only.

### Phase 13 — observation → `src/hengbot/policy_observation.py`

- Move: `_observe` (832), `_resolve_observed_uncomposable_stop`, `observe_character_snapshot`,
  `_refresh_warning_avoidance`, `_strategy_force_for_snapshot`, `_current_pinned_identities`,
  `_missing_required_*`. 7 methods.
- Class name: `ObservationMixin`.
- Expected delta: `policy.py` −989, new module +1,030.
- Deliberately last among the moves: `_observe` writes 133 attributes shared with 13 other clusters
  and is the widest single write surface in the file. Moving it after every consumer has already
  moved makes the review a one-directional check.
- Test split: `OverExtensionDungeonSwitchTest` (613), `StatusTest` (23) →
  `tests/test_policy_observation.py`.
- Mutation anchors: none.

### Phase 14 — module-level constants → `src/hengbot/policy_constants.py`

- Move the 260 module-level constants (and only constants — not the four pickled classes) into the
  existing `policy_constants.py`, with `from .policy_constants import *`-style **explicit
  re-exports** in `policy.py`.
- **25 distinct constants are imported directly from `hengbot.policy` by tests and scripts**, e.g.
  `DIRECTION_KEYS`, `CHARACTER_DUMP_MACRO`, `HOME_PAGE_SINGLE_PAGE_MESSAGES`, `WAIT_KEY`,
  `LEAVE_STORE_KEY`, `PACK_CAPACITY`, `FIXED_QUEST_ALLOWLIST`, `CALIBRATION_HOME_VISIT_LIMIT`,
  `QUEST_STATUS_TAKEN`, `RESIST_FLAG_BY_ABILITY`, `TOWN_TRAVEL_STORE_SYMBOLS`,
  `FIXED_QUEST_REWARD_POSITIONS`, `MINING_STALL_LIMIT`, `DIGGER_WIELD_LIMIT`, `WEAPON_BLOCK_LIMIT`,
  `ESCAPE_BUDGETED_WAIT_LIMITS`, `CHEST_DISARM_BUDGET`, `STORE_ALCHEMIST`, `STORE_HOME`,
  `WildernessMap`, `_persistent_grid_signature`, `_new_town_turn_arbiter`.
  Every one of those import sites must keep working — re-exports are mandatory, not optional.
- Expected delta: `policy.py` −900 (approx; constants are dense), `policy_constants.py` +940.
- This phase is optional and may be deferred; it buys little scope pruning because constants rarely
  change.

### Phase 15 — verification tooling (no `policy.py` change)

- Retire `verify_scope.ALWAYS_MODULES = {"tests.test_policy", ...}`. This literal is the reason
  every fix runs the full 61k-line `test_policy.py`, and it is the payoff the whole split is for.
  Replace `tests.test_policy` with the reduced set that actually needs to run unconditionally
  (probably `tests.test_policy` shrunk to its residual core plus `tests.test_policy_structure`).
  **This is a real logic change to the tooling** — it gets its own commit, its own review, and a
  before/after comparison of derived scopes on three historical fixes.
- Re-run `scripts/owner_map.py` (it globs the package, so it should pick up the new modules for
  free) and confirm the reason map is unchanged.
- Confirm `scripts/sale_key_lint.py` still covers every module (it globs `POLICY_ROOT/*.py` — new
  modules are picked up automatically, which also means new lint findings could surface; treat any
  as a pre-existing finding that moved, not a new defect).

**Total: 16 commits** (Phase 0, Phases 1–10, 11a, 11b, 12, 13, and 15; Phase 14 optional → 17).

### Expected end state

| | before | after |
| --- | ---: | ---: |
| `policy.py` | 38,239 | ≈ 4,600 (module region 1,367 + spine 2,638 + class shell ≈ 600) |
| largest single module | 38,239 | `policy_quest.py` ≈ 5,320 |
| `tests/test_policy.py` | 61,405 | ≈ 3,000 (fixtures + residual) |
| largest test module | 61,405 | `tests/test_policy_shop.py` ≈ 14,200 |

---

## 4. Verification gate — identical for every phase

A phase is complete only when **all** of the following hold. Each is a hard gate, not a signal.

1. **Replay key identity — both captures, byte-identical.**
   ```
   python tests/replay_key_equality.py equip-swap        # 400 decisions
   python tests/replay_key_equality.py no-actionable     # 300 decisions
   ```
   Both must print `identical N decisions`. This is the primary gate: it compares
   `(key, last_reason)` pairs against a pinned baseline and is the one check a behavior edit cannot
   sneak past. **Never re-record the baselines during a split phase** (`--record` is forbidden).
2. **Decision equivalence.**
   ```
   python scripts/decision_equivalence.py <repo's standard compare invocation>
   ```
   Must report no divergence against the pre-phase recording made in Phase 0.
3. **Parallel suite ×1.**
   ```
   python scripts/test_parallel_runner.py
   ```
   One clean run. Failures must match the Phase 0 baseline exactly, including the entries already
   listed in `verify_scope.KNOWN_FAILURES` — no new failure, and no *disappeared* failure either
   (a vanished known failure means a test stopped being collected, which is what a botched test
   move looks like).
4. **Focused modules.** `python scripts/verify_scope.py` for the phase, plus a direct run of the
   phase's own new test module and `tests.test_policy`.
5. **Checkpoint round-trip.** `tests/test_policy_structure.py` (added in Phase 0) green — attribute
   dict identity across `checkpoint` → `restore_checkpoint`.
6. **Structural diff review (Claude).** The diff must be readable as a pure move. Concretely:
   `git diff -M --stat` should show the moved lines as additions in the new module and deletions in
   `policy.py`, and a manual `diff` of the moved region against its pre-move text must be empty
   apart from indentation-neutral import adjustments.
7. **Capture ledger and incident fixtures byte-unchanged.** `git diff --stat` must show zero
   changes under `jsonlog/`, `tests/fixtures/`, `incident-captures/`, `evidence/`.

---

## 5. Landmines

Ordered by how expensive they are to discover late.

### L1 — `home_entry_capture.STATE_FIELDS` is an attribute-name registry (30 names)

`home_entry_capture.py:22–52` lists 30 attribute names read via
`getattr(policy, name, None)` at line 81; `_home_owned()` (lines 84–96) reads nine more the same
way. Twenty of them belong to the Phase 10 cluster. Because the read is `getattr` with a default,
**a renamed or missing attribute produces `None` silently** — no exception, no test failure, just a
capture that quietly records nothing. Mitigation: zero renames (§6), and Phase 10's review must
diff the 30 names against `STATE_FIELDS` explicitly.

### L2 — `restore_checkpoint` setdefaults are an ordered upgrade chain

`latch_onset_capture.py:48–100` runs `policy_type.__new__` then `__dict__.update(pickle.loads(...))`
followed by 12+ `setdefault` calls and two value-normalization blocks (`_town_blocked_reason_value`
legacy names, `_cross_decision_latches` permanent-value patching). This function is the **only**
compatibility boundary for old checkpoints. Two rules:

- No phase may add, remove, or reorder anything in it. If a phase seems to need a new `setdefault`,
  that phase is not a pure move — stop and escalate.
- The four module-level classes pickled by reference (`ExplorationGoalKind`,
  `ExplorationPathOutcome`, `ExplorationGoalIdentity`, `ProcurementHomeGate`) stay in `policy.py`.
  Moving one without a re-export alias makes every existing checkpoint unloadable with
  `AttributeError` at unpickle time.

### L3 — `mutation_battery.py` anchors: 41 `policy.py` snippets, each requiring exactly one match

`scripts/mutation_battery.py` holds 47 `replacement(path, old, new)` anchors, 41 of them against
`"policy.py"`, and `apply_edit` refuses unless `text.count(edit.old) == 1` (line 688–690). Two
things break them:

- **Path**: after a move, `relative_path` must become the new module filename. This retarget is a
  **required companion edit in the same commit** and is explicitly permitted (it is a tooling path
  literal, not policy behavior).
- **Count**: if a snippet becomes ambiguous or vanishes, the anchor silently degrades.

Per-phase anchor load (measured by locating each snippet's enclosing method):

| Phase | Cluster | Anchors | `mutation_battery.py` lines |
| ---: | --- | ---: | --- |
| 1 | calibration | 0 | — |
| 2 | identification | 0 | — |
| 3 | fundraising | 0 | — |
| 4 | supply | 1 | 135 |
| 5 | navigation | 4 | 349, 392, 605, 658 |
| 6 | combat | 7 | 313, 323, 337, 359, 372, 418, 428 |
| 7 | helpers | 1 | 646 |
| 8 | quest | 0 | — |
| 9 | equipment | 5 | 213, 268, 442, 593, 634 |
| 10 | home | **8** | 169, 199, 254, 258, 279, 511, 521, 531 |
| 11 | shop | 6 | 125, 145, 157, 179, 189, 244 |
| 12 | town | 2 | 541, 555 |
| 13 | observation | 0 | — |
| — | stays in `policy.py` (`_decide`) | 1 | 301 |
| — | already non-`policy.py` | 6 | 224, 234, 382, 402, 491, 501 |

**Pre-existing breakage found while measuring:** `mutation_battery.py:480`
(`drop-evaporated-home-claim-charge`) and `:620` (`route-only-addressed-digger-withdrawal`) have
`count == 0` against the current `policy.py` — they are already stale, before any split. Phase 0
fixes or retires them so the battery is a valid baseline.

### L4 — `verify_scope` prunes by **top-level** symbol only

`verify_scope.top_level_symbols()` walks `tree.body` — top level only. `policy.py` has exactly 8
top-level symbols plus `HengbotPolicy`, so *any* change inside the class reports the symbol
`HengbotPolicy`, which nearly every test module mentions. That is the mechanism behind today's
always-huge scope, and the split is what fixes it: a change in `policy_home.py` will report
`HomeMixin`, matched by far fewer test modules.

Two derived rules:

- **Name each mixin distinctively.** A mixin named something generic that appears as a substring in
  unrelated tests re-creates the problem. `derive_scope` matches with `\b<name>\b`.
- **Create `tests/test_<module stem>.py` for every new module.** `derive_scope` (lines ~305–309)
  auto-adds `tests/test_<stem>.py` as the owner test for a changed `src/hengbot/<stem>.py`. Naming
  the test file to match the source stem is what wires the seam up; a mismatched name loses it.
- `ALWAYS_MODULES` still forces `tests.test_policy` into every scope. Until Phase 15 lands, the
  pruning benefit is only partially realized — expected, not a defect.

### L5 — `hunk_guard` prunes by symbols *introduced in the hunk*

`hunk_guard.modules_for_hunk` (line 290) intersects `introduced_symbols(hunk["body"])` against test
sources. In a pure move commit the hunk bodies are the moved method texts, so the introduced symbols
are the moved method names — pruning stays accurate and actually improves, since the candidate
module list shrinks with `scope["modules"]`. But `hunk_guard` also treats an
`ImportError`/`ModuleNotFoundError` naming an introduced symbol as evidence (line 210): a phase that
forgets an import in the new module can be *scored* rather than *failed*. Rule: never accept a
hunk_guard verdict on a phase whose parallel suite showed an import error.

### L6 — test-class re-exports would double-count the suite

Six test classes in `test_policy.py` are referenced by other test modules:

| Class | Referenced by | Moves in |
| --- | --- | ---: |
| `TownAndFundraisingPolicyTest` | `absorbing_state_catalog.py` | 12 (town half) |
| `TownErrandPlanTest` | `absorbing_state_catalog.py` | 11b |
| `HomeOneOperationPerEntryTest` | `absorbing_state_catalog.py`, `test_home_entry_capture.py` | 10 |
| `NoSafeRecallDestinationTest` | `absorbing_state_catalog.py`, `test_latch_onset_capture.py` | 12 |
| `EquipmentTransactionOwnershipRegressionTest` | `absorbing_state_catalog.py` | 9 |
| `ApprovedQuestStrategyExecutionTest` | `test_golden_trajectory.py` | 8 |

The tempting fix — re-exporting the moved class from `test_policy.py` — makes `unittest` collect it
in **both** modules, doubling its runtime and changing the parallel-suite counts, which then fails
gate 3 for reasons that look unrelated. **Repoint the importers in the same commit; never
re-export.**

Separately, five modules import *fixture helpers* (`grid`, `player`, `item`, `hostile`, `FOOD`,
`SCROLL`) from `test_policy`: `test_exploration_commitment_observation.py`, `test_navigation.py`,
`test_quest_navigator.py`, `test_town_restock_trajectory.py`, `test_worldmap_key_hygiene.py`.
Those helpers stay in `test_policy.py`. Do not move them.

### L7 — MRO shadowing is silent

Composing 12 mixins into one class means a duplicated method name resolves by MRO order with no
warning. A copy-paste that leaves the original behind in `policy.py` produces a class where
`policy.py`'s copy wins (it is the subclass body) and the mixin's copy is dead — replay stays green
and the split looks done while nothing actually moved. The Phase 0 collision test plus a
`policy.py`-side check that the moved names are absent from the class body is the guard.

### L8 — `sale_key_lint` globs the whole package

`scripts/sale_key_lint.py:58–60` iterates `POLICY_ROOT.glob("*.py")`. New modules are covered
automatically — good — but findings that today report as `policy.py: ...` will start reporting as
`policy_shop.py: ...`. Any allowlist or count keyed on the filename needs the same retarget
treatment as the mutation anchors.

---

## 6. DO-NOT list

Binding for every phase. A violation is grounds for revert, not a review comment.

1. **No renames of state attributes.** Not `self._x` → `self._y`, not casing, not a "clearer" name.
   549 attribute names are the checkpoint contract (§2, L1, L2).
2. **No signature changes.** No added parameters, no defaults changed, no keyword-only conversions,
   no return-type changes, no `@property` added or removed.
3. **No behavior edits of any kind in a move commit.** No condition reordering, no dead-branch
   removal, no constant folding, no "obvious" bug fix, no `is None` → `if not`. If a bug is spotted
   during a move, **write it down and leave it** — it becomes a separate task after the phase lands.
4. **No new guard constants, no new latches, no new early returns.** (Standing anti-enbug rule.)
5. **No reformatting.** No line rewrapping, no import reordering beyond what the move requires, no
   docstring rewording, no comment cleanup. Whitespace-only churn hides real edits from gate 6.
6. **No moving the spine.** `_decide`, `__init__`, `prime` stay in `policy.py`.
7. **No moving the four pickled module-level classes** without a re-export alias
   (`ExplorationGoalKind`, `ExplorationPathOutcome`, `ExplorationGoalIdentity`,
   `ProcurementHomeGate`). The recommendation is: do not move them at all.
8. **No re-recording replay baselines** (`replay_key_equality.py --record`) during a split phase.
9. **No test-class re-exports from `test_policy.py`** (L6).
10. **No edits to `latch_onset_capture.restore_checkpoint`** or `home_entry_capture.STATE_FIELDS`.
11. **No combining phases.** One phase, one commit, one review.
12. **No `__getstate__`/`__setstate__`/`__reduce__`** added to `HengbotPolicy`.

---

## 7. Rollback rule

**Any phase that fails replay key identity is reverted, not patched forward.**

- On a mismatch in gate 1 or gate 2: `git revert` the phase commit (or `git reset --hard` if
  unpushed). Do not attempt to locate and fix the divergence inside the same commit — a move commit
  that needs a fix is by definition no longer a move commit, and a "fixed" move is the exact shape
  in which a behavior change enters the tree invisibly.
- After reverting, re-run gate 1 to confirm the baseline is restored before anything else happens.
- The reverted phase is then re-attempted from scratch, with the divergence recorded first: run the
  failing capture on the reverted tree and on the failed tree and diff the two decision streams to
  name the first divergent decision index, key, and reason. That diff, not a hypothesis, is the
  input to the retry.
- Gate 3 failures (parallel suite) follow the same rule when the failure is a new one. A
  *disappeared* known failure is also a revert — it means a test stopped being collected.
- Gate 6 (structural diff review) failing is a revert too: if the diff is not readable as a pure
  move, the commit is not what it claims to be, regardless of green gates.
- If two consecutive attempts at the same phase fail, stop and escalate. Do not attempt a third.
  (Three-strike breaker, standing rule.)

---

## 8. Open questions for the user

1. **Phase 14 (constants)** buys little scope pruning and touches 25 external import sites. Include,
   or drop it?
2. **Phase 15** changes `verify_scope.ALWAYS_MODULES` — a real logic change to the gate tooling.
   It is the payoff of the whole project, but it should probably be reviewed against three
   historical fixes before landing. Confirm that is wanted.
3. **Phase 11a** splits a 10,588-line test class. That is the only phase that restructures test code
   rather than relocating it. Confirm it is acceptable, or the shop phase must ship its test split
   as one 14,000-line module.

---

## 9. USER DECISIONS (2026-09-06, recorded by Fable — this section is authoritative)

1. Phase 14 (constants): **EXCLUDED** from this project. May be done later as a standalone commit. Total = **16 commits** (0-10, 11a, 11b, 12, 13, 15).
2. Phase 15 (verify_scope.ALWAYS_MODULES tooling change): **APPROVED** — implement as a reviewed tooling fix with its own tests, validated against three historical fixes before landing.
3. Phase 11a (TownAndFundraisingPolicyTest restructuring): **APPROVED** — test IDs change; every in-repo referrer is repointed in the same commit, and the fix event lists the id mapping so standing docs/monitors can be updated.
4. Standing constraints from the split gate lift (user 2026-09-06): split has RAISED priority; phases are strictly sequential (single-writer); any phase failing replay identity is reverted, never patched forward; two consecutive failures on one phase = stop and escalate to the user.

## 10. RESIDUE LEDGER (append-only; each phase review adds leftovers here)

- Phase 1 (bea6b21): `calibration_entry_state` (public, 46 LOC) remained in
  policy.py — the phase's `_calibration_*` pattern (leading underscore) did
  not match it. Pick it up in a later calibration-adjacent phase or a
  dedicated residue commit; the collision guard will protect the move.
- Phase 1 (bea6b21): `CHARACTER_DUMP_MACRO` and
  `EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT` are DUPLICATED in policy.py and
  policy_calibration.py (identical values today; divergence hazard).
  Consolidate into policy_constants.py (both sides import) — scheduled as a
  Phase 2 rider.
- Phase 2 F4 (constants consolidation): `policy_identification.py` duplicated
  23 constants still defined in `policy.py`; 12 of the policy-side copies were
  dead after the identification move. Resolved by defining the shared values
  once in `policy_constants.py` and policy.py re-imports all consolidated names from policy_constants (re-export compatibility: tests and scripts access several via hengbot.policy attributes, which is WHY zero-Load deletions were safe).
- Phase 2 F5 (derived-neighbour authority): the identification mixin rewrote
  `NEIGHBOR_OFFSETS` as an expanded literal instead of retaining
  `tuple(DIRECTION_KEYS.keys())`. Resolved by moving `DIRECTION_KEYS` alongside
  the shared constants and deriving `NEIGHBOR_OFFSETS` exactly once in
  `policy_constants.py`.

- Phase 2 (9af9d8c): the roadmap's Phase 2 section says 29 methods, but its
  literal prefix list matches only 21; these 8 identification/chest methods
  remain in policy.py for a later residue commit: _is_processable_chest,
  _normal_identification_flow_candidate, _reserve_next_identification_source,
  _release_identification_source_reservation,
  _town_equipped_identification_key, _request_identification,
  _retain_identification_source_owner, _defer_full_identification.
- Phase 2 rework (6d39996) follow-ups queued as Phase 3 riders: hunk_guard
  F2 any() short-circuits on the first non-parsing line (prose-first mixed
  hunks still SKIPPED); dead LEAVE_STORE_KEY import in
  policy_identification.py; fix-event receipts must list path+sha256 pairs
  (the rework event regressed to hashes only); scripts self-test suite
  (scripts/test_verification_gates.py) is outside parallel/serial discovery
  and must be run focused whenever scripts/ changes.
- Phase 3: the roadmap's literal prefix list matches 24 methods, not the
  stated 35. The 11-method count mismatch is retained for later classification;
  Phase 3 moved only the methods selected by the authoritative literal prefixes.
- Phase 4: the roadmap's literal prefix list matches 28 methods, not the
  stated 77. The 49-method count mismatch is retained for later classification;
  Phase 4 moved only the methods selected by the authoritative literal prefixes.
- Phase 4 (fd660d9) review notes: (a) the NameError repair added a
  _supply_test_case() lazy accessor in tests/test_policy.py and one
  qualified reference in the moved WieldLightTest — undisclosed in the
  event (accuracy demerit on record); (b) LANDMINE for Phase 6:
  tests/test_policy_supply.py:168 does `import test_policy as _test_policy`
  and :1133 references test_policy.EmergencyRecallEscapeTest — Phase 6
  moves that class to test_policy_combat.py and WILL break this reference;
  repoint it in the same commit.
- Phase 5: the roadmap's literal prefix list matches 27 methods, not the
  stated 79. The 52-method count mismatch is retained for later classification;
  Phase 5 moved only the methods selected by the authoritative literal prefixes.
- Phase 5 (fed6344) review notes: 4 of 27 moved methods drifted by docstring
  trailing whitespace only (semantically pure; describe such moves as
  "AST-identical modulo docstring whitespace" going forward); dead
  `import test_policy as _test_policy` in tests/test_policy_navigation.py:169
  (inherited template, unused) — remove in a later phase.
- Phase 6 breaker (2026-09-07, attempts 8cfc77d/2750f34 rolled back):
  investigated and the move EXONERATED. Root causes are latent: (1)
  home_disposal.py writes a fixed cwd-relative home-withdraw-history
  .jsonc.tmp with no env override; four test modules drive it; the phase's
  NEW test module made the parallel partitioner discard all weights
  (any-unweighted guard) and round-robin co-scheduled the writers -> tmp
  replace race. (2) WORSE: _read_json swallows OSError -> {} -> next
  record() silently REWRITES the live bot's durable history from empty
  (reproduced: 9676 tx/recall 133 -> 248/0; restored). Retry round =
  runner-only fix (SERIAL_MODULES for the three out-of-pool writers +
  default weight for unknown modules) + reapply the move. QUEUED with full
  gates: home_disposal hardening — env-routed path (isolates workers AND
  stops suite runs polluting the live 1.9MB artifact, ~4000 rows/day,
  ~89s/suite parse tax) + _read_json OSError hardening + the same pattern
  in the queue writer (:190); exploration_ledger.py shares the .tmp+replace
  shape but is not test-reachable (path=None default).
- Phase 6: the roadmap's literal prefix list matches 38 methods, not the
  stated 85. The 47-method count mismatch is retained for later classification;
  Phase 6 moved only the methods selected by the authoritative literal prefixes.
- Phase 6 retry (894f809+73f23b8) review notes: move 38/38 AST-identical
  (streak 6); minor: event misquoted the roadmap's `_paralyz*` prefix as
  `_paralyz_*` (implementation used the correct one); expected-delta lines
  in the phase section reflect the phantom 85-method count. The exonerated
  2750f34 additionally lacked battery retargets (would have failed the
  battery gate) — caught and fixed in reconstruction.
- home-disposal hardening (06766d8) review notes: ACCEPT; dead-latch,
  phantom-pin, trailer all closed. Phase 7 riders queued: (D1) the serial
  selftest's assertNotIn(HENGBOT_HOME_HISTORY_DIR, os.environ) sits outside
  its patch context and fails if the ambient env sets the var — move it
  inside; (D2) scripts/mutation_battery.py:~725 does not set
  HENGBOT_HOME_HISTORY_DIR, so every battery run writes the LIVE
  home-withdraw-history.jsonc (measured: +89 tx/+2 recall in one run) —
  wire the isolation env there too. NOTE: live file now 10,181 tx /
  recall 145, overwhelmingly test pollution accumulated before H2; a
  cleanup/restore decision is deferred to the user (recall counter gates
  disposal cadence).
- Phase 7: the roadmap's literal move list names 19 methods, not the stated
  25. The unspecified "remaining 6" are not runnable literal selectors and
  remain in policy.py for later classification; Phase 7 moved only the 19
  explicitly named methods.
- Phase 7 (bb89fe0+4c5efef) review notes: ACCEPT, streak restarted at 1.
  Phase 8 rider queued: fixture-DEFAULT history isolation —
  os.environ.setdefault(HOME_HISTORY_DIR_ENV, per-process tempdir) in BOTH
  tests/__init__.py and the shared module test_policy imports (the repo
  uses both "tests.test_policy" and bare "test_policy" import forms), plus
  a selftest asserting a bare unittest run does not touch
  <repo>/home-withdraw-history.jsonc; runner per-worker roots keep priority
  via setdefault. Conduct rule stays as secondary. Live file drifted again
  (+22 tx/+3 recall this round): now 10,203 tx / recall 148 — cleanup
  decision still pending with the user.
- Phase 8: the roadmap's literal prefix list matches 66 methods, not the
  stated 94 + 4. The 32-method count mismatch is retained for later
  classification; Phase 8 moved only the methods selected by the authoritative
  literal prefixes and exact `_q2_phase_key` / `_q2_breach_key` names.
- Live-history cleanup (user decision 2026-09-07): investigation found NO
  pre-pollution backup anywhere — the file itself began 2026-09-02 already
  carrying test-fixture names, and every on-disk copy was a test artifact.
  Composition was 10,203 tx of which only ~96 were live-shaped (turns
  1.3-1.5M, real Japanese item names); the rest were fixture names (item /
  captured restore / home pick / restore 00-11 / selected sword ...).
  User chose: reset transactions to [] and KEEP dungeon_recall_count=148.
  Applied: home-withdraw-history.jsonc is now 77 bytes (tx 0, recall 148,
  version 1); pre-reset file preserved at
  C:\hengband\backups\home-withdraw-history.jsonc.bak-20260907-preclean
  (2,054,315 bytes, sha256 b1f0022c...). Phase 8's fixture-default
  isolation rider is what keeps it clean from here.
- Phase 8 (6d2e9ce+54efee5+1d843fe) review notes: move REJECTED once for
  duplicate collection (+174 ids/+7 skips) caused by a from-import of a
  foreign TestCase in tests/test_golden_trajectory.py; fixed by module-alias
  form plus a duplicate-collection guard (revert-proved). Final id math:
  3139 unique = 3135 base + 320 moved 1:1 + 4 genuinely new, 0 duplicated,
  skips back to 26. SUPERVISOR NOTE: sol's rebuild reset past two pushed
  commits (incl. the user's live-history cleanup record); the work was
  rebased onto origin/main and the standing rule "never reset past a commit
  that exists on origin/main" was added to fixer prompts.
  Phase 9 riders queued: (a) scripts/run_receipt.py sets no isolation env,
  so receipted bare-unittest runs still touch the live history via
  in_repo()'s Path.cwd() fallback (measured: recall drifted 148 -> 152 —
  transactions stayed []); wire the env there; (b) the duplicate-collection
  guard imports test modules by bare stem, creating second module objects
  under the runner — switch it to the `tests.<stem>` form; (c) fix events
  keep listing receipts by label without paths — path+sha256 is required.
- Phase 9 attempt 1 (b4991b0, parked at branch phase9-attempt1): REVERTED
  per §7 after the parallel gate showed 2 new failures in
  tests.test_ability_sources_incident (_equipment_optimization_last_depth
  None instead of 19). MECHANISM (supervisor-confirmed by source read, not
  a guess): that module patches "hengbot.policy.prepare_warrior_optimization"
  (lines 118/126); once _prepare_equipment_optimization moves to
  policy_equipment.py the call resolves against the NEW module's globals, so
  the patch no longer intercepts and the stubbed preparation never lands.
  Same class as Phase 1's calibrate_character_constants repoint — a TEST-side
  patch-target repoint, not a production defect.
  NEW STANDING PRE-CHECK for every move phase: before committing, grep the
  WHOLE tests tree for patch("hengbot.policy.<name>") / patch.object on
  hengbot.policy for every symbol the phase moves (and for functions the
  moved methods CALL that are imported into the source module), and repoint
  them in the same commit. Do not rely on per-phase discovery.
  Riders of that round landed separately as b00de17 (receipt-run history
  isolation + tests.<stem> duplicate-collection guard).
  Rider follow-ups: run_receipt's isolated_home_history gates on env
  MEMBERSHIP, so an empty HENGBOT_HOME_HISTORY_DIR falls through to cwd and
  writes the live file (reviewer tripped it: 148->149, restored) — match
  test_timing_runner's truthiness check or harden in_repo() against blank
  values; and note ReceiptHistoryIsolationProbeTest is a deliberate canary
  that bumps the live counter if run bare without the env.
- Phase 9: the roadmap's literal prefix list matches 43 methods, not the
  stated 84. The 41-method count mismatch is retained for later classification;
  Phase 9 moved only the methods selected by the authoritative literal prefixes
  and exact names. Four mutation anchors moved with those methods; the listed
  `_set_equipment_transaction_session` method is outside the literal selectors
  and remains in policy.py with its anchor.
- Phase 9 retry (81b77a4): ACCEPT. Attempt-1's failure class is CLOSED —
  two independent tree-wide sweeps (43 moved symbols + 24 reviewer-derived
  at-risk module helpers) found zero stale patch/import targets, and the
  lone-revert of the old patch strings reproduces exactly the two
  "None != 19" failures. Event narration corrections recorded by review:
  (i) 3 anchors bite, not 4 (omit-inflight-digger is a standing miss);
  (ii) "42 constants" was the added LINE count — the real symbol count is
  11; (iii) the discovery-accounting sentence is arithmetically broken
  though its underlying facts are right; (iv) the quest weapon_expected_dps
  patches are consumed by _approved_strategy_force_ready which REMAINS in
  policy.py (not by quest-module methods as the event said) — retaining
  them was still correct. Note hunk_guard's candidate_modules omits
  tests.test_policy_quest, so that seam is not advisory-covered.
- Phase 10 attempt (breaker, both attempts reverted): failures were purely
  MECHANICAL hand-execution slips — (1) AST spans excluding decorators
  stranded @staticmethod onto the FOLLOWING methods (_inventory_overweight,
  _find_low_level_sale) causing "missing snapshot argument"; (2) an import
  header copied from Phase 9 omitted ADJ_STR_WEIGHT_LIMIT and
  UNUSED_DIVE_LIMIT (NameError). Per the 3-strike rule the response was
  STRUCTURAL: scripts/split_move.py (cc91b9a) now performs moves with
  decorator-inclusive spans, auto-computed imports, and pre-write
  self-verification. Riders 8a66c51 closed the blank/empty
  HENGBOT_HOME_HISTORY_DIR hole and documented hunk_guard ADVISORY_GAPS.
  REVIEW VERDICT: both commits ACCEPT and pushed, but the TOOL IS NOT YET
  USABLE for Phase 10 — blockers found by adversarial testing:
   F1 (blocker) base-class insertion renders `class HengbotPolicy(A, ..., Z), HomeMixin:`
      — outside the parens => SyntaxError. Untested path: the self-test
      fixture class has no bases and --dry-run returns before render.
      Fix: insert right after the opening paren (mixin-first, avoiding a
      metaclass= kwarg); reviewer validated a patch across 6 header shapes.
   F2 (blocker) a generated back-reference `from .policy import
      ProcurementHomeGate` passes verify_move (static binding + compile only)
      but fails at real import time (circular). Fix: refuse on back-references
      to the source module and require lifting the symbol first
      (ProcurementHomeGate is an Enum -> policy_types.py), and add a real
      import smoke test to verify_move.
   F3 generated modules lack `from __future__ import annotations` (Phase 9's
      hand-written policy_equipment.py has it).
   P0a prerequisite: 8 constants must move to policy_constants.py first —
      the tool correctly refuses until then.
  Also: the roadmap's Phase 10 selector `_deferred_home*` matches no method;
  _deferred_home_items / _deferred_home_item_sites are INSTANCE ATTRIBUTES —
  the phase line mixes state ownership with method selectors. Drop it from
  the selector argv (hard refusal is the correct default for unmatched
  selectors).
- Tool hardening (b6ef5be + 8d3b913): ACCEPT and pushed. F1 (base inserted
  inside the parens, six header shapes pinned), F2 (back-reference refusal +
  a REAL import smoke test in verify_move), F3 (future-annotations) all
  closed with executed lone-reverts; 8 constants + ProcurementHomeGate
  lifted (pickle compat proven at the production protocol 5, not just the
  pin's protocol 0). Phase 10 dry-run now: 39 matched, zero back-references,
  valid header (HomeMixin first, inside the parens), import smoke PASS.
  CORRECTION (see the correction event): re-export is required for FOUR
  constants + the Gate, not one; four have no external consumers. Do NOT
  prune policy.py's now-unused imports after the Phase 10 render
  (UNUSED_DIVE_LIMIT in particular) — eight test modules import them from
  hengbot.policy.
  PHASE 10 GO CONDITIONS (from review): (1) correction recorded [done];
  (2) no import pruning [in the phase prompt]; (3) reconcile the roadmap's
  Phase 10 expectation (65 methods / -2,419 / +2,460) against the measured
  39 / -1,992 / +1,999 — account for all 26 missing names (already moved in
  an earlier phase, renamed, or deleted) before executing, per
  plan-source-of-truth; (4) the roadmap's Phase 10 review obligation to diff
  home_entry_capture.STATE_FIELDS' 30 names is still owed.
  Note: roadmap §2's "four pickled classes stay in policy.py" is now stale —
  ProcurementHomeGate and ExplorationPathOutcome live in other modules with
  aliases.

### Phase 10 selector correction (supervisor, 2026-09-08)

The Phase 10 prefix list reaches only 39 methods, yet the phase's own stated size is 65. The
STEP-0 accounting closes exactly: 39 matched + 2 already moved in Phase 9
(`_home_rearm_weapon_score`, `_home_rearm_key`, in 81b77a4) + 24 genuine Home-cluster methods the
literal prefixes miss = 65. The selector list was an incomplete rendering of the documented intent,
so Phase 10 executes with these 24 EXACT names appended to the prefix list (drop `_deferred_home*`,
which names instance attributes, not methods):

- `_file_home_errand`
- `_ensure_home_visit_request`
- `home_route_refusal_state`
- `consume_home_knowledge`
- `_open_home_page_is_complete`
- `_record_digger_home_withdraw_failure`
- `_has_withdrawable_digging_tool`
- `_has_withdrawable_treasure_detection`
- `consume_pending_home_visit_report`
- `consume_pending_home_procurement_fallthrough_report`
- `_current_town_has_home`
- `retention_reservation_state`
- `_entire_stack_is_surplus`
- `_inventory_overweight`
- `_spare_equipment_deposit_shape`
- `_idle_deposit_protected`
- `_defer_unobserved_home_withdrawal`
- `_invalidate_home_observation`
- `_stage_home_operation`
- `_observe_home_history`
- `_capture_home_history_intent`
- `_retain_identification_source_owner`
- `_activate_home_batch_item`
- `_defer_home_item`

This realizes the roadmap's own 65-method figure; it is a correction of the selector rendering,
not a scope change. Anything these 24 + the prefixes still leave behind is residue for §10.
