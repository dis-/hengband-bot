# Ownership contract — S3 design (rev 1, final, 2026-09-26)

Design only; no source/test edits. Baseline `main` 6de8446a. Rev 1 applies the fable review of rev 0 and
the user decisions of 2026-09-26 (section 5). Companion to `SOL-DESIGN-ownership-contract.md` rev 10.2
(sections 2, 3.1-3.3.1, 5.5, 6 "S3") and `SOL-INVENTORY-ownership-migration.md`. Aliases: **P**
`policy.py`, **T** `policy_town.py`, **S** `policy_shop.py`, **H** `policy_home.py`, **E**
`policy_equipment.py`, **HV** `home_visit.py`, **A** `town_arbiter.py`, **PT** `policy_types.py`, **EO**
`emit_ownership.py`, **CR** `claim_register.py`, **CL** `claim_ladder.py`, **GT** `claim_goal_typing.py`,
**C** `cli.py`. Line numbers are 6de8446a.

User decisions carried verbatim: contract is global; a violation stops the bot; progress = distance +
expected observation; survival preempts-and-resumes; 2026-09-26 "着手順の交換は許可する。実機観測が
必要ない部分を可能な限り先に". Every S3 step is built and proven on recorded captures; every behaviour
change ships behind a stage attribute that defaults OFF.

**Definition — record-only.** Keys, reasons and decisions are byte-identical on every recorded replay
(the hash test `tests/test_ownership_s2a_classification.py:126-133` and the 2026-09-25/26 recorded pins).
Claim ids, closing reasons and their aggregates **may** change, and the pins that count them are updated
by name in the dispatch: `test_unaffordable_claim_tour_recorded.py:121-136` (`S2A1_NEXT_ROW_COMPLETE`
= 1354, `S2A1_ENDINGS`) and `test_ownership_s2a1_closure.py:748-752` (`sale-observed` rows). Nothing else
pre-existing changes.

## 0. What S3 is, in one sentence

A town errand's identity is held in six places at once — `StoreVisit.owner` (PT:196, aliased at A:333-347
and S:150-178), `OwnerExpectationRegistry` keys (PT:268-375; posts at P:2636, P:5560/5590, P:13135,
T:4440-4458, T:5275/5309, H:53/1532, S:4548, …), `TownTravelProgress` (PT:147-181, T:3948), the arbiter's
per-family budget and `_retired` dict (A:349-523), the retirement rewrite (P:2722-2796) and
`HomeVisitExecutor.attempts_used` (HV:85-164; **missing from the inventory — added by S3.0**) — and the
claim (CR) is a seventh that only records. S3 makes the claim the one place and turns the others into
readers of it (deleted in S4).

## 1. Measured (what S3 must close)

S2b.1 on the 19:39-20:41 session (16,750 rows, 62 min): 63 S3-family violations. The whole
`incident-20260925-2041-…ownership-claims.jsonl.gz` (39,168 rows, several sessions, `ladder_numbers`):
S3 violations 136 — `store-router>detectors` 22, `home-scan>store-router` 17, `home-scan>home-visit` 16,
`store-router>home-scan` 13, `calibration>equipment-txn` 7, `home-visit>store-router` 6,
`home-visit>departure` 5, `store-router>shop-buy` 4, `home-errand>home-visit` 4, `cross-town>store-router`
4, …; S3 retargets 47 — `departure` 36, `equipment-txn` 7, `calibration` 4. Four shapes:

- **(A) rewrite over an in-flight operation** (`store-router>detectors` 22): a `detectors`/`town-plan`
  rewrite (P:2644-2645, T:1082, T:1207) replaces the key while a `store-operation` Observe claim is open;
  CL:495 `never_suspended` makes that a violation by design. The 12:56 stuck-prompt is this shape live.
- **(B) an errand step that never closes** (`home-scan>*`, `*>home-scan`, `home-visit>store-router`, ~52):
  the scan (opened at P:9553, no registry post) is never completed where knowledge becomes current
  (H:271); the router's `Reach(entrance)` to the Home is not completed when the atomic composer posts
  entry+op+exit from the outside cell (H:2415, HV:198-213 "outside-ready"), so P:3353 `entered-store` never
  sees a store board; `_close_store_visit("completed")` deliberately closes nothing (P:3197).
- **(C) one operation, many goals** (`calibration>equipment-txn` 7, retargets 47): P:2636 posts a fresh
  transaction expectation on **every** `equipment-transaction:*` key, so each key is a new Observe goal and
  CR:379-391 opens a new claim — a retarget per step of one transaction. Departure's 36 retargets are the
  `rje`/`rj` shape (read = Observe floor-change, cancel = Terminal).
- **(D) leaving with an operation open** (`home-visit>departure` 5, `*>bookkeeping` 3).

## 2. Steps

### S3.0 — Observe claims with real identities and closing paths (record-only)

One checked-in constant `OPERATION_CLAIMS` (beside GT), one row per multi-board operation:

