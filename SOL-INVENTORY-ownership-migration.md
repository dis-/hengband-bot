# Ownership migration inventory (design 5.5) — built in S1, before any enforcement

Companion to `SOL-DESIGN-ownership-contract.md` rev 6, section 5.5. It exists so that
S4 ("removal") cannot break a consumer nobody listed. Nothing here is a change; it is a
census, taken on **63dae5d** (the S1 base) and re-measurable with the commands quoted.

Three questions, one per part:

1. who reads an **operation owner as a string** today, and does that reader want the
   identity (`claim_id`) or the label (diagnostics)?
2. where is the **retirement rewrite** called from, and what pins it?
3. what does the **S0 classifier** depend on?

Re-measure with:

```
grep -n "owner" src/hengbot/cli.py src/hengbot/input_executor.py
grep -rn "_departure_supplier_counterfactual\|preview_may_select" src/hengbot
grep -rln "owner-retired" tests
python scripts/ownership_claim_lint.py
```

---

## 0. The six owner notions, and what S1 added

Design section 2 lists six. S1 added a seventh **on purpose**: the claim's `owner`, which
is the one the others are to collapse into. Until then:

| # | notion | where | S1 status |
|---|--------|-------|-----------|
| 1 | `Operation.owner` = the decision's final reason label | `input_executor.py:376-389`, set in `cli.submit_operation:2103-2115` from `decision["reason"]` | untouched; part 1 below decides each reader |
| 2 | `TownTurnArbiter` reason-prefix families | `town_arbiter.py:66-125` | untouched; the claim register **derives** its owner enum from these (`owner_families()`), so they cannot drift apart |
| 3 | `StoreVisit.owner` + emit clauses + alias table | `policy_types.py:193-226`, `emit_ownership.py`, `town_arbiter.py:243-249` | untouched; S3 |
| 4 | `OwnerExpectationRegistry` | `policy_types.py:262-330` | read-only: the claim's `Observe` goal copies its pending `expected_changes` through the new `pending()` reader; nothing is written |
| 5 | `TownTravelProgress` | `policy_types.py:147-181` | read-only: its `goal` is one source of a `Reach` goal |
| 6 | `EscapeState` owner bookkeeping (`policy_types.py:410…`), `prompt_owner_handoff` | `cli.py:1946-1968` | untouched; S2/S3 |
| 7 | **the claim** (new) | `claim_register.py`, written into the decision row by `policy.choose_key` | records only |

---

## 1. Consumers that match an operation owner as a string

Verdicts: **re-point** = must read `claim_id` (identity) before S4 deletes the
label-based answer; **diagnostic** = may keep the label, because it is printed, logged
or matched against a reason for a human, not used to decide who owns anything.

### 1.1 `input_executor.py`

| line | site | what it decides | verdict |
|------|------|-----------------|---------|
| 376-389 | `Operation.owner: str` | the field itself | **re-point**: gains `claim_id`; `owner` stays as the label |
| 393-398 | `OperationReference.owner` | half of the barrier identity | **re-point** |
| 419 | `"owner": self.reference.owner` in the emitted receipt | wire identity the game echoes back | **re-point** (the receipt must carry `claim_id`) |
| 483 | `(intent.sequence, intent.owner) != (reference.sequence, reference.owner)` — `InputBarrier.accept` | **admits or drops an accepted watch** | **re-point**: this is identity, and a relabelled decision silently fails to match |
| 497-501 | `settle`: `(sequence, owner, executor_scope, admission_boundary)` vs the watch | **settles or refuses a receipt** | **re-point**, with 483 |
| 621 | `operation.owner.startswith("identify:full")` | whether to keep an identify continuation | re-point *or* keep as a reason test — the decision is about the *action*, not the owner; S3 decides with the identification family |
| 780 | `owner == "return:recall"` | recall feature gating | same as 621 (departure family, S2) |
| 824 | `f"input owned by {self.active.owner}"` | a busy message | **diagnostic** |
| 978 | `self.active.owner.startswith("identify:full")` | continuation routing | S3, with 621 |
| 1001 | `self.active.owner.startswith("town:enchant-launcher-")` | continuation routing | S3 (curse-enchant) |
| 1069 | `self.active.owner == "shop:one-shot-buy"` | continuation routing | S3 (shop-buy) |
| 1080 | `self.active.owner.startswith("equipment-transaction:")` | continuation routing | S3 (equipment-txn) |
| 1107 | `board["_completed_operation_owner"] = operation.owner` | what the next board reports | **re-point** (the board should carry the claim) |
| 1170 | `f"<stuck-prompt> owner={active.owner} ..."` | a stop detail line | **diagnostic** |

