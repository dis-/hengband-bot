# PROPOSAL — Town decision: single-owner dispatch and pure producers

Status: **PROPOSAL. Not approved, not dispatched.** Written 2026-08-27 after the
armour-swap campaign (5 commits, `a3ca7e4..53c5576`) and the `no-actionable-claim-owner`
stall that followed it.

---

## 1. What the evidence says

### 1.1 The two stalls have the same origin line

`src/hengbot/policy.py:22922-22926`

```python
visit = self._store_visit
if visit is not None and visit.store_type != store_type:
    # The visit that opened first is authoritative.  A newly-derived
    # need cannot steal the approach or an open command context.
    return None
```

| stall | open visit | wanted | consequence |
|---|---|---|---|
| armour swap (2026-08-26) | store 0, `entering` | store 7 (Home) | `home-route-unavailable` -> `5` -> re-enter store -> ESC -> abandon -> replan, 8-decision cycle, 5021 game turns |
| `no-actionable-claim-owner` (2026-08-27) | store 6, `approaching` | store 7 (Home) | no progress key exists -> liveness invariant fires -> WAIT/breakout alternation, confined to 3 cells |

One rule, two symptoms, two separate multi-round repairs. "The visit that opened first is
authoritative" is a **second, independent ownership authority** that the arbiter cannot
see or override.

### 1.2 Ownership is advisory, not enforced

Measured on `53c5576`:

| measurement | value |
|---|---|
| `policy.py` | 37,151 lines |
| `_decide` (single function) | 1,473 lines, **158 `return` sites** |
| `self.last_reason` assignment sites | **675** (470 unique literal reasons) |
| `self._*` state fields | 1,238 |
| `_close_store_visit(...)` call sites | 21, with **14 distinct outcome strings** |
| `town:blocked:*` terminal reasons | 8 |
| `town_arbiter.py` | 455 lines |
| owners actually observed in 2000 live decisions | 12 (`store-router` 197, `equipment-txn` 161, `detectors` 75, `home-visit` 47, `shop-buy` 31, `departure` 21, `home-scan` 19, `unregistered` 16, `misc` 13, `town-plan` 8, `survival` 6, `shop-sell` 3) |

The arbiter is consulted at ONE place (`choose_key`, `arbiter.may_select`). The 158 exits
in `_decide` can each produce a key without consulting it. That is why guarding a seam
moves the emission to another seam — measured three consecutive times in the armour-swap
campaign (round 2: reason relabelling; round 3: the retired-claim fallback; round 4: the
session cleared mid-decision).

### 1.3 Detectors exist; a resolver does not

`town:blocked:no-actionable-claim-owner` (`policy.py:3248`) is the town liveness invariant
working exactly as designed: it observes "the winning rung was `stuck:wander`, claims are
active, no progress key exists" and converts a silent wander into a visible WAIT. It
reports correctly. Nothing then **resolves** the stale visit that caused it.

The 14 `_close_store_visit` outcome strings and the 8 `town:blocked:*` terminals are the
fossil record of this: each was added where a symptom appeared, because no component owns
"make the town make progress".

### 1.4 What round 5 proved

Round 5 changed shape rather than adding a guard: ownership latched once per decision at
the `choose_key` boundary, all gates reading the latch. Result — the number that had not
moved in three rounds went to zero, **and `policy.py` shrank by 46 lines**:

| | round 4 (`3b371bc`) | round 5 (`709060f`) |
|---|---|---|
| relocation matrix | 231/504 | **0/504** |
| independent from-scratch detector | 231/504 | **0/504** |
| `policy.py` net | +guards | **-46 lines** |

Decision-scoped ownership works. This proposal generalises it.

---

## 2. Design

### S1 — Single-owner dispatch

Owner selection happens BEFORE any key is produced, once per decision, and is immutable
for that decision.

```
choose_key(snapshot):
    ctx = DecisionContext(snapshot, owner=arbiter.select(snapshot, state))
    key = OWNER_PRODUCERS[ctx.owner](snapshot, ctx)     # only this producer runs
    commit(ctx, key)                                    # the single mutation point
    return key
```

- The owner set is the 12 already observed live, plus `unregistered`/`misc` retired into
  real owners as they are identified.
- A producer that cannot act returns `None`; the arbiter then selects the next owner by
  its existing precedence and progress rules — but still exactly one at a time.
