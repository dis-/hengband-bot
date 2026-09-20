# DESIGN — Town stop: overweight departure with no claim owner

Author: reviewer (Fable), 2026-09-21. Status: **user-confirmed 2026-09-21 (full scope P1-P4)**, dispatched as topic `town-weight-departure`.
Supersedes the diagnosis in `jsonlog/fixer-town-priority-stage3-r4-prompt.txt` ("the order has no tail").

## 1. What the live stop actually is

Artifacts (all under `bot-client/`):
- `incident-captures/20260921-0536-no-claim-after-bounty/decisions.jsonl` (1.4 MB, 177 decisions)
- `incident-captures/20260921-0536-no-claim-after-bounty/snapshots.jsonl`
- `tests/fixtures/incident-20260921-0536-no-claim-after-bounty.jsonl.gz` (same window, 177 rows)

Measured, not inferred:

1. **The only failing departure conjunct is `inventory_weight_ready`.** All 17 blocked rows carry an
   identical `departure_block`: every one of the other 30 conjuncts is `true`.
2. **The excess is 7.** Pack 1,235 + worn 372 = **1,607**; limit `ADJ_STR_WEIGHT_LIMIT[23] * 50` = **1,600**.
   `_inventory_weight()` sums inventory *and* equipment (`policy_helpers.py:276`).
3. **No `weight-overload` need is ever produced or selected** — 0 occurrences in the whole decision log.
   `procurement_requirements` is `[]` on the blocked rows; the only live claim is `launcher-enchant`.
4. **Home is blocked by a cumulative bound**: `visit_ledger.unsatisfied_passes = {"7": 5}`,
   `blocked_stores = [7]`, `approach_fails = {}` (zero). The limit is 3.
5. **Retention reserves the whole carried stack of every consumable**: recall 11/11, teleport 15/15,
   cure 10/10, heal 8/8, speed 10/11, ammo 99/99. `_retention_surplus` is therefore 0 for all of them.
6. **The pack churns**: row 85 deposits the weapon of weight 190 (1,235 to 1,045); row 141 takes it
   back (1,049 to 1,239). The visit ends overweight again.
7. **Slot-based owners cannot fire**: 18 items of 23, 5 free slots. Both
   `_town_overflow_destroy_key` (`policy.py:5945`) and `_town_space_deposit_actionable`
   (`policy_town.py:1392`) are gated on `PACK_CAPACITY - len(inventory) < MIN_FREE_PACK_SLOTS` (5).

Mechanism, read from source and consistent with every artifact above:

    _inventory_overweight -> inventory_weight_ready = False           (policy_town.py:1352)
      -> departure_ok = False, recall never fires                     (policy_town.py:4429)
    weight-overload need would exist (budget 1, departure_blocking)   (policy_town.py:1925, 2403)
      -> the selection loop skips every Home need because
         _town_store_blocked_under_applicable_bound(STORE_HOME)       (policy_town.py:2508)
      -> the named terminal town:blocked:overweight-home-unreachable
         is armed only for approach_fails >= limit, which is 0        (policy_town.py:2528-2538)
    nothing claims the decision -> stuck:wander -> town liveness fuse
      -> town:blocked:no-actionable-claim-owner x17                   (policy_town.py:1060-1067)

## 2. Why round 4's pins passed without the fix

`TownPriorityStage3Round4RecordedTest` patches `_recall_town_departure_conjuncts` to return
`{"recorded-ready": True}` and `_dungeon_entry_allowed` to `True`. That wall removes the *only*
conjunct that fails in the field. On the unmodified tree P1 and P3 pass and P2 fails solely on
`policy._town_order_operation == "normal-step13-depart"`, a white-box label. The pins do not
discriminate the defect and must be rebuilt.

## 3. Defects to fix

- **D1 — a cumulative optional-churn bound retroactively blocks a mandatory departure errand.**
  `unsatisfied_passes[STORE_HOME]` is a lifetime counter (`policy_town.py:3073`) reset only by an
  *observed* completed Home operation (`policy_town.py:2975`). Once it reaches 3 the store is blocked
  for every category, including `weight-overload`, whose spec is `departure_blocking=True`.
  User decision 2026-09-03 #3: 「需要の再武装は許可する。ループしないよう留意すること。」
