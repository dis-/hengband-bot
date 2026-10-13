# Review: packspace-depart-1013 (b8f5ac67..e7b0ff5f) — step 3 B

Verdict: **FIX-THEN-MERGE** (the staging itself is sound for the captured scene; two
production changes go beyond the task and flip existing 1.5a tests; one ordering/context
gap adds live risk; no LUNA-REPORT / final-run evidence exists).

## Answers to the operator's concerns

1. **step15a `test_fresh_optimizer_*` flip (blockers `('equipment-transaction-failed',)` →
   `()`)** — caused by `home_deposit_available=(not _home_is_full and not
   _equipment_home_full_refused_this_visit())` (policy_equipment.py:1250-1253, 1469-1472)
   which makes the planner **omit every deposit action** (planner 150-160, 233-244). The
   base 1.5a rule lives at policy_equipment.py:1504-1524 ("refused this visit AND plan has a
   deposit → equipment-transaction-failed → depart on the confirmed current loadout"); with
   deposits stripped that branch can no longer fire, so the fresh search returns an empty
   plan and departure becomes `complete_now` (2802-2810) instead of the recorded
   optional-failure departure. Consequences: no `_retire_actionless_equipment_failure`
   (policy.py:15251), no `_equipment_retired_worn_item_ids`, no
   `optional-optimization-failure-confirmed-loadout` record. Also, a Home-full board that was
   not yet refused now **executes the swap and keeps the displaced items in the pack**
   (deposits never planned, so the tombstone at 2019-2024 is never set). That is a widening
   of 10-03/10-09 ("満杯で入れ替え失敗なら今の装備で出発＋記録"), not required by this task.
   The task only needs the Home-full flag for *capacity accounting*.
2. **Conditional `assertTrue(_equipment_retired_worn_item_ids)` + early break** — same cause.
   In the pin1 replays (134416 / 191943) the bot used to reach the retire path and the
   assertion; now the empty plan makes departure ready earlier, the bot emits
   `town:recall-to-alt-dungeon` before retirement, and the harness breaks out. The weakened
   assertion hides the loss of the retire/record path. Fix 1 restores both tests unchanged.
3. **Removed elif (base policy_equipment.py:2828-2833, `pack-space-required` +
   `_town_pack_space_ready`)** — at b8f5ac67 it allowed departure on the current loadout
   when ≥5 free slots, or 4 free with the terminal signature (MIN_FREE_PACK_SLOTS=5,
   MIN_TERMINAL_FREE_PACK_SLOTS=4). Under the new planner a staged group needs at most +3
   (two takeoffs + one withdraw before the equip; planner 329-339), so with ≥4 free slots the
   planner never leaves `pack-space-required` and the elif would be dead. No reachable
   safety valve is lost; the test flip True→False is correct (there is executable work).
   Note: in the live capture (5 free) that elif should have fired at b8f5ac67 unless
   `premise` (2811-2817) was false; the DIAG does not explain this. Not blocking.
4. **Ratchet 125→126** — the one new declared finding is the `SimpleNamespace` result in
   `test_constructed_home_full_closure_requires_an_unfittable_staged_step` (step15a:174),
   declared constructed, with the plan side covered by the planner unit test. Legitimate.
   Weakness: it patches `_home_is_full` and `_current_worn_loadout_confirmed` and never
   checks that the departure record is actually posted (`_confirm_optional_equipment_failure_departure`).
5. **Staging** (planner 245-370): each group is simulated from the running pack count
   (329-339), groups are complete slot changes, a plan is returned only if it contains a
   takeoff/equip/reposition (368), groups ≤ changed slots, infeasible groups are skipped and
   replanned after the session on the pack-count change (policy_equipment.py:1236-1268).
   Plans that fit are byte-identical (the staged block is entered only when
   `peak_pack_items > pack_capacity`; only `test_reports_pack_space_when_non_equipment_consumables_fill_pack`
   changed, which is the decided behaviour). Mid-group failure: session blockers →
   `_abandon_blocked_equipment_transaction` → restore via owned items, including a Home
   withdraw when the old item was already deposited (1831-1847) — existing path, untested
   for the new deposit-first order. **Gap**: the group order is takeoff → deposit → withdraw
   → equip (310-325) even when withdraw → takeoff → equip → deposit would fit, and the
   session context is `"home"` only if the plan has a PHASE_HOME_PREPARE action
   (policy_equipment.py:1588-1595; session.py:136). A staged plan without withdraws
   (targets from pack, or emptied slots) runs in `"legacy"` context: takeoff outside, deposit
   inside, equip outside, per slot — repeated Home leave/enter and walking with an emptied
   armour/weapon slot (09-29 「空いた鎧の欄は必ず埋める」, 10-03 low-HP rules).
6. **`home_full_packspace_closed`** (policy.py:15269-15288) — has the three stated
   conditions and keeps `_missing_required_abilities`, but it also requires
   `_equipment_home_full_refused_this_visit()` (the deposit tombstone). The
   `pack-space-home-full` closure (policy_equipment.py:2824-2855) never sets that tombstone,
   so the block is unreachable in the scenario it was written for (and if a tombstone exists,
   base 1504-1524 handles it). Dead code that looks like a gate.
7. **State** — `_equipment_transaction_visit_closure` already has restore defaults
   (policy.py:2434, policy_observation.py:27/38). New reasons `pack-space-home-full` and
   `pack-space-home-full-current-loadout` reuse the existing closure / optional-failure
   shapes; the departure record is logged once via `optional_failure_departure`
   (policy.py:13712) and the closure via `_offer_execution_no_step` (811-818, existing
   work_id). No new item state → item_intent_baseline unchanged is fine. `town_work_review.json`
   evidence for the planner lost the `pure helper:` prefix form used in
   `town_producer_baseline.json:55` — confirm `tests.test_town_structure_lint` passes.

## Required fixes

1. **Do not strip deposit actions** (policy_equipment.py:1250-1253, 1469-1472; planner
   150-160, 233-244). Pass `home_deposit_available=not self._home_is_full(snapshot)` only,
   and in the planner use the flag only for accounting: no deposit credit in
   `peak_pack_items` (186-191) and in the group simulation / deposit-first pairing
   (314-320, 351-358); keep emitting the deposit actions as at b8f5ac67. Then
   `test_fresh_optimizer_and_rearm_reject_only_home_deposit_plan` and the pin1 replay
   assertions return to their base text (revert the rename, the `()` expectations, the
   `completed_departure` break, and the conditional assertion).
2. **Group order and context** (planner 310-325; policy_equipment.py:1588-1595). Try
   withdraw → takeoff(s) → equip → deposit(s) first; use takeoff → deposit → withdraw →
   equip only when the first order does not fit. Select `physical_context="home"` when the
   plan is staged (a PHASE_HOME_FINALIZE action precedes a PHASE_EQUIP action), so a staged
   plan never alternates leave/enter per slot nor walks with an emptied slot. Add a planner
   test for the fallback order and a session/context pin.
3. **Remove or repair `home_full_packspace_closed`** (policy.py:15268-15291). Either delete
   the block (departure is already granted by 2824-2872 and the record is staged there), or
   drop the `_equipment_home_full_refused_this_visit()` conjunct and add a pin that reaches
   it. Do not leave an unreachable gate.
4. **Final-run evidence**: write LUNA-REPORT-packspace-depart.txt with the affected +
   hygiene set, timings vs b8f5ac67, and the revert checks (task lines 55-65). None exists.

## Not required, worth noting
- A mid-group failure after deposit-first (old item in Home, slot empty) relies on restore's
  Home withdraw (1831-1847); fix 2 makes this the fallback only, but one pin would help.
- Partially staged plans (skipped infeasible groups) return `blockers=()`; the remainder is
  replanned after the session. Acceptable under "staged", but undocumented in the DIAG.

## Owner decision needed
- None, provided fix 1 is applied. If instead the owner wants Home-full swaps to proceed
  with the displaced items kept in the pack (current branch behaviour), that is a change to
  the 10-03/10-09 rule and must be decided explicitly.