| operation | producer | goal (`Observe`) — identity, expectation, `within` | `complete` at | `release` / `expire` at |
|---|---|---|---|---|
| shop one-shot buy / sell / batch-inscribe | S:4581 `_atomic_shop_transaction_key`; post S:4548 | `(store_type, operation_key, posted_sequence)` from the visit; expectation `gold`, `inventory`; `STORE_STUCK_LIMIT` | S:3160 (sale); the buy confirmation that sets `operation_effect_observed` (site named in the dispatch, S:224-260 neighbourhood) | `_close_store_visit(outcome≠completed)` P:3188; S:234 `released-operation-effect-unobserved` → `expire` |
| Home atomic withdraw / deposit / disposal | H:1225 `_atomic_home_withdraw_key` (pending set H:1771), H:2101 `_atomic_home_deposit_key` (pending set H:2189/2281/2374), H:2415 compose; blocked-owner posts T:4440-4458 | the pending tuple `(STORE_HOME, signature, before_count, take_count, posted_turn)`; expectation `inventory`; `STORE_STUCK_LIMIT` | **HV:280 `observe_outside(effect_observed=True)`** and the clears with an observed effect: P:4520, P:4994/5026, H:1861 | the clears without effect (`policy_observation.py:612`, S:1296, T:1879) → `release("target-unobserved")`; `expire` on `STORE_STUCK_LIMIT` |
| Home knowledge scan | opened at P:9553 (`_home_knowledge_scan_requested`), reason `home:request-knowledge`; **no registry post today** | `(STORE_HOME, "knowledge", scan_epoch)`; `STORE_STUCK_LIMIT` | H:271 `_home_knowledge_current = True` | request cleared without a page → `release` |
| home-errand filed work | H:48-57 post `home-errand:<purpose>` | `(STORE_HOME, "errand", request.signature)`; `STORE_STUCK_LIMIT` | the errand's own `post`/observe (H:1805-1811) | `home-errand:stopped:` → `release` |
| equipment transaction (strip → wield → deposit) | E:1553 `_equipment_transaction_town_owner_key`; session E:1508-1531; post P:2636 | **`(session.opened_sequence, plan set fixed at open)`** (E:1518-1523) — never the owned-item list (P:4852 appends per takeoff → a new claim per step = today's retarget); the per-key `OWNER_EXPECTATION_MAX_TURNS` is recorded as a *step* bound; the claim's `within` is `EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT` (A:579) | E:431-445 `_equipment_ownership_release_due` empties the owned list | session = None with owned items left (E:1366/1508, `policy_calibration.py:348/591/829-882`) → `release("abandoned:<terminal>")` |
| calibration strip / restore | `policy_calibration.py` session sites 673/723 | same identity, source `calibration` | restore observed (H:1845 `_observe_calibration_restore_batch`) | `calibration:abort` → `release` |
| staged prompt chain (identify `uqt`, enchant, curse) | P:2435 `_staged_prompt_chain`, C:2480/2519 | `(chain_owner, stage_count)`; `within` = stage count in decisions | the chain's tail posted | tail dropped (6168c9fa path) → `release` |
| recall read (town and dungeon) | T:5275 (`return:recall`), T:5309 (town reads) | unchanged: floor-change, 350 game turns | unchanged (P:3358-3360) | `town:cancel-*` → `release("cancelled")` — today a retarget |

Rules: (1) the goal's identity is the operation's own tuple, so a second key of the same operation
**continues** the claim (shape C); the per-key registry expectation stays (still popped by `may_select`,
still recorded `satisfied`), it just no longer *is* the goal. (2) `_close_store_visit("completed")`
completes the standing store-operation Observe when `visit.operation_effect_observed`, otherwise expires
it `completed-unobserved` (shape D). (3) `Reach(entrance)` completes when the player stands on the
entrance cell **or** the visit posts its composed operation from the outside cell — read from
`HomeVisitExecutor.context_token == ("outside-ready", g)` (HV:198-213) / `_home_entry_operation_posted`
(A:785) / `_intentional_entrance_activation` (S:4512) — labelled `entered-outside` (shape B). (4) A recall
cancel releases the read's floor-change claim `cancelled`. (5) **`claim_verdict_conflict`** (user decision
3): when a producer's own verdict on an operation (`target-unobserved`, `unfulfilled` HV:286-289,
`approach_fails` T:2776/2794) contradicts the claim's ending (`complete`), the row records
`{claim_id, claim_ending, verdict, attempts_used}` — `attempts_used` (HV:85) is one side of the conflict,
the claim the other. Counted only; nothing changes. (6) `HomeVisitExecutor` is added to the inventory as
owner notion 8 (`attempts_used`, `previous_completed_delta`: budgets, re-pointed at S3.3, deleted at S4).

Pins: a class test per row (declare → key → confirm → `complete`; declare → drop → `release`; declare →
`STORE_STUCK_LIMIT` boards → `expired`); the frozen S3 rows of the 20:41 ledger re-read through
`rejudge_recorded_violations` (as S2b.1b did): S3 violations ≤ 5 (from 63), every remaining pair named;
`posted-effect-unobserved-20260923` and `home-withdraw-failed-stock-present-20260925` record ≥ 1
`claim_verdict_conflict` each (the 17:30 take was observed and the verdict said failed).

### S3.1 — `non_discardable` set so it cannot flip mid-transaction (record-only)

Rev 10.2 found that deriving it from `_equipment_transaction_owned_items` per row flips it inside an open
claim and CR:389-390 then abandons the claim. Structural fix:

- `non_discardable` is a property **of the claim**. A producer declares it through a per-decision slot
  (`_declare_non_discardable()`, reset at P:2428 like `_decision_goal`, read only at P:3470) **on every board
  on which the condition holds**: `_equipment_transaction_owned_items` non-empty (E:1553 rung, P:6274-6281),
  `_home_atomic_withdraw_pending` / `_home_atomic_deposit_pending` set (H:1771, H:2189/2281/2374), a
  calibration session with stripped slots, a staged prompt chain (P:2435). Declaring on every board is what
  makes a claim re-opened after `survival-displaced` (CL:517-523 releases the holder) non-discardable again.
- **Monotone promotion, idempotent.** `continues` (CR:389-390) and `resumable_index` (CL:542-556) drop the
  `non_discardable` term. A continuing claim whose slot says True is promoted in place
  (`replace(claim, non_discardable=True)` in `declare`, like `survival` CR:433) **and re-ranked**:
  `rank`/`rung` are recomputed by `rung_of(owner, reason, non_discardable=True)` (CL:434-461 → the
  `owns_transaction` rungs CL:214-217) on that promotion, because `declare` otherwise keeps the opening
  rank and only `resume` (P:3504-3516) updates it. A claim that opened or was promoted non-discardable
  stays so until it **closes**; no path clears it on an open claim.
- Rows change `rank`/`rung`; keys do not. Pins: `test_unaffordable_claim_tour_recorded` — zero equipment-txn
  retargets on the recorded tour (the two of rev 10.2 gone); `stuck-prompt-staged-tail` records a
  non-discardable identification claim on 7286-7288.

### S3.2 — `StoreVisit.owner` folded into the claim (record-only, then the stage switch)