- When no owner can act, the arbiter emits a named `POLICY_FINAL_STOP_REASONS` terminal.
  There is one such site, not eight.

This makes the round-2/3/4 failure mode impossible by construction: a producer that is
not the selected owner never runs, so it cannot overwrite the selected owner's key.

### S2 — Pure producers, one commit phase

Producers become `(snapshot, ctx) -> key | None` with **no `self._*` mutation**. All state
transitions move into `commit(ctx, key)`.

This kills two measured defect classes outright:

- **Probe mutation.** Round 4 measured `_boxed_town_breakout_key` — a candidate-evaluation
  loop — destroying a transaction and permanently quarantining a wearable, and the same on
  the in-town hunger route. A pure producer cannot do this.
- **Self-invalidation.** Round 4's blocker was a producer clearing the session its own
  guard later reads. A pure producer cannot do this either.

### S3 — Visit ownership belongs to the arbiter

Delete the "first opened is authoritative" rule at `policy.py:22923`. `_store_visit`
becomes arbiter-held: when the arbiter changes owner, the visit is closed or transferred
with it. `town_arbiter.py` already proxies the neighbouring state
(`_shopping_approach_store_type`, `_store_entry_wait_owner`, `_store_entry_posted_owner`,
`_close_store_visit`), so the seam exists.

This closes the store-visit leak class — both stalls above, and the three occurrences
recorded earlier (`ccce8b7`, `be8a644`, `2548822`).

---

## 3. Staging, with numeric acceptance gates

Each stage lands separately, is reviewed, and must move a number. A stage that adds code
without moving its number is rejected — the lesson from round 4, which changed nothing
measurable.

| stage | change | acceptance gate |
|---|---|---|
| **T1** | Frozen replay-equality harness + completed-decision attribution census; NO behaviour change. **CORRECTED 2026-08-27:** T1 does NOT deliver an arbiter-selected owner — see §3.1 | replay both frozen incidents: identical key sequence to today (bit-for-bit). Attribution coverage: `unregistered` + `misc` = 0, and `mismatches` = 0 against a committed expected-attribution fixture |
| **T2** | `_store_visit` moves to the arbiter; the "first opened is authoritative" rule is deleted | **LANDED 2026-08-28**, `735843e..30bc57f`. Visit-leak matrix 588 -> **0** (and 0 transfer violations); constructed reproduction refused=True at `735843e` / False at HEAD. Capture-replay acceptance was withdrawn mid-stage — see §3.2 |
| **T3** | Town producers converted to pure functions; single `commit()` phase | **LANDED 2026-08-28**, `e67b56f..4a34ed5`. Probe-purity matrix 2 impure -> **0**, with an empty exemption list and a differ that sees property-backed arbiter state. See §3.3 for what T3 did NOT achieve |
| **T4** | Single dispatch for the town path; the 8 `town:blocked:*` terminals collapse to one arbiter-emitted terminal | town-path exit count: from 158 -> the owner count (~12). Full suite green; both incidents replay clean |

Dungeon path is **out of scope** and needs separate approval.

### 3.1 Correction — what T1 can and cannot deliver (recorded 2026-08-27)

The T1 row above originally promised "arbiter-selected owner recorded per decision". That
is **not achievable at T1 without changing behaviour**, established by review and traced in
the code:

`choose_key` (`policy.py:2523`) delegates to the 1,473-line `_decide` monolith at
`policy.py:2603`, whose 158 exits each write `self.last_reason`. The reason is then still
rewritten by `_refuse_no_progress_cycle` (`policy.py:2619`), `_town_procurement_decision`
(`:2620`), `_forbid_wait_while_damaged` (`:2623`), and the arbiter-retirement branch
(`:2656`, `:2659`, `:2662`). Producing a pre-production value equal to the final one means
predicting which exit wins and whether four later rewriters fire — achievable only with
pure producers (T3) or selection-determines-producer dispatch (T4).

Compounding this: `TownTurnArbiter` exposes only `owner_for_reason`,
`decision_owner_for_reason`, `may_select` and `observe` — **every one keyed on a reason
string; none takes a snapshot**. The `arbiter.select(snapshot, state)` in §S1 does not exist
yet; building it is T4's work.

**Therefore:**

