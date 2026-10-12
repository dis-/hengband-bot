# Review: SOL-DESIGN-town-idle-20261013.md (step 3 D, issue #1)

Reviewer: Claude (Fable 5.1), 2026-10-13. Read-only. Base checked: worktree `6e9925f8` (= main `32f93f9c` + task + design).
Checked against `src/hengbot`, `evidence-d/owner-retired-log-only-step2.jsonl` (16 rows), and the decision gzips at the
line numbers the design cites (R1, R2, R3, R4, R5-R8, R10, R12, R13, R14-R16 streamed; 11 of 16 verified by row).

## Verdict: **APPROVE-WITH-CHANGES** (required changes 1-6 before dispatching any slice)

What holds up:
- Record table (R1-R16): time/turn/key/reason/owner/forgiven all match the jsonl; the cited gzip line numbers are exact.
  R7/R16 `forgiven=false` and the burst-after-restart sequence are confirmed (`ba369f140f50.gz:8356-8359`,
  `d2e9d08b57c7.gz:953-955`). The 13-vs-12 CL45 category overlap (R10 counted twice in STEP2) is a correct catch.
- Code citations are accurate to within a few lines: `town_arbiter.py:531-539` (recurrence counted only when the pair
  differs from `_last_pair`), `:538` (limit = detectors budget 2), `:584-600`, `:364-385` (forgive clears everything),
  `cli.py:449-513`, `:527-561`, `:592-593`; `policy_town.py:164-168` (only `equipment-transaction:approach-home` gets a
  distance), `:223-247` (Q2 already has BFS inn distance), `:304-344` (`town:cross-town-shopping:travel-*` absent).
- Group diagnoses verified by rows: R3 is a pure budget stall (rem 8->0 while walking (37,91)->(31,99),
  `77e4ab80164b.gz:5286-5294`) = missing signal. R10 sequence Magic->leave->Alchemist->leave->Magic->`pm1`->pack 16->17
  (`3c2bdf7818df.gz:3357-3363`) = scheduling defect, not false positive. R5-R7: claim 35303 is
  `EquipmentTransaction(phase='equip', item_id='pack:496a911c336315db:0', target_slot='sub_hand')`, each Home entry is
  followed by `leave-home-for-equip` (`policy_equipment.py:2095-2105`), pack 20 unchanged; after the restart the fresh
  process (no session) acquires the catalogue and the equip `wpy` lands at seq 12 (`ba369f140f50.gz:8370`). The
  "feasible but never offered" classification is right. R14-R16: `restore-lantern` (survival, never retired) and
  `equipment-transaction:equip` alternate with physical swaps each time; keeping the retirement is correct.
- Owner decisions: no new owner, no priority change, no departure change; equal rank kept; defect stops kept; no
  persistent tombstone; the slice-1 burst stop retained. "End once per visit with a record" is within the task's item 2.
- All 35 named existing tests exist (`rg 'def test_'` confirmed).

## Required changes

1. **Restart persistence is asserted but does not exist; drop it and state the real bound.** Design line 208-214 says
   "Persist finite receipt consumption/minima with the existing checkpointed visit accounting ... add serialization ...
   pin restart behaviour". There is no such accounting: `_owner_retired_no_progress_count`/`_owner_retired_progress`
   live only in `cli.py:431-464` and tests; the "checkpoint" at `cli.py:3447-3450` is the recorder's replay pickle, not
   restart state; `policy_observation.py:18-45` re-mints `_town_visit_epoch` and resets
   `_equipment_transaction_visit_closure = None` on a fresh process (only the overweight-surplus file survives). The
   10-09 decision (`step1-accounting-only`) says 滞在の記録の引き継ぎ・滞在をまたぐ記憶は作らない. Required: delete the
   persistence sentence; state that every bound in this design is per process + per visit, that an autorecover restart
   resets all of them (R7 was in fact ended by the restart, not by any bound), and that the outer bound is the plan's
   3 town restarts / 24 h. Any slice that needs a field to survive a restart must be marked as an owner question.

2. **Resumed-route credit after an interruption is self-contradictory and would still retire R12/R13.** The shared rule
   (line 189-192, and `cli.py:504-510`) credits only a new minimum per (visit, target) and says "return to an old
   minimum never renews credit"; G7 (line 143) says "the next observed decrease settles it". R12: pursuit pushed the
   character from (23,51) to (21,65) (`44bd959fb3cd.gz:8080-8096`); the walk back needs ~10 decisions before it is
   below the pre-pursuit minimum, but the Q2 bound is 3 (`town_arbiter.py:700`, TOWN_STOP_PASS_LIMIT). Under the
   design's own rule the D3 pin ("one charged unsuccessful resumption below bound") fails at the third step. Required:
   define it. The honest option is: an interruption by another owner that moved the player re-baselines the retained
   minimum at the resumption position (external cause, as the design already allows for readiness), with the
   recurrence/own-decision bound still applying from there. Also fix the mechanism text: the pair is split not by
   "safety" (survival returns early at `town_arbiter.py:486-504` and leaves `_last_pair` alone) but by the `melee` row,
   which is **misc** (`town_arbiter.py:177`, telemetry `misc/misc rem=3` at `44bd959fb3cd.gz:8096` and
   `3f239572048a.gz:9901`). "Safety cannot reset the minimum" therefore does not cover R12/R13; the rule must name misc.

