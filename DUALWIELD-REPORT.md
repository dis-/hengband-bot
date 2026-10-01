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
