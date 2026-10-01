# Recorded dual wield investigation

Step 1: the AC-100 floor is real; the dump is not evidence of a small penalty.
`src/view/display-player-middle.cpp:53` adds `skill_thn / 3` to the displayed
weapon bonus. The recorded ~f row at T1491464 gives two-weapon experience **4556**
and shield experience **4000**. `warrior_optimization.py:730` passes that value
unchanged. The record's other combat inputs are level 25, natural STR 155,
natural DEX 69, melee skill 175 and shooting skill 130. Reconstructed evaluation
exactly reproduces the report's dual 16.816407183591124 and scythe
178.3940894773091, including both hands' damage per hit.

Source arithmetic (`player-status.cpp:1847,1866`): 4556 // 160 = 28;
spear penalty = 100 - 28 - (130 - 50) / 8 + 10 = **72**;
scythe penalty = 100 - 28 - trunc((130 - 250) / 8) + 10 = **97**.
STR index 29 and DEX index 23 contribute 9 + 4 = 13. Both weapon
proficiencies (4988, 4952) contribute 4, and body armor contributes -2.
Thus hand bonuses are 13 + 4 - 2 - 72 = **-57** and
13 + 4 - 2 - 97 = **-82**. The dump adds weapon bonuses 11/8 and
175 // 3 = 58, giving **+12 / -16**. Damage bonuses are 10 + 1 = 11
and 10 + 0 = 10, so the dump gives **+21 / +18**. Blows are **5 / 4**.
Actual AC-100 reliabilities are **37 / -47**, both at the **5% floor**.
No guessed or increased two-weapon experience is justified.

The evaluator's `_distributed_bonus` (`warrior_equipment_evaluator.py:257`)
incorrectly includes the sling's +7/+7: +4/+4 on the main hand and +3/+3
on the sub hand. It consequently reports -53/-79 and +15/+13. It also
omits the sub-ring bonus in two-handed mode, contrary to the two-handed
case in `player-status.cpp:2313`. The recorded rings have zero attack bonuses.

Rank 1 was selected by `_stable_operational_best`
(`equipment_optimizer.py:1128`), before `_prefer` sorts alternatives:
no candidate clears the existing 30-turn survival floor; the 95%-of-max
survival filter retains the dual's 7.329822524588722 and discards the
scythe's 5.914599384189424. Their combat margins are -29.644514547823675
and +2.429195190727497. The extra acid/poison coverage changes modeled
survival, not a direct resistance-count score. Both satisfy the 20F
free-action/fire gate. The band loop (`equipment_optimizer.py:1308`)
uses this same survival-selected dual as `melee_free` = 16.816407183591124;
the chosen band also selects it, so its ratio is 1.0 and the half-melee
guard cannot detect the loss.

The spear alone, with the same armor and rings, has old modeled melee
**110.50802295384614**, 4 blows, 74% hit chance, 37.33379153846153 damage/hit,
6.971768672899432 survival turns and +1.3452495213196318 margin.
The original report stores only three ranks, none containing this loadout.
Its exact historical rank is **not recorded**. The preserved raw board/home
plus recorded deposits reconstruct 40 items and 6588 candidates rather than
the report's 7830. Therefore an exact historical rank must not be asserted
from that reconstructed pool. This evidence gap remains explicitly open.

Fixture provenance: board T1493274, Home knowledge T1492540, ~f T1491464,
and pre-deposit board T1493262 from `jsonlog/bot-state-fixed.jsonl` in the
read-only main checkout. The live decision at 16:16:23 sends
`dkdjdd\\x1b`; the pre-board maps j to shovel and k to pickaxe, and both
are absent in the next board. The fixture keeps the source records verbatim.
Calibration and the original report are also copied from read-only jsonlog.
The reconstruction script does not emit game commands or change live state.