- T1 delivers: the bit-for-bit replay-equality harness (durable — T3 depends on it, and
  T2's authorised re-baseline is only meaningful against it), plus a completed-decision
  attribution census with a falsifiable gate (a baseline, not a component).
- T4 must promote an arbiter-selected owner, **not** this completed-reason attribution.

**T4 baseline number, preserved here before it is lost from the tree:** T1 round 1 measured
a naive pre-selected owner against the completed one at **71.9% disagreement (351/488
town decisions; 128/192 equip-swap, 223/296 no-actionable)**. T4's own acceptance gate is
to drive that to 0.

### 3.2 T2 stage record (2026-08-28)

**Landed:** `735843e..30bc57f` — `bca1f0f`, `59f07ab`, `a0e3be6`, `8f2537b`, `f3817d2`,
`30bc57f`. Net `src/` change: `policy.py` 41 lines, `town_arbiter.py` +117, `cli.py` **0**
(byte-identical to `735843e`).

**What the acceptance gates actually proved**

- Visit-leak matrix (18,144 cells; 2,268 live, 1,764 candidates, 1,176 protected):
  `735843e` **588 leaks** -> `30bc57f` **0**, transfer violations **0**. Non-vacuous in both
  directions: deleting the R4 protection branch yields **1,176 transfer violations**, i.e.
  every protected cell.
- Constructed reproduction (unit-level, built from the captures' own `store_visit`
  telemetry): `refused=True` for both incidents at `735843e`, `refused=False` at HEAD.

**Capture-replay acceptance was WITHDRAWN mid-stage.** Neither frozen capture reproduces its
stall even at `735843e`, because `tests/replay_key_equality.py` starts a cold
`HengbotPolicy()` and the accumulated claim/ledger/session state that produced each stall is
never reconstructed. Seeding from the captures is impossible: they were recorded under the
current record schema and `jsonlog/latch-onset.jsonl` predates both incidents. Ruling B2
replaced that gate with the constructed reproduction above.

**The strongest evidence is a byte accounting nobody set out to produce.** Emitting the
no-actionable capture through `_write_decision` gives 5,552.07 B/record at `735843e` and
4,653.54 B/record at `30bc57f`. Field-by-field, the −898.5 B/record is almost entirely
`departure_block` (−893.3), and **nothing lost content** — bytes per record that carries the
field went 1,656.9 -> 1,662.1. The drop is a presence change: records 49-208 (160 contiguous)
carried `failed = (teleport_ready, organization_complete, equipment_departure_ready,
home_candidate_resolved, home_catalog_ready)` at `735843e` and carry no departure block at
all at `30bc57f`. Index 49 is also the only `town_stall_report` in the capture
(`passes_since_progress: 48`, `store_visit {store: 0, opened_sequence: 49}`,
`need_attempts {"oil": 12}`) — and it does not fire at `30bc57f`. **The store-visit leak that
pinned the errand on store 0 for twelve attempts is gone, the departure block clears, and the
stall stops.**

Honest scope: the equip-swap capture is byte-identical under T2 (zero transfers occur in it).
Its leak-class closure rests on the matrix and the constructed reproduction, not on a replay.

**A seed-telemetry excursion was authorised and then withdrawn.** Ruling B2-c authorised
additive telemetry so FUTURE incidents would be seedable. It grew the record 2.27x
(14,821 -> 33,710 B/record on the no-actionable capture), and — decisively — corrupted the
data it existed to record: a walk-wide cycle-detection set replaced non-cyclic shared
references with `{"unserialisable": ...}` **12,041 times across 296 of 300 records**, all
inside the progress vectors, and `equipment_transaction_session` was emptied in 11 of 11
non-null rows. Ruling C1 withdrew it. Re-proposing it is separate work that must state a
per-record byte budget first.

**Process correction adopted (permanent).** Three of the stage's four late rounds presented
*synthetic-scenario* numbers as evidence for claims about the frozen captures. Every
measurement about the captures must now be measured ON the captures; a synthetic run must be
labelled synthetic and accompanied by the capture measurement.

### 3.3 T3 stage record (2026-08-28)

**Landed:** `e67b56f..4a34ed5` — `67a9894`, `0ceae8e`, `4a34ed5`. Net `src/` change:
`policy.py` +76 lines. Nothing else in `src/`.

**What was proved.** With a from-scratch differ, **no exemption list**, over all 371 in-town
surface snapshots of both frozen captures:

- probe purity: `_boxed_town_breakout_key` mutated 13 fields on every call at `e67b56f`
  (plus four arbiter/transfer fields on 26 snapshots); at HEAD it mutates **nothing**.
- key identity: the effective key is byte-identical to the old on **371/371**, and
  **145/145 + 226/226 with a posted `STORE_GENERAL` visit pinned** — the population that
  round 4 broke (34 and 93 General-escape rows) is exercised and matches.
- no lost side effects: `mutations OLD made that NEW does not = {}` **and** `NEW-only = {}`.
- producer B was **refactored, not exempted**: `DERIVED_CACHE_EXEMPTIONS = {}`, 0 mutations
  across 371 x {cold, warm}, 0 return-value divergences.
- both gates carry negative controls the supervisor reproduced by hand: re-narrowing the
  store loop makes the purity unittest FAIL; re-adding a history-bearing field makes
  `exemption_control=False` and the script exit 1.

**What T3 did NOT achieve — carried to T4.** At the only production call site
(`policy.py:3198`) `_boxed_town_breakout_key`'s return value is **discarded**; the key
actually used still comes from the mutating commit path (`policy.py:3199`). So §S2's
objective — a pure producer deciding the key that is actually used — is not met for producer
A. What landed is behaviour preservation plus one extra pure call. Re-gating the commit on the
probe is not the fix: it was measured suppressing a key the old loop produced on 11/145
snapshots. The correct resolution is T4's single dispatch, where only the selected owner's
producer runs.

**Two acceptance criteria I wrote were wrong, and the fixer's stops caught both.**

1. "T3 is behaviour-neutral" — wrong in principle. Two producers were measurably impure, so
   removing a probe mutation *can* legitimately change which key wins. Ruling D1 replaced
   bit-identity with per-decision attribution. (In the end the targeted refactor turned out
   to be behaviour-preserving anyway, so the authorisation went unused.)
2. "identical 400/300 replay" — vacuous here. `_boxed_town_breakout_key` is invoked **0
   times** in both captures at both commits, so replay equality never executed the diff. The
   evidence that counts is the direct 371-snapshot producer sweep.

**Process rule extended (permanent).** §3.2's rule was "measure on the captures". T3 adds:
**and the measurement must be about code that actually executes.** A green replay over a diff
that never runs is not evidence.

**Also withdrawn this stage.** A generic copy/rollback mechanism (`_evaluate_town_producer`
with `copy.deepcopy(self)`) was implemented and then withdrawn by ruling D3: measured
**131-390 ms/decision** against a 5 ms budget, because the policy pickles to ~2 MB. The
targeted refactor costs ~0. Cheaper generic variants (copy-on-write, `__setattr__`
interception, read-only views) were forbidden with it — all of them have to catch mutation
through nested containers, which is the same trap that made the naive `__dict__` differ blind
to `_store_visit` after T2.

## 4. Risks

| risk | mitigation |
|---|---|
| A 37k-line file; regressions land in live play | Stage gates are replay-based on frozen captures, not opinion. Bot stays held during T2/T4 landing; T1/T3 are behaviour-neutral by construction |
| "Behaviour-neutral" claims that are not | T1 and T3 acceptance is bit-for-bit key-sequence equality on replay, which cannot be argued |
| The arbiter becomes the new single point of failure | It already is, in effect — it just cannot enforce. Making enforcement explicit means one place to inspect instead of 158 |
| sol weakening pins / non-reproducible claims (3 occurrences this campaign) | Same hard rules that worked in rounds 5-6: numeric acceptance committed as a runnable script, hunk-level revert-proof, adversarial review with an independent from-scratch detector |
| Scope creep into the dungeon path | Explicitly excluded; a separate proposal if wanted |

## 5. Cost

Four dispatch+review cycles, comparable to one stage per cycle. The armour-swap campaign
took six rounds for one defect class; this targets the class that produced it. T1 is the
largest single piece of mechanical work; T2 is the one that closes both known stalls.

## 6. What happens if this is NOT done

Both stalls are repaired symptomatically today. The rule at `policy.py:22923` remains, so
the next distinct entry point (a different store, a different owner) produces the same
shape again. That has now happened twice in two days.

---

## 7. Decision requested

Approve, amend, or reject — and if approved, whether the bot stays held for the whole
campaign or is resumed between stages.