3. **D5 is not a slice; R4 has no pin and the state evidence claim is wrong.** Line 266/269-275 give R4 an
   "evidence-dependent branch" and point to `bot-state-fixed.jsonl.live-1620.gz`. That file covers turns
   16844673-16853798 (after 16:20); every CL45 record is at turn <= 16732715, so it covers none of the 16. The usable
   state evidence is the burst captures `jsonlog\autorecover-20261011-124735-*.bot-state-fixed.jsonl.gz` (R5-R7) and
   `autorecover-20261012-231248-*` (R14-R16), which the design did not open. Required: (a) correct the evidence
   statement; (b) use the two captures for the D1 and D6 pins; (c) split D5: R10 (G6, one concrete pin:
   `3c2bdf7818df.gz:3361` seq 18501 -> continuation of the bound Magic shelf operation, no second route) stays as its own
   slice; R4 moves to "unclassified until pinned" with the decision rows `ba369f140f50.gz:2473-2489` (weight deposit
   pack 19->14 at seq 33451, Alchemist leave, Home return, `~9`, `identify-staff-reserve-unavailable`, equip `wjy`) and a
   stated expected key, or is left out of this design. A slice whose expected outcome is "depends" cannot be merged.

4. **G1/G3 overlook that `~9` works outside the Home.** R3's forgiven suffix shows `home:request-knowledge-scan` `~9`
   posted at (32,100) with `store=None` (`77e4ab80164b.gz:5295`), and R2 does the same at (44,124) (`31c6cc1b1895.gz:4205`).
   The design's G1/G3 remedies still walk to and enter the Home for the catalogue. Required: state what the Home page
   gives that `~9` does not (if nothing, the smallest change for G3 is to let `acquire-home-catalog` use the existing
   outside `~9` request and stop walking; if something, name it). This is a designer question, not an owner question.

5. **Flipping-test list is incomplete; it was grepped by test name, not by alias.** Modules that reference the aliases
   D1-D3 change and are not listed: `test_equipment_homefull_step15a.py` (the 50ecc1eb visit closure D1 builds on),
   `test_travel_interrupted_store_await.py`, `test_crosstown_alt_recorded.py`, `test_home_route_release_recorded.py`,
   `test_home_withdraw_moved_address.py`, `test_live23_home_cycle.py`, `test_equipment_home_full_incident_recorded.py`,
   `test_ownership_s2a1_closure.py`, `test_ownership_s3a_record.py`, `test_s33_batch_context.py` (full list: 20 modules,
   `rg -l 'acquire-home-catalog|travel-home:await-entry|leave-home-for-equip|cross-town-shopping:travel|equipment-transaction:travel-home|home:await-fresh-knowledge|scan-incomplete-open-page' tests/`).
   Required: per slice, list which of these stay green and which flip, with the assertion that flips.

6. **D6 duplicates step 3 A and should be reduced to a regression control.** Branch `light-swap-1013` (`f52ce85b`,
   `policy.py:12840-12850`) already stops `_empty_lantern_to_restore` while a usable light is worn, which removes the
   `restore-lantern` offers in R14-R16. The design's D6 ("D must verify completed swap stays complete", "one finite light
   choice per unchanged readiness") adds equipment-side rules on top. Required: exclude R14-R16 from D's change set
   (keep them in the record table as "no change; retirement correct; A owns"), make D6 a single control test on the
   `autorecover-20261012-231248` capture after A lands, and drop the "finite light choice" rule from D. R13 stays in D
   (G3, not a light row). The planned B fix (pack space -> depart with current gear) touches none of the 16 rows.

## Should-fix

- D0 should also log which seam published the retirement (`policy.py:2994` vs `:3069` vs final `:3086`), the recurrence
  key and count, and `_last_pair`; the design already says the trigger is underdetermined, so make D0 answer it.
- Gate 2 (24 active hours per cohort, 20 visits, 3 dives) is measurable from `autorecover.jsonl` + decision rows only
  after D0 adds the visit epoch; say that D0 is a prerequisite of starting the clock. "A town no-progress alternation with
  no retirement fails the gate" needs a concrete detector: use the existing `TOWN_BLOCKED_STOP_LIMIT`/residence 1500 stops
  plus the D0 own-decision counter, and state the threshold.
- G2 (R2): rows 4204-4211 show the loop continued after forgiveness (seq 35 = seq 31); the design should say what ended it.

## Open questions for the owner (real decisions only)

1. Design line 208-214 wants per-visit receipts/minima to survive an autorecover restart. The 10-09 decision excludes
   carry-over across restart. Keep 10-09 (bounds reset on restart; the 3-restart/24h gate is the outer bound), or allow
   this one in-visit ledger file for D?
2. R14-R16 (3 of the 4 low-level records) are owned by step 3 A (light-swap-1013). Confirm D changes nothing for them
   and A's qualification is measured separately, so D's gate does not wait on A.