Relevant user decisions: the authoritative AGENTS.md table says required
abilities are specific to each band and to maximize offense/defense within
that gate. The 2026-07-24 decision in
`C:/Users/user/.claude/projects/C--hengband/memory/bot-session-handoff.md`
approves the 30-turn survival-first safety net below the floor. The
2026-09-16 `empty-slot-preference-decision-20260916.md` orders filling empty
slots on equal evaluation, before preserving the current equipment; it
does not authorize sacrificing melee for additional occupied slots.
The current task explicitly forbids losing most melee for extra resistance
coverage beyond the band requirements. Any implementation must reconcile
that instruction with the existing below-floor survival selection.

Step 2 implements the current directive using the **existing half-melee
limit**, with no new threshold. Within the requirement-valid candidate pool,
reject candidates below half of the maximum melee before applying survival
selection. Then retain the approved 30-turn survival rule and existing tie
breakers within that bounded pool. The unconstrained band baseline is now
the actual maximum melee, rather than the survival-selected winner.
Required abilities remain enforced before this comparison. No skill input
is increased to make dual wield look better.

The evaluator excludes launcher to-hit/to-damage from melee and includes
both rings for a two-handed weapon. Future loadout reports retain combat
inputs and each hand's to-hit, to-damage and hit reliability.

Corrected recorded-input metrics (AC 100, same representative encounters):

| Loadout | Melee per turn | Blows | Hit chance | Hand to-hit / to-damage | Survival turns |
| --- | ---: | --- | --- | --- | ---: |
| Spear, two hands | 87.23033856 | 4 | 72% | +28 / +16 | 6.97176867 |
| Scythe, two hands | 153.10963194 | 4 | 71% | +28 / +16 | 5.91459938 |
| Spear + scythe | 15.19430805 | 5 + 4 | 5% + 5% | -57 / +11; -82 / +10 | 7.32982252 |
| Fixed optimizer choice: spear, two hands | 87.23033856 | 4 | 72% | +28 / +16 | 6.97176867 |

The spear retains 56.972% of the best available melee (the scythe), so it
passes the half-melee limit; its modeled survival is higher. The dual retains
only 9.924%, so optional coverage cannot keep it in contention.

Verification, one test module per process, PYTHONPATH=src;tests;scripts:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_dualwield_recorded | 6 | PASS |
| tests.test_policy_equipment | 192 | PASS |
| tests.test_equipment_optimizer | 93 | PASS |
| tests.test_warrior_equipment_evaluator | 11 | PASS |
| tests.test_warrior_loadout_evaluator | 11 | PASS |
| tests.test_warrior_loadout_search | 19 | PASS |
| tests.test_warrior_optimization | 36 | PASS |
| tests.test_ownership_s2a_classification | 16 | PASS |
| tests.test_test_fakery_lint | 13 | PASS |

Total: **397 passing tests**. No existing assertion was changed. The named
equipment_optimizer/warrior_equipment/warrior_optimization/loadout test
modules are the five matching test modules listed above; recorded_loadout.py
is a replay helper, not a unittest module. Verification used the installed
Python313 executable; the documented Codex runtime executable is absent on
this machine. Reverting all three production files to b24fd077 gives four
failures and one error in the six new pins; restoring them gives six passes.
No production state attribute was added, so no new checkpoint field exists.

stuck OFF: 4 decisions, identity hash c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5;
stuck S33: no divergence, no trajectory defect. withdraw OFF: 34 decisions,
identity hash a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9;
withdraw S33: expected first divergence at index 3, historical/off
`~9\\x1b` (home:request-knowledge-scan), on `\\x1b`
(equipment-transaction:catalogue-leave-for-scan), no trajectory defect.
No later recorded board is claimed to show the effect of the divergent key.

Both pre-commit assertion audits:

```text
No changed pre-existing assertions or forbidden test edits.
```

Pending for Claude, not run: scripts/test_parallel_runner.py,
scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py,
scripts/mutation_battery.py; tests.test_cli, tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states; long tour/town/overweight
replays, town-producer purity sections, full-fixture first_divergence runs,
and broad matching-module sweeps. The authorized stuck/withdraw exceptions
were run. Also pending: recover the exact historical 7830-candidate catalog
to establish the spear's original rank; the available report does not store it.