- `StoreVisit` (PT:193) gains `claim_id: int | None = None` and `claim_owner: str | None = None`.
  `acquire_store_visit` (A:213; callers P:5191, P:5232, S:4238) and the recovery constructors (P:5059-5071)
  run before the exit declaration, so `_record_decision_claim` **re-stamps both on every decision while a
  store-family claim is open** (a store change opens a new Reach claim, CR:388, so a one-time stamp would
  go stale; a visit transfer A:238-243 then carries the new id, which is the errand's next leg).
- The row records `visit_owner_mismatch` when `alias(visit.owner)` (A:341-346) ≠ `claim.owner`.
- Stage `s3.2` ON: `_decision_owner` (A:333), `_arbiter_close_store_visit` (S:150), `_store_visit_arbiter_owner`
  (S:163) and the `town-errand` test in `_release_invalid_store_visit` (S:252) answer from
  `visit.claim_owner`; the alias tables go dead (deleted in S4). Pins: `tests/town_emit_ownership_matrix.py`
  and `test_town_emit_ownership_recorded` identical OFF; ON re-derives the same verdicts on the matrix.
  EO:38-56 `in_flight_clause` is untouched (S4 re-points it to the claim's `awaiting` state).

### S3.3 — the retirement rewrite path migrated (behaviour; stage `s3.3`, default OFF)

Today (P:2722-2796): `preview_may_select` rejects the winner → `_arbiter_close_store_visit` (P:2732) →
`_departure_supplier_counterfactual` (P:2733; also P:7392, S:1238/1285, T:5097; it **writes** state
through `_rearm_town_store_for_new_work` S:1300-1328) → `shop:approach` with no claim (P:2791) or
`town:blocked:owner-retired` (P:2788/2794).

**OFF (record-only, behaviour-neutral).** Two pure-function verdicts are recorded on every town row, and
nothing else: `contract_retired` — whether the standing claim is out of budget on its own measure (Reach:
a per-claim no-progress counter that increments when the row's `distance` (P:3545) did not fall, budget =
the family's CR `budget` from A:571-594; Observe: `within`); `contract_barred` — whether the decided
owner/goal matches an entry of the S2b.2 bar table. **Never `contract_key`**: computing the key the
contract would emit re-runs producers that write state (S:1300-1328, A:213, registry posts, staged
chains). Go/no-go for ON = count of rows with `legacy_retired ≠ contract_retired` on the eleven captures
below (zero required); the same rows also print `claim_verdict_conflict` (S3.0 rule 5) so the 17:30 class
is judged on the same substrate.

**ON.**
1. Retirement is the claim's: `_claim_owner_retired` (P:3279) answers from `contract_retired`; the
   arbiter's locomotion vector (T:116-167) is not consulted for S3 families.
2. A retired/abandoned errand claim enters the S2b.2 bar table keyed `(owner, goal, clearance key)`. With
   the S2b.2 skip switch ON for town rungs, the barred producer does not produce and the ladder falls
   through — what the counterfactual computes by hand today.
3. **A town-errand bar is not lifted by locomotion alone.** Today's clearance key defaults to the progress
   vector (T:591-593 → T:88-167), whose locomotion part changes on every step, so one step would lift the
   bar and the walk ⇄ retire alternation would return. The errand lift key is the **durable** part only
   (T:106-115: core without position/turn, fingerprint, departure block, Home knowledge, blocked reason,
   descent flags) plus the quest and departure tuples T:520-602 as they are. *This changes the lift
   condition — user decision to confirm (section 5, item 1).*
4. The counterfactual's `shop:approach` becomes a producer: it declares through `_shopping_approach_key`'s
   `writer_family` (S:4460) at the store-router ordinary rung (CL:309-310). `_rearm_town_store_for_new_work`
   stays (plan state, not ownership).
5. **The terminal's new home.** `town:blocked:owner-retired` is emitted by a new exit helper
   `_claim_barred_terminal_key(snapshot, key)` at the place of P:2722-2796, when the decided owner is barred
   and no other town rung produced; it is distinct from `town:blocked:no-actionable-claim-owner` (T:1207,
   the liveness invariant, unchanged). The string stays: the 34 pins (inventory 2.3;
   `tests/test_policy_town.py:13912/14562/14977/15060` assert the literal) keep their meaning.
6. The `_retired` readers outside the rewrite — P:4132/7094/7260 (quest), H:566, T:537, T:3049
   (`_departure_supplier_core`) — read the bar table with the same key shape; a test asserts the two
   answers agree on every recorded town board OFF.
7. The 17:30 class (user decision 3): the operation verdict (`target-unobserved` H:1522/1537, HV:286-289
   `unfulfilled`, `approach_fails` T:2776/2794) is **derived from the claim's ending** — a completed claim is
   never re-judged failed; `attempts_used` is not incremented by a completed claim's visit.
8. **Plan order rule (user decision 1).** The execution order of errands is `_build_town_errand_plan`
   (T:3185: Home first if needed, stores by phase and proximity, Home after the Alchemist for post-alchemist
   needs); the ladder rank does not order them. A plan rebuild may reorder stops **only after the current
   errand's claim closes** (complete / release / expire / retired); while an errand claim is open the rebuilt
   plan keeps that stop at its index, and the row records `plan_rebuild_deferred` when a rebuild wanted to
   move it. ON enforces the deferral; OFF counts it.

**Proof of ON — the eleven recorded captures are the substrate** (no live boards): `town-approach-retired-20260925`
(claim 925's distance falls → never retired → the walk reaches store 7), `morivant-return-walks-away-20260925`
(distance rises → the claim retires → bar → the pin asserts the **final stop reason
`town:blocked:owner-retired` and a bound of ≤ 219 decisions**, the recorded window), `entrance-travel-retired-20260922`,
`morivant-travel-retired-20260922`, `incident-20260920-1846-owner-retired`, `incident-20260921-0855-home-entrance-owner-retired`,
`posted-effect-unobserved-20260923` (the Observe expires → release → next owner instead of the 18:15 stop),
`town-plan-exhausted-wander-20260923`, `unaffordable-claim-tour-20260922`, `unsafe-recall-fallback-20260923`,
`recall-stockout-set-end-20260921`. The 34 rewrite pins stay green OFF; ON is exercised by new classes,
never by loosening them; any pre-existing pin that must change under ON is declared by name and board.
The live 2 h is a **post-ON confirmation** (S3 violations ≤ 1/h, `claim_verdict_conflict` 0), not the gate.

### S3.4 — the S3-family ranks (user decision 1, final)

Town errands keep **one rank** (`TOWN_RANK`, CL:402; families CL:94-108): no errand may hijack another
errand's open claim at the same rank — that is a violation (CL:500-534) and, under S2b.3, a stop. Two
exceptions rank above `TOWN_RANK`, both reached only through `non_discardable` (S3.1): the equipment
transaction after the strip (CL:214-217) and — new rung, `owns_transaction=True` on the home-visit /
home-errand / calibration families — a Home atomic operation in progress. **Rewrites are refused on top of
those**: `_refuse_no_progress_cycle` and `_town_procurement_decision` (P:2644-2645) return the key unchanged
when `register.current.non_discardable` and record `rewrite_refused` (shape A; the 12:56 class). Departure in
town stays at `TOWN_RANK` (CL:349-353). Order among errands is the plan's (S3.3 item 8), never the rank's.

## 3. The 2026-09-25/26 live stops against the steps

| # | stop | class | S3 step | prevented by S3? |
|---|---|---|---|---|
| 1 | 06:24 `owner-retired` walking to store 7 | arbiter progress = Manhattan sum; claim distance fell 33→20 | S3.3-1 | **yes**: retirement judged on the claim's distance. Fixed b5be3770 meanwhile |
| 2 | 10:22 `overweight-home-unreachable` on the Home entrance | Home bound spent by **successful** ops (`approach_fails` T:2776/2794) | S3.0 rule 5 → S3.3-7 | **OFF: detectable** (`claim_verdict_conflict`); **ON: yes** (a completed claim's visit is not a failed approach). Fixed c1a4abb5 |
| 3 | 12:56 stuck-prompt, identify staged tail key-replaced | rewrite over an in-flight chain (A) | S3.1 + S3.4 | **yes** ON (`rewrite_refused`); pinned on `stuck-prompt-staged-tail`. Fixed 6168c9fa |
| 4 | 14:52 recall read⇄cancel ×9 | departure retarget (36 in the ledger) | S3.0 recall row | **no** as prevention; each cycle becomes a visible `release("cancelled")` and S2b.3 stops it at the second. Root fix 8a8c15cf + user decision stand |
| 5 | 16:33 resume inside the Black Market | bootstrap | — | **no**: not ownership. S3.2 only stamps the recovered visit (P:5066) |
| 6 | 17:30 `home-withdraw-failed-stock-present` | confirmed take re-judged "target-unobserved" | S3.0 rule 5 → S3.3-7 | **OFF: detectable**; **ON: yes** (verdict derived from the completed claim). Fixed cef4849e |
| 7 | 20:41 `owner-retired`, Morivant walk away | declared goal wrong (previous town's terrain) | S3.3 | **not proven** until the ON pin shows the same stop within the bound; the arbiter and the claim agree today. Fixed 3a9d2ad4/a78594aa |
| 8 | 02:01 guardian recall ping-pong ×7 | destination latch; each trip a completed floor-change claim | — | **no**: no violation on those rows. Fixed 0d5473f8..b57da438 |
| 9 | 02:52 `departure-unsatisfiable` (weight) | need-supplier judgement (T:2973) after 15 Home visits | — | **no**: need evaluation is outside S3; S3.0 only makes the 15 visits' endings visible |

(Not town: 01:57 pickup-pile stuck-prompt, S2 scope.) Net: S3 removes classes 1 and 3 (and, ON, 2 and 6);
4, 5, 8, 9 stay with their landed fixes; 7 is open until pinned.

## 4. Order, deadline, risks

**Order.** S2b.2 (bar table, record-only, in flight) → **S3.0 + S3.1 + S3.2-record** in one dispatch
(merge surface with S2b.2 is `_record_decision_claim` P:3413-3582 only; S3.0 touches S/H/E/calibration
producers and P:3040-3400; S3.1 replaces P:3470 after S2b.2 merges) → **S3.3 + S3.4 + S3.2-stage** in one
dispatch, OFF (needs S2b.2's bar table and skip switch) → ON go/no-go on the eleven captures → ON → live
2 h confirmation → S2b.3 enforcement extends to the S3 families → S4 deletions per the inventory
(registry, alias tables, `TownTravelProgress`, `_retired`, `prompt_owner_handoff`, `HomeVisitExecutor`
budgets). S2b.3 for the in-scope families does not wait for S3. S3.0 may be split by family (store rows
first — 3/4 of the violations) without changing any other step.

**Deadline.** The 8-round limit is removed (user decision 2); the only limit is 2026-09-29 08:46. Plan:
S3.0-S3.2 dispatched 09-26, reviewed 09-27; S3.3/S3.4 dispatched 09-27, reviewed 09-28; ON go/no-go 09-28.

**Checkpoint cover** (RULE: every new policy attribute is listed): `StoreVisit.claim_id` /
`claim_owner` (dataclass defaults), the per-claim no-progress counter (CR field, class default 0),
`_claim_contract_stage` (`"record"` default; values `"s3.2"`, `"s3.3"`, monotonic — one attribute instead
of three booleans), the `non_discardable` slot (`getattr`, default None), `plan_rebuild_deferred` (row only).

**Risks.** (1) Claim ids re-allocate on every recorded replay (S3.0 identities, S3.1 dropping the
`continues` term): the named aggregate pins are updated per the record-only definition; readers go through
`rejudge_recorded_violations`, never id literals. (2) The 34 rewrite pins: OFF byte-identical is a hard gate;
ON gets new classes. (3) `_retired` readers (S3.3-6): ON answers from the bar table; the OFF agreement test
guards them. (4) The lift-condition change (S3.3-3) is the one place S3 alters a user-visible rule —
gated on the decision below. (5) `plan_rebuild_deferred` may delay a Home-first insertion by one errand;
counted OFF before ON. (6) Deadline pressure with S2b.2, the weight fix and S3 on one implementer; the
family split of S3.0 is the relief valve.

## 5. Decisions

Applied (user, 2026-09-26): (1) one `TOWN_RANK`, two non-discardable exceptions, rewrites refused on them,
execution order = the town errand plan, rebuild reorders only after the current claim closes — S3.3-8 /
S3.4; (2) the 8-round limit removed, deadline only — section 4; (3) the 17:30-type conflict recorded in
S3.0, fixed by deriving the verdict from the claim in S3.3 (OFF → ON after the captures show no
difference), duplicate ledgers deleted in S4 — S3.0 rule 5, S3.3-7.

**New decision needed (1):** S3.3-3 — a town-errand bar is lifted only when the **durable** part of the
clearance key changes (T:106-115 plus the quest/departure tuples), never by the player's own movement.
Today one step lifts it (the key defaults to the full progress vector, T:591-593). Confirm, or name a
different lift condition (e.g. the existing 50-turn safety clock used for threat-triggered owners).


## USER DECISION 2026-09-26 (S3.3-3, bar lift for town errands)

A town-errand bar is lifted ONLY when the durable part of the retirement clearance key changes (inventory, gold,
equipment, quest / departure tuples; T:106-115 and the quest/departure tuples), never by the player's own movement
(the position part of the progress vector, T:591-593). The 50-turn safety clock is NOT used for errands.
Consequence for S2b.2 (b78b1cfe): its errand bar currently reuses the arbiter's `_retired` entry, whose default key
is the whole progress vector; S3.3 must switch the errand lift to the durable part.


## DESIGN RULING 2026-09-26 (sol stop on S3a): `shop:travel:await-entry` and other entry waits

`shop:travel:await-entry` (and every `*:await-entry` / `travel-home:await-entry` wait at an entrance) posts NO store
operation; it waits for the store screen after arriving. It is therefore NOT a store-operation claim:
- goal = Observe(expectation=('store-entry', <target store type>), within = the existing entry-wait bound), source
  'store-entry' (never 'store-operation');
- it COMPLETES (`entered-store`) on the first board whose snapshot shows the target store open - the same test an
  entrance Reach claim uses (`_claim_entered_store_at`);
- it is an ordinary suspendable claim: a strictly higher rung (e.g. the detectors rewrite
  `town-progress-invariant:continue-observed-shop`, rank 0) preempts it into the stack instead of recording a
  violation; if the store is already open on the preempting board it has completed first;
- it expires (`expired`) past `within`, and is released with a named reason where the entry is abandoned.
Record-only: typing table row + closing; no key/reason change. This resolves the 11 `store-router>detectors`
violations of session 36788; report how many remain.


## DESIGN RULING 2026-09-26 #2 (sol second stop on S3a): plan handoffs are real violations

An open Reach claim of one town errand handed to another town errand before arrival (e.g. `store-router>home-scan`,
`cross-town>store-router`, player still away from the recorded target) is a genuine violation of the user rule
'a plan rebuild may reorder only after the current errand's claim closes'. S3a must NOT add a record-only release
that would hide it. Instead:
- tag such violations `kind: plan-handoff` (from/to both town errands, holder a Reach/Observe claim not closed,
  the town errand plan index/stops changed or the next stop differs) and count them on their own line;
- they are removed by S3.3 (behavioural: the plan rebuild waits for the claim to close), not by S3a;
- the S3a numeric acceptance (<= 5) applies to S3-family violations EXCLUDING `plan-handoff`.
Gate misses are NOT a reason to stop the round: build every specified step and report the remaining counts per
class with causes. Stop only when the design itself is silent or contradictory about WHAT to build.


## DESIGN AMENDMENTS 2026-09-26 #3 (review of S3a 8fa10c0d)

1. One-shot shop/Home operation identity must be fixed at COMPOSE time and never rewritten during the operation:
   use the pending store transaction / the visit's `opened_sequence` together with `operation_key` - NOT
   `visit.posted_sequence` (policy_shop.py ~4636 sets it, policy.py ~4863 resets it; the wait '5' and the posting key
   then get different goals and every one-shot records a retarget).
2. The S3a gate is measured on REPLAYS OF THE NEW CODE (recorded lifetimes, e.g. the unaffordable-claim tour and the
   2026-09-25/26 captures), not by re-reading base-code ledger rows (`rejudge_recorded_violations` cannot see new
   closings or new violations). Replays that skip `commit_staged_prompt_chain` must call it as live cli.py ~2644 does
   (or those rows are excluded and named).
3. The `home:` catch-all typing (claim_goal_typing.py ~172) is wrong for keys that post no Home operation
   (`home:queue-catalogue-shortage`, `home:leave-for-pending-withdraw`, `home:await-fresh-knowledge`, step-offs):
   type each explicitly (Terminal, or Reach for walks); only real Home operations are store-operation Observe.
4. Rule 2 (visit close closes the in-store claim) applies whether or not an operation was posted: no operation ->
   release (`visit-closed-no-operation`); a confirmed in-store effect (deposit/withdraw/sale observed by any path, not
   only the composed paths) -> complete. The added `if not operation_posted: return` is removed.
5. `plan-handoff` tagging excludes holders that are `non_discardable` (those are S3.4 rewrite-refusal violations);
   the writer and the reader use ONE predicate, which requires evidence that the plan changed.
6. Declared design changes (accepted): a `town:wait-recall*` decision continues the standing floor-change claim;
   equipment/calibration non-await Reach reasons continue the session's Observe claim. The pins they moved
   (1354 -> 1348; equipment-txn abandoned 1 -> 6) are declared as consequences.
7. `claim_verdict_conflict` is detected per OPERATION (the same operation identity completed by the claim and failed
   by the visit verdict), not per visit.
8. `visit_owner_mismatch`: map the literal `town-errand` visit owner to the errand family that opened the visit
   (the arbiter's selected producer family) before comparing; report the remaining mismatches.
9. Producer rule, record-only in S3a: a Home scan while a Home atomic operation is pending is recorded as
   `scan-during-pending-atomic` (the behaviour change - no scan while pending - belongs to S3.3/S3.4).
10. Required pins: one test per operation row (complete / release / expire) incl. home-errand, calibration, Home
   atomic, shop expiry; the stuck-prompt-staged-tail capture shows a non_discardable identification claim on
   7286-7288; the claim_verdict_conflict pin reads RECORDED rows (the named captures are already fixed in code and
   cannot reproduce the conflict by replay).

## DESIGN AMENDMENTS 2026-09-26 #4 (after the two reviews of acc741b6)

1. Home continuation: while a Home atomic operation (deposit/withdraw) is pending, `home:leave-*` and
   `home:store-context-exit` emitted by the same family CONTINUE its claim (they are the operation's own exit), they
   are not Terminal retargets. Type by pending state, not by literal alone.
2. Operation identity is per operation, not per family: a store-operation Observe decision receives the pending atomic
   operation's identity ONLY if its key is that operation's own step; a separate request (e.g.
   `home-errand:request-knowledge:*`) gets its own identity. The Home withdraw identity must check the visit is the
   Home visit and must survive until observe_outside completes the operation (capture it at compose). Deposit and
   withdraw use the same identity basis (visit opened sequence + operation key); the table row must match the code.
3. Precursor steps outside a store (`shop:batch-inscribe`, `store:entry-await-observation` before the Reach target is
   reached) are not store operations: they must not open a generic `Observe(("store-operation",))` or store-entry
   Observe claim that the composed operation then retargets.
4. Every emitted `home:*` literal gets an explicit typing row (enumerate them from the source); the catch-all is only
   for literals that truly emit no Home operation. `home:morivant-temporary-deposit` and
   `home:morivant-retry-temporary-deposit` are real deposits.
5. plan-handoff requires recorded plan-change evidence (plan rebuild / plan identity change recorded in the row). A
   family proxy (`owner in {home-scan, home-errand}`) is not evidence. The writer records the evidence fields in the
   row; the reader decides from those recorded fields only.
6. Visit owner: `opened_producer_family` is captured when the visit is acquired/opened (the producer that composed the
   entry), never latched from the first claim row and never defaulting to the claim's own owner. Report the remaining
   mismatches with causes (router-opens / family-operates is a structural class: record it as such, do not count it
   as a mismatch if the operation family is the one the router opened the visit for).
7. Correction of amendment #3 item 10 and S3 §3 row 3: the stuck-prompt capture holds the identification tail at 7261
   (`identify:pack-pressure 'uqt'`); 7286-7288 hold the curse-enchant launcher chain. The capture proves that a staged
   tail is rewritten, not that `register.current.non_discardable` was set. The rewrite row must record the displaced
   non_discardable producer (family + key) from the per-decision producer slot, and S3.4's refusal must read that
   per-decision producer, not only `register.current`.
8. Pins must exercise production code: the verdict-conflict pin must run the production detector on the recorded rows
   (with provenance: source file, line numbers, sha256) or on a replay of the real atomic-withdraw flow; a fixture-only
   assertion is not a pin. Vacuous `if ... is not None` guards in pins are not allowed.
9. Replays release a staged chain only when `_chain_matches(chain, key)` holds, as live cli.py does.

## DESIGN AMENDMENTS 2026-09-26 #5 (after the two reviews of 7df0fb0d)

Recording fixes (record-only, S3a round 4):
1. `opened_producer_family` comes from the producer that actually composed the entry. Remove the fixed guesses at
   policy.py ~5941 (observed-transaction -> "shop-buy"), ~5816 (shop-handler-recovery -> "shop-buy"), policy_home.py
   ~2446 ("home-visit" when no equipment-transaction session). Tour mismatches seq 10/11/12/15/16/17/2666/2667/2668 are
   artifacts of 5941 (the entry was composed by the shop-sell one-shot).
2. The router records the family it opened the visit FOR (at open). `router-opens-family-operates` applies only when
   the operating family equals that recorded purpose (policy.py ~3946); otherwise it is a mismatch.
3. `scan-during-pending-atomic` applies to every '~9' knowledge scan (home-scan AND home-errand:request-knowledge)
   while a Home atomic operation is pending (policy.py ~3981; town-approach 1922, 1958).
4. One operation, one family: a Home atomic deposit/withdraw or Home exit composed on behalf of an equipment
   transaction or calibration restore is recorded under that transaction's family and claim (tour 3038, 3040, 4250;
   town-approach 1179, 1885, 1893, 1899); `calibration-restore:*` plans are recorded under the calibration claim
   (tour 3020); the `town:entrance-step-off:<inner>` wrapper is recorded under the inner owner, in census and claim
   alike (tour 2646, town-approach 1906).
5. Ending a claim because its own identity went stale is a named release, not a retarget (town-approach 1919).
6. Home operation identity is captured at compose and survives `close()` (policy.py ~3327-3348 rebuilds it per
   decision from visit.operation_key).
7. plan-change evidence only when the ordered stop sequence changes the CURRENT or NEXT stop (policy_town.py ~3232),
   and never from a rebuild that is not adopted (policy_shop.py ~1247 refreshed_plan).
8. The verdict-conflict pin replays the recorded rows through the production reader/detector; the provenance sha is of
   a frozen copy committed as a fixture (the live log keeps growing), and the test checks it.

Design rulings for the S3.3/S3.4 enforcement (from the user decisions already on record):
9. "生存は中断して戻す": town damage responses `town:seek-shelter` and `town:recover` are survival for ownership. They
   SUSPEND the current town claim (including never_suspended equipment/calibration Observe claims, which resume
   afterwards); they are not violations (tour 3008, 3030).
10. A producer whose one-shot trigger is gone releases its own Reach with a named release (tour 3009: seek-shelter's
   `_took_damage`), not a violation.
11. "町の用事は同じ順位（横取り禁止）": between the two exceptions (non_discardable equipment transaction and Home atomic
   operation) the one already holding the goal continues; the other waits. A second non_discardable transaction may
   not interrupt a running calibration restore (tour 3037) and vice versa.
12. A Home errand claim is per operation, not per Home stop: each operation in one Home stop (knowledge request,
   deposit of bought items) has its own claim and completes on its own effect (town-approach 1947, 1957).
Real violations S3.3 must refuse (evidence): tour 2701, 3052 (router Reach not arrived -> Home scan);
town-approach 1177 (filed Home errand ESC during an equipment-transaction deposit), 1916 (combat-weapon Home errand and
restore-combat-weapon hold the same purpose), 1922/1958 (knowledge scan during a pending deposit; 1923/1959 are their
consequences).

Side finding (separate live fix, not S3a): policy_home.py ~1231 answers the quantity prompt only when
deposit_count > 1; depositing 1 from a stack of more than 1 leaves the quantity prompt open and the following key
(ESC, or the next 'd' in a composed chain) cancels or corrupts it. Live keys seen: "db\x1b", "de2\rdddcdb3\rda\x1b".

## DESIGN AMENDMENTS 2026-09-26 #6 (after the two reviews of ec2ffd99)

1. Purpose duplication is a violation class of its own: when a family starts work on a purpose (e.g. the combat-weapon
   restore, keyed by the purpose identity such as item/slot) while another family still holds an OPEN request for the
   same purpose (filed Home errand `home-errand:request-knowledge:combat-weapon` stays filed through 1922/1946/1956/1958),
   record `purpose-duplicate` on the row with both holders. town-approach 1916 must be counted again under this class.
   Per-operation completion (#5.12) stays; the filed request is a separate holder from its individual operations.
   Fix the note at tests/test_town_approach_retired_recorded.py ~115-118 (the #5 list is 1177, 1916, 1922/1958).
2. A claim re-attributed to another family (#5.4: equipment-transaction under a calibration session ->
   calibration) must complete through the same completion path: the completion recorder closes the claim under the
   family it is recorded with (policy.py ~5773-5776 closes only owners=("equipment-txn",)). Base completions must stay
   completions: tour 3018, 3032, overweight 3755, 3767. Add a pin on calibration/Observe endings.
3. `opened_for_family` is the family of the producer that REQUESTED the router trip, captured when the router accepts
   the request (the requester is known at that moment), not inferred from need_categories / session presence
   (town_arbiter.py ~714-729). Include `_calibration_session_owned()`. No default "home-visit". Measured wrong rows:
   overweight 3710, 3768-3775; tour 3032-3046.
4. #5.4 also covers the non-atomic `equipment-transaction:deposit` exit `home:leave-after-one-operation` (tour 2654,
   2682).
5. `_claim_family_of` rule 5 (policy.py ~2986-3000) decides by the COMPOSING producer, not by the mere presence of an
   equipment session; a home-visit deposit composed during a session stays home-visit (and is then a violation).
6. Correct the stated causes: town walk claim id 902->893 (1179/1885/1893/1899 transaction Home steps, 1906 step-off
   wrapper, 1907 continuation; not calibration); equipment Observe complete/abandoned re-pin; overweight owner-mismatch.
7. Item-8 verdict pin: pass the recorded closed_claim.owner (calibration in 2 of 3 rows) to the detector, not a
   synthesized home-visit withdraw.
8. Suspended-claim completion: an observed effect (e.g. `_claim_home_knowledge_observed`) completes the matching claim
   whether it is active or suspended; consume the flag only after suspended claims were checked (policy.py ~3815;
   reproduced: knowledge request suspended by town:seek-shelter stays open after its ~9 response).

## DESIGN AMENDMENTS 2026-09-27 #7 (after the Opus review of 85cd7b4b)

1. Store-trip requester (replaces the #6.3 implementation). There is one write point for a router trip: every place
   that sets the shopping approach target (`_shopping_approach_store_type` and the equivalent Home request) goes through
   a single helper that takes the requesting family explicitly (the family of the rung/producer making the request),
   for EVERY store type, not only Home. The router copies that value into `StoreVisit.opened_for_family` when it opens
   the visit. `_home_visit.request.requester` (stale while a request is queued: home_visit.py ~119-126) and the fixed
   priority classification (policy_quest.py ~407-508) must not be used for this. No fallback guess: if a path has no
   explicit requester, record `requester-missing` on the row (a recording defect to fix, never counted as a mismatch).
   Expected: the 11 overweight rows (16, 3709, 3735-3741, 3743, 3780) and the tour/town increases (22->31, 10->12)
   resolve to either real mismatches with a named requester or zero `requester-missing` rows.
2. purpose-duplicate is generic: a purpose identity = (purpose kind, target slot or item identity). Any family starting
   work whose purpose identity equals that of an open filed request of another family records it (examples to pin:
   restore-combat-weapon vs combat-weapon errand; replace-no-teleport-weapon vs the same main_hand errand from
   `_home_rearm_key` policy_equipment.py ~2445-2451; identification / experience-potion errands vs another family's
   same-item work). Record it alongside any other violation on the row (a row may carry several classes).
3. An exit key after the transaction's effect was observed continues/closes the transaction claim; it must not open a
   fresh Observe(store-operation) claim that can only end as `visit-closed-no-operation` (tour 2654->2655, 2682->2683,
   overweight 3779->3780, town approach 1904->1905).
4. Operation family = the owner whose plan the operation serves. A deposit registered into the calibration restore list
   by `_home_deposit_key` (policy_home.py ~1211-1221) is a calibration operation; remove the fixed "home-visit" at
   policy_home.py ~2426 and ~2337 (tour 2998-3003, overweight 3738-3741).
5. Suspended-claim completion (#6.8) is generic over every observed effect (home-withdraw-observed,
   equipment-transaction-complete, ...), not only knowledge.
6. Transaction completion closes the family recorded on the claim (not re-derived at completion time).
7. Correct the 893 cause note: 1179, 1885, 1893, 1899, 1906, 1907 plus the resumed transaction claims 1887, 1895, 1901.

## S3a MERGED 2026-09-27 (4e6baea7, record-only; keys/reasons identical to main on 6 replays; S3 gate met:
## tour 3, town approach 5, overweight 1, others 0). OPEN ITEMS REQUIRED BEFORE S3.3 ENFORCEMENT (Opus review of 4e6baea7):
1. #7.3 still unmet: after `equipment-transaction-complete` the `home:leave-after-one-operation` ESC opens a fresh
   Observe(store-operation) that ends `visit-closed-no-operation` (tour 2654->2655, 2682->2683, overweight 3779->3780,
   town 1904->1905); policy.py ~3504 checks only visit.operation_effect_observed, and completion closes the standing
   claim before `_claim_goal`, so the session branch (~3511) sees None.
2. Requester constant "store-router" at 13 sites (policy.py 2764, 5444, 5582, 8610; policy_quest.py 577, 605, 612;
   policy_shop.py 758, 766, 777; policy_town.py 1019, 1438, 4566) makes requester_missing structurally 0. Ruling needed:
   router plan stops as a formal `router-plan-stop` structure (excluded from mismatches) vs requester-missing. Also:
   reusing an open visit keeps the first requester (town_arbiter.py ~240); `_claim_family_of` still reads
   `_home_visit.request.requester` (policy.py ~3022). Genuine mismatches measured: tour 9, town 4, overweight 2
   (sibling families), withdraw 2.
3. town 1958: `shop:await-leave-confirmation` is a store-agnostic leave barrier (policy.py ~6470) attributed to
   shop-buy by prefix; attribute barriers to the visit family; treat 1957 as "interrupt before leave confirmed".
4. Undesigned record-only rules added in the merge need a design ruling + pins: character-dump preemption
   (policy.py ~4471, contradicts never_suspended for store-operation claims, never fired, no test),
   `continuing_home_errand` (~3938), `shop-observation-interruption` (~3906).
5. `decision_attribution` telemetry value changed (policy.py ~3952-3956; tour 2998-3003, 3038; overweight 3736-3741,
   3769); purpose-duplicate identity uses key[-1] slot letters for identification/experience (may self-match).
6. Stale note tests/test_overweight_home_unreachable_recorded.py ~314 (requester is store-router, not home-scan).

## USER DECISIONS 2026-09-27 for S3.3 (answers to the fable review jsonlog/design-review-s3-prereq-fable.md)
1. Purpose duplicate (town approach 1916): 「登録済みの依頼を優先」 - while a filed request holds a purpose identity, any
   other family wanting the same purpose waits until the filed request completes or is released by its own owner.
2. A town errand stop that became unnecessary while walking to it: 「最後まで歩き切る」 - the walk continues to the
   store/Home; the decision is re-made on arrival (no stop-obsolete release mid-walk).
3. A town monster adjacent during a pending store/Home operation or equipment transaction: 「中断して戦い、終わったら戻る」
   - town:kill-mob is treated as survival for ownership: it suspends the running claim, which resumes afterwards.
Technical rulings (a')(b')(c') and rules 2.1/2.2 of the fable review are adopted as written in that file.

## RULING 2026-09-28: requester for mixed-family plan stops (closes the requester-missing item)
A town-plan stop that serves several needs records the SET of families whose needs it serves as the requester
(`requester_families`). An operation by a family inside that set is not a mismatch; an operation by a family outside the
set is a genuine mismatch; an empty set is requester-missing (recording defect). No single-family guess.

## DESIGN AMENDMENT #8 ADOPTED 2026-09-29 (explicit execution delegation and holder liveness)
Text: jsonlog/design-s3-3-amendment-8-astra.md (gpt-6-astra, against 5f955fe8). Review: jsonlog/design-review-s3-3-amendment-8-fable.md
(fable: adopt with changes). #8 is adopted TOGETHER WITH the review's seven REQUIRED changes (missing executor paths
file-combat-weapon / file-identification / router one-shots; entry gates for identification, curse-enchant, cross-town,
rumor or declare them outside ON; delegation token only for items in the calibration deposit candidate set H:1234;
reserve at session install and bind/cancel at the choose_key exit; `no-step:<cause>` releases enter the S2b.2 bar table
with the durable lift key and one terminal literal; immutable visit field `exit_requester`, no guessing -> typed stop;
measurable ON go/no-go: (i) six OFF hashes unchanged, (ii) each fixture's first divergence is in a pre-fixed expected
table, (iii) zero ON rows with an empty key that is not a typed stop, (iv) holder-silent only from the §3 final branch).
Implementation order: the review's six steps (harness first; record-only delegation; leave provenance; entry gates and
reservation; ON behaviour; re-measure). No new user decision required.

## RULING 2026-09-29 (Claude, r8 stop at tour index 2701): a posted operation's own observation wait is not an empty holder key
At tour index 2701 (historical 2699) OFF emits `""` / `store:entry-await-observation`: the store-entry key has been POSTED and
the next board has not yet shown the store. That is design §3's "posted observation pending: use that operation's
context-valid existing continuation" - and the existing continuation of a posted store entry IS that observation wait.
The #8 no-empty-key rule forbids `""`/`ownership:holder-*` (a holder waiting on nothing); it does not forbid the typed
observation wait of a live posted operation with an identity. Sending a travel macro while a posted entry is unobserved
posts keys blind (LANDMINE composed-store-macro-posts-blind). Therefore: a posted store/Home entry suspends the route child
(arrival is being observed; the Reach is not continued or replanned) until the entry is observed (complete) or the existing
entry-wait budget ends (release, then the route may replan). The fixed first-divergence table is NOT revised; ON must equal
OFF at 2701. Typed observation waits are counted separately in go/no-go (iii) and are allowed only with a live posted
operation identity.

## RULING 2026-09-29 #2 (Claude, r8b stop): two rows of the fixed first-divergence table corrected from ADOPTED design, not from output
1. Town index 1179: the row's REASON `equipment-transaction:atomic-deposit` stands; its byte was mis-stated. Inside an open
   Home store page the existing store command boundary (policy.py ~7608) sends `\r` for the continuation `5`; the byte is
   fixed by that boundary, not by #8. Expected: `\r` / `equipment-transaction:atomic-deposit`.
2. Tour: design #8 §1 (row tour:2701) classifies the outside Home scan proposed while store-router's Reach is open as a
   real interruption of a different errand, and user decisions 「最後まで歩き切る」/「町の用事は同じ順位（横取り禁止）」 keep the
   route. The fixed row at index 2705 (`2` melee) contradicted §1 by assuming the scan was admissible first. When the
   posted travel releases short of the entrance (index 2702) and the route claim remains open, the route continues.
   Expected tour first difference: index 2703 (historical 2701) `7` / `shop:approach`.
Only these two rows change; every other row stands. The remaining go/no-go items are still required: (iii) over all six
FULL ON streams plus the newer incident replays, (iv) `ownership:holder-silent` only from the §3 final branch (the
constructions at policy.py ~2692, ~5552, ~5596 must be routed through it or removed).

## CROSS-AREA DESIGN ADOPTED 2026-09-29 (fundraising purpose + shared verdict; one equipment selector; declarations)
Text: jsonlog/design-ownership-crossarea-astra.md (gpt-6-astra). Review: jsonlog/design-review-ownership-crossarea-fable.md
(fable: adopt with six REQUIRED changes; first round limited to the shared verdict + entrance route resume; declaration table,
family audit and a general contract-conflict stop deferred to round 2+).
USER DECISIONS 2026-09-29 (verbatim):
1. Food: 「初期アイテムに食料となる杖があるため、最初の採掘で食料が問題になることはない。必要なら初回のみ条件を緩和。」
   -> the dungeon rule (carry an edible device) stands; the town admission requires the edible device CARRIED, withdrawing it
   from Home first (Home-first procurement, departure conditions count carried items only); only when no edible device exists
   anywhere (pack, Home, affordable shop) may the FIRST fundraising run of a character depart without one. The fact of that
   waiver is an immutable field of the fundraising purpose; the dungeon continuation reads the same verdict.
   Evidence: the starting food staff (tval 55, 20 charges) was deposited at Home by calibration at turn 79437-79448 (09-28 17:1x)
   and never restored after calibration stopped owner-retired; nothing withdrew it since.
2. Empty body slot: 「空いた鎧の欄は必ず埋める」 -> filling an empty body-armour slot (when a legal candidate exists) is a
   REQUIRED constraint of the ONE full-loadout selector; it maximises within the satisfying set (bands, AC100 damage, depth
   gates unchanged). The priority body-rearm (policy_quest.py:1035-1099) only submits the need to that selector.

## RULING 2026-09-29 #3 (Claude, cross-area index 1256): the shared verdict reproduces the existing stop rule, it does not change it
The shared `fundraising_run_verdict` exists to make town admission and dungeon continuation read ONE predicate; it must not
silently change a policy. The existing rule (policy_fundraising.py ~987-996) returns at the gold target only in `scavenge` mode
or when no known treasure remains; `mine` with known treasure continues to the loot route. The verdict encodes exactly that
(`objective_achieved` is a return trigger only under that condition). Town index 1256 must therefore match OFF (`7` /
`fundraise:seek-loot`); the frozen table stays. Any change to when fundraising stops is a user decision, not part of this refactor.

## RULING 2026-09-29 #4 (Claude, town index 1179 after the second live stop): supersedes #2 item 1
Evidence (s3-town-1179-live2.md, recorded boards): the posted `dm` deposit (axe) had taken effect by sequence 1177 (axe gone from
the pack, Home stock 130 -> 131, game message). Ruling #2's expected `\r` / atomic-deposit was a continuation wait AFTER an
observed effect - the same defect that stopped the bot live at 19:04 (CR x9 -> owner-retired). Per design #8 §3 ("ready
child/action executes") the session's next planned action (deposit pack:055751ff10eb08e9 = slot l) is dispatched. Expected
row: `dl` / `equipment-transaction:deposit`. Lesson: an expected row must be checked against the recorded board's observed
effects, not only against the key byte conventions.

## RULING 2026-09-30 #5 (Claude, after declarations r8/r9): deferral skips the rung; the holder is not re-dispatched
Rule 2.1 of the fable prereq review ("record errand_deferred, emit the holder's key") forced the enforcement to RE-DISPATCH the holder's
work. Legacy producers are broad methods, not callable units, so re-dispatch needs a per-step dispatcher (~70 next_step names; r8/r9 could
only cover route.resume, stair.post, calibration.*, equipment.next-action). Replacement rule under S3.3 ON:
1. A town producer whose family is not the holder's (and has no identity-bound grant) is SKIPPED at its entry gate (returns None, records
   errand_deferred); the ladder continues. The holder's own family producers run at their normal place in the ladder and emit their
   own step. No re-entry, no emitting the holder's key from the enforcement.
2. If the ladder ends with no key: the holder's bound declaration decides - awaiting with a live posted identity -> that operation's typed
   continuation; no-step/releasing/done -> named release in the same decision and one more ladder pass (bar entry per ruling);
   acting but its producer did not emit -> holder-silent typed stop (a real defect to capture); missing -> declaration-missing typed stop.
3. The r8 named dispatch stays only where the holder's producer cannot re-emit by itself (route.resume after short travel, stair.post,
   calibration continuation, equipment.next-action), as a producer-level fix, not an enforcement fallback.
RULING #5 REVIEW (fable, jsonlog/design-review-ruling5-fable.md): adopt with changes. REQUIRED before ON:
1. One helper wraps every `_decide`/town producer call in `_choose_key`, derived from the CLAIM_LADDER rung table: holder present, family
   differs, not survival/detectors -> the producer is NOT called (entry deferred recorded). Only 5 per-producer entry gates exist today
   (P:2929, 6326, 6659, 7588, 8259); the result-stage catch-all `_enforce_town_claim_result` (P:6270-6330) is what really gates, AFTER
   producers have mutated state -> false holder-silent stops (the r8c 13/7/15 counts) and double mutation on a second pass.
2. The catch-all becomes a gate-leak detector: `final:` rows counted OFF; ON go/no-go = zero `final:` rows on the six replays; if one
   appears ON -> typed stop `ownership:gate-missing:<family>`.
3. No second ladder pass if the first pass had a `final:` row; the second pass uses the same call path as the first (incl. home_capture).
4. `held_claim_decision` decided by `_claim_family_of(reason) == holder.family`; arbiter retirement / no-progress / procurement rewrites
   pass the holder's key through with `rewrite_refused`.
5. Bookkeeping/detector rewrites are outside the holder judgement (state it). 6. The catch-all's `in_town` condition matches the loop's
   (`in_town or store`). 7. Plan order (S3.3 item 8): after a release the next holder must be the plan's next stop - families that are not
   plan-next are also gated, or their self-restraint is shown.

## RULING 2026-09-30 #6 (Claude): withdraw fixture expected row (edited by sol in d49a72f7 without a prior decision - accepted after review)
Recorded decision 20: OFF `rkc` / `town:enchant-launcher-todam` (curse-enchant family, not the plan's next stop) -> ON `\x1b`n%.` /
`shop:travel` to store 3, the plan's next stop after the Home operation released. This follows the user decision 「実行順は予定表」 and
ruling #5 review item 7 (families that are not plan-next are gated). Expected row: (20, 20, "\x1b`n%.", "shop:travel").
Process note: sol must not edit EXPECTED_FIRST; it must stop and state the decision needed (re-stated in the next prompts).

## RULING 2026-09-30 #7 (Claude): tour expected row after declarations r12
sol r12 classified tour index 2048 as (A): the store-4 one-shot purchase (posted at 2044) was released (parent-claim-ended) and no entry was
posted, so the OFF `5` / `shop:travel:await-entry` had no live entry identity (ruling #1 requires one); the plan's next stop is store 3
(「実行順は予定表」, ruling #5 review item 7). Expected row: (2048, 2046, "\x1b`n(.", "shop:travel"). r12 fixed two (B) defects
(town 59 probe outside the gate; overweight 3707 empty entry wait without a posted identity).

## RULING 2026-09-30 #8 (Claude): overweight index 3715 (declarations r13)
At 3715 the Home visit is EXIT_PENDING with its Home-tail delegation open. User decision 「町の用事は同じ順位（横取り禁止）＋例外2つ
（非破棄の装備取引・自宅の原子操作）」: a Home atomic operation in progress ranks ABOVE the town errands. Therefore:
- the recorded OFF `identify:device` is a hijack of the open Home tail (identification may NOT preempt it);
- the current ON `shop:travel` to store 4 is ALSO wrong (it abandons the pending Home tail/exit);
- ON must emit the Home tail's own continuation (its exit / leave-confirmation step per ruling #1-#4 and design #8 §4, with the
  visit's operation provenance). Fix the code so it does; then the overweight expected row becomes index 3715 with THAT key/reason
  (the first difference is legitimate because OFF hijacked). Claude sets the row after seeing the measured key.

## RULING 2026-10-01 #9 (Claude): withdraw expected row after live23 (supersedes #6)
Measured on main f5b43e62: recorded decision 3, OFF `~9 ESC` / `home:request-knowledge-scan`; ON `ESC` /
`equipment-transaction:catalogue-leave-for-scan`. The withdraw fixture's Home page at that decision shows 52 of 131 items. live23
(ddebaf64) keeps the registered equipment-txn catalogue claim until the catalogue is adopted; a partial page leaves the store under the
same owner to request the complete list, instead of a later home-scan producer taking the UI (user decision 2026-09-27
「目的の重複＝登録済み優先」). OFF is unchanged (hash a9b34420). Expected row: (3, 3, ESC, "equipment-transaction:catalogue-leave-for-scan").