The four continuation sites (978/1001/1069/1080) are the ones design 5.5 names. They are
**not** ownership decisions: each asks "is this operation the kind that needs this
follow-up?" A claim's `owner` alone could not answer them (one family posts many kinds of
operation), so they migrate with their family's producer, which will declare a
`Terminal(effect)` goal specific enough to answer instead.

### 1.2 `cli.py`

Sites that compare or key on an owner string:

| line | site | verdict |
|------|------|---------|
| 1809 | `"recall" in owner and key.startswith("r")` in `_posting_effect_signature` | **re-point** — a substring test on a label deciding how strictly an effect is observed |
| 1870, 1914-1918, 2015-2018 | `_posted_by_owner[owner]`, `_last_posted_owner` | **re-point** (the posting contract's identity) |
| 1880, 1941, 1976 | `_settled_transport_by_owner[owner]` | **re-point**, with the above |
| 1934-1941 | `owner = str(receipt.get("owner"))`, `_settled_post` | **re-point** (receipt identity, pairs with `input_executor.py:497-501`) |
| 1946-1968 | the prompt-owner contract: `owner != self._last_posted_owner and prompt_owner_handoff != self._last_posted_owner` | **re-point** — design 9 names this explicitly; it is identity, and `prompt_owner_handoff` exists only because the label cannot express "the same claim, continued" |
| 1983, 1996 | `"owner": owner` inside a refusal incident | **diagnostic** (they name the refusal to a reader) |
| 2167 | `owner = str((decision or {}).get("reason", "unknown"))` — where the label becomes an owner | **re-point** (the single place the operation gets its identity) |
| 2185-2190, 2221 | `_quest_entry_continuations`, `_home_modal_continuation`, `_store_buy_continuations`, `prepare`/`posted` | as `input_executor` 978-1080: migrate with the family |
| 2313 | `owner not in {…}` (quest entry) | S3 (quest-request) |
| 2332 | `owner != "shop:one-shot-buy"` | S3 (shop-buy) |
| 2480, 2519 | `owner = str(chain["owner"])` for staged prompt chains | **re-point** (design 4 lists staged chains among the paths that bypass `choose_key`) |
| 3186 | `"reason": operation.owner` | **diagnostic** |
| 3567 | `pending_batch_row["input_owner"] = send.executor.active.owner` | **diagnostic** |
| 4060-4068 | `incident.get("owner", incident.get("answer_owner", policy.last_reason))` | **diagnostic** |
| 4165 | `send.last_result.operation.owner` | **diagnostic** |
| 399, 402 | the two blocked-reason explanations | **diagnostic** (prose) |
| 886, 1233, 1648, 1669, 1699 | decision-row fields (`requested_owner`, `store_visit.owner`, `town_emit_ownership`) | **diagnostic**, and they stay: the row is evidence |
| 1632, 3282, 3288, 3992, 4105 | `prompt_owner_handoff` plumbing | **re-point** with 1946-1968 |
| 2949-2983 | `_acquire_control_owner` / `<input-owner-busy>` | **unrelated** — an OS mutex owner, not a decision owner. Listed so a future grep does not re-open it |

Count: 35 `owner` sites in `cli.py` that are not imports, comments or the ledger wiring;
15 of them **re-point**, 14 are **diagnostic**, 4 migrate with their family, 2 are the
unrelated control-port mutex.

### 1.3 `policy_types.py` / `emit_ownership.py` / `town_arbiter.py`

| site | verdict |
|------|---------|
| `StoreVisit.owner` (`policy_types.py:196`) and every `visit.owner` read | **re-point** at S3; the design folds the store-visit owner into the claim |
| `town_arbiter.py:243-249` alias table (`shop-handler`→`shop-buy`, …) | **delete at S4**: it exists only to reconcile two owner vocabularies |
| `town_arbiter.py:182-188` `owner_for_reason` | **keep through S3** — the claim register derives its enum from these registrations; delete at S4 with the prefix registry |
| `OwnerExpectationRegistry.post/may_select` keyed by owner string (`policy_types.py:268-330`) | **re-point** at S3 (the `Observe` goal replaces it) |

---

## 2. The retirement rewrite

Design 3.3: the in-gate rewrite at `policy.py:2592-2659` (this base: **2591-2658**)
achieves by other means what the bar table will do. It is migrated in S2/S3, **not
before**.

### 2.1 The path

Line numbers are this base **after** the S1 commit, so they can be checked directly.

```
policy.py:2632  arbiter.preview_may_select(self.last_reason, vector, retirement_key=…)
policy.py:2637  retired_owner = arbiter.owner_for_reason(self.last_reason)
policy.py:2638  self._arbiter_close_store_visit(retired_owner, "arbiter-retired-claim")
policy.py:2639  supplier = self._departure_supplier_counterfactual(snapshot)
policy.py:2641  step    = self._shopping_approach_step(snapshot, supplier)   [guarded]
policy.py:2694  self.last_reason = "town:blocked:owner-retired"  (transaction owns relocation)
policy.py:2697  self.last_reason = "shop:approach"   <- emits without a claim (design 3.3.1)
policy.py:2700  self.last_reason = "town:blocked:owner-retired"; key = WAIT_KEY
```

### 2.2 Every call site

`preview_may_select` (`town_arbiter.py:464`):

- `policy.py:2591` — the unresolved quest-candidate re-instatement
- `policy.py:2632` — the retirement gate itself
- `policy.py:2646` — the `shop:approach` counterfactual's own admission check

`_departure_supplier_counterfactual` (defined `policy_town.py:2836`):

- `policy.py:2639` — the retirement rewrite
- `policy.py:6382`
- `policy_shop.py:1232`
- `policy_shop.py:1279`
- `policy_town.py:4768`

Store-visit state written from the counterfactual's neighbourhood: `policy_town.py:2836…`
and the approach bookkeeping it reaches (design names `T:2803`; on this base the
`_departure_supplier_counterfactual` definition has moved to 2836, so quote the symbol,
not the line, when this path is migrated).

Terminal reasons this path can emit: `town:blocked:owner-retired`,
`fixedquest:*:unsatisfiable`, `shop:approach`, and — from `policy_town.py:1131` —
`town:blocked:no-actionable-claim-owner`, which is **not** in
`POLICY_FINAL_STOP_REASONS` (`policy_constants.py`), exactly as design 3.3 warns.

### 2.3 What pins it

`grep -rln "owner-retired" tests` on this base finds **34** files: 22 `test_*.py`,
3 shared test modules and 9 fixture extractors (plus fixtures and one `.md`). The design
says 28; the difference is the extractors and the two support modules, which the design's
count did not include. The full list, so a migration can run them as one batch:

*Tests (22)* — `test_alchemist_observed_shop_alternation`,
`test_calibration_restore_deposits_recorded`, `test_destruction_gate_procurement`,
`test_entrance_travel_retired_recorded`, `test_equipment_in_home_stage1`,
`test_equipment_swap_loop_incident`, `test_home_knowledge_scan`,
`test_morivant_travel_retired_recorded`, `test_pattern_a_owner_retired_recorded`,
`test_policy_home`, `test_policy_shop`, `test_policy_town`,
`test_posted_effect_unobserved`, `test_restore_stall_recorded`,
`test_retirement_self_clearing`, `test_shop_one_shot`, `test_town_arbiter`,
`test_town_plan_exhausted_wander`, `test_town_progress_invariant`,
`test_unaffordable_claim_tour_recorded`, `test_unsafe_recall_fallback_recorded`,
and `tests/ARB2_LEGACY_PIN_DISPOSITIONS.md` records the dispositions of the earlier ones.

*Shared modules (3)* — `tests/historical_emit_fixture.py`,
`tests/store_visit_alternation_gate.py`, `tests/town_emit_ownership_matrix.py`.

*Extractors (9)* — `extract_entrance_travel_retired_fixture`,
`extract_morivant_travel_retired_fixture`, `extract_organization_departure_fixture`,
`extract_posted_effect_unobserved_fixture`, `extract_recall_stockout_set_end_fixture`,
`extract_town_loot_supplier_alternation_fixture`,
`extract_town_plan_exhausted_wander_fixture`, `extract_unaffordable_claim_tour_fixture`,
`extract_unsafe_recall_fallback_fixture`.

---

## 3. The S0 classifier's dependency on `arbiter.owner`

`stop_shape.py` reads two different things, and only one of them is a dependency:

| what | where | migration |
|------|-------|-----------|
| **producer identity** = `reason_owner_family(reason)`, refined by the reason's leading segment inside the two catch-all families | `stop_shape.py:66, 128-137` | **re-point to `claim_id`'s owner** before S4 deletes the prefix registry. It is the classifier's only *decision* input about ownership |
| `arbiter.owner`, `arbiter.producer_owner`, `arbiter.retired` from the stopping row | `stop_shape.py:146-161, 221-222, 290` | **evidence, not a trigger** (its own docstring says so) — except `arbiter_retired`, which *is* read as a rule input at `stop_shape.py:309-313`. That one **re-points** to the claim's `state == "retired"` |
| `arbiter.owner` change counting | `ownership_metrics.py:227-240` | **superseded** by the S1 claim ledger's implicit-handoff metric; keep until S2's go/no-go is taken off the new number, then delete with the rest |

S1 leaves all three in place and adds the claim beside them, so the two measurements can
be compared on the same run before either is removed.

---

## 4. What S1 itself introduced that S2+ must revisit

- **`unregistered` as a declared owner.** 14 of the 57 marked producers carry
  `@claims(ClaimOwner.UNREGISTERED)` — 34 of the 169 covered `self.last_reason` sites —
  because no registration claims their reasons today (`detected:`, `chest:`, `summoner:`,
  `breeder:`, `flee-sustain`, the floor-item and victory-loot producers). That is the
  honest current answer of `owner_for_reason`, not an invented family — but S2 must give
  each of them a real one, and the marker is where to do it.
- **`misc` and `unregistered` hide the dungeon producers.** The design's 5.2 breakdown is
  by family; in the dungeon that collapses `explore`, `melee`, `seek-loot`, `hunt` and
  `wait` into one family. The claim ledger therefore also records `producer`
  (`stop_shape.producer_identity`) and the report prints the same metric by producer and
  by `claim_id`. The family number alone is **not** a safe S2 gate for the dungeon.
- **`OwnerExpectationRegistry` has its own owner vocabulary.** Its keys are neither
  families nor reasons: `"equipment-transaction"`, `"return:recall"`, `"stair-command"`,
  and computed reason strings (`policy.py:2542, 4588, 4618, 11995`,
  `policy_town.py:4243-4261, 4939, 4972`, `policy_home.py:53, 1509`,
  `policy_navigation.py:246`, `policy_shop.py:4512`, `policy_combat.py:1614, 1627`,
  `policy_quest.py:4779`). S1's `Observe` goal therefore looks the pending expectation up
  only under the reason itself and the reason's leading segment, so it can never borrow
  an unrelated owner's expectation. S3 replaces the registry with the goal and the
  vocabulary disappears; until then a decision whose expectation is keyed some other way
  records `Terminal(reason)` instead of `Observe`, which understates `Observe` goals
  rather than inventing one.
- **Trigger-set identity.** Design 5.4.1 requires `(index, race_id)` pairs. Today
  `policy.py:12461` stores `frozenset(monster.index …)` — indices only. S2 must
  widen that tuple before the bar key can be trusted, because Hengband reuses the index
  of a dead monster.
- **Two rows can share a `decision_sequence`.** The skill probe and the look probe return
  before `_choose_key` increments it (`policy.py:3152`), so their rows — and their claim
  records — carry the previous decision's number. The ledger records them as the separate
  decisions they are; a reader must not key on `decision_sequence` alone.
- **`choose_key` may run twice for one row** (the second call after
  `refuse_key_posting`, `cli.py:4065`). The register continues the same claim when
  the owner and goal are unchanged, so the row is unaffected; only an id may be skipped.