- **D2 — the shed selector cannot see surplus.** `visit-purchase` reserves `item.count`
  (`policy_home.py:536`), so anything bought this visit is untouchable, and `_overweight_home_deposit`
  filters on `_retention_surplus(...) > 0` (`policy_home.py:893`). With 7 units of excess the correct
  shed is a spare armour piece, a shovel, or the cursed shield — never a required supply.
  User decision 2026-09-03 #1: 「重量を原因に要求物資を緩和してはならない」 and #2:
  「まず要求物資の過剰分を自宅に預け入れる。」
- **D3 — the stop is anonymous.** When the deposit genuinely cannot happen, the terminal must be the
  named `town:blocked:overweight-home-unreachable` (already in `cli.py:387`), not the generic
  liveness fuse. User decision 2026-09-03 #5: 「本当に預け入れに失敗するならそれは停止するべき事案である。」

## 4. Proposed design

**P1 (D1). A departure-blocking Home need re-arms the store bound once per new work signature.**
`_town_store_blocked_under_applicable_bound` already carries the notion of "the bound that installed
it". Add: a Home need whose spec is `departure_blocking` re-arms the store when the *work signature*
(the selected deposit item's signature) differs from the one in flight when the bound was installed.
Re-arm at most once per signature per town visit, so the churn bound still holds against a repeated
identical failure. No new tunable constant; reuse `_rearm_town_store_for_new_work`.

**P2 (D2). Order the shed by an explicit ladder before touching any required supply.**
When overweight, `_overweight_home_deposit` selects in this order and stops at the first item that
alone clears the excess (existing `excess` logic at `policy_home.py:901`):
  1. cursed equipment carried in the pack (decided 2026-09-18: destroy);
  2. digging tools on a non-mining departure (decided 2026-09-18);
  3. spare equipment not held by an equipment transaction;
  4. only then the *excess over the retention target* of a required supply.
Step 4 must never take a supply below its `required_departure`; step 3 must not take an item the
equipment optimizer currently owns, or the row-85/row-141 round trip repeats.

**P3 (D2, root). `visit-purchase` stops reserving the whole stack.** Reserve
`max(supply-ledger target, the quantity bought this visit that the ledger still needs)`, not
`item.count`. Anything above the target is surplus by definition, which is what user decision #2 names.

**P4 (D3). Named terminal.** When overweight and every Home route is exhausted *after* P1's re-arm,
set `_town_blocked_reason = "overweight-home-unreachable"` whether the exhaustion came from
`approach_fails` or from `unsatisfied_passes`.

**Out of scope, deliberately**: the town-order tail (steps 11/12/13). The recording proves departure
fires as soon as the weight conjunct is satisfied, so the tail is not what stops this character.
Stage 3 round 4 should be re-scoped to this defect, and the tail deferred to its own round.

## 5. Pins (recorded rows only, public `choose_key`)

The 05:33–05:36 window starts *after* the latch formed (`unsatisfied_passes` was already accumulating),
which the standing rule about capture windows warns about. Therefore:

- **R1 (reproduction, mandatory).** Replay the fixture with **no wall on
  `_recall_town_departure_conjuncts` and none on `_dungeon_entry_allowed`**, reaching the ledger state
  the recording itself reports (`unsatisfied_passes[7] = 5`, `blocked_stores = {7}`) through the same
  public reporting path that produced it, and assert `town:blocked:no-actionable-claim-owner` appears.
  Revert-proof: this must FAIL (no such reason) once the fix lands.
- **R2.** With the fix, from the same rows, the posted decision is a Home route whose reason names the
  weight work, and the selected deposit item is not a required supply.
- **R3.** Weight arithmetic pin: the selected item's weight alone clears the recorded excess of 7.
- **R4.** With Home genuinely unreachable (exhausted through its public path), the terminal is exactly
  `town:blocked:overweight-home-unreachable`, never the generic fuse.
- **R5.** Required-supply floor: no pin passes by shedding recall/teleport/cure/food below its
  `required_departure`.

If R1 cannot be reproduced from the recorded rows alone, capture a new window that starts before the
first unsatisfied Home pass rather than seeding private state.

## 6. User decision (2026-09-21)

Scope question asked and answered verbatim: 「P1〜P4 をまとめて（推奨）」
— implement P1, P2, P3 and P4 in one round. Dispatch prompt:
`jsonlog/fixer-town-weight-departure-prompt.txt`.
