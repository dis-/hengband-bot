# live31 — diagnosis (step 1)

Base: dcb3fed7; worktree: bot-client-decl-r3b, branch decl-r3b.

Recorded evidence: incident-20261001-1235-calibration-restore-target-absent-2.state.jsonl.gz
and .decisions.jsonl.gz, copied without changing boards into the live31 fixture.
No game, live bot, logs, or other worktrees were modified.

The outstanding signature is `('岩石溶解の魔法棒 (25回分)', 65, 6)`.
At turn 1086352, inventory e contains count=3, charges=pval=25. The deposit
macro is `dhdg2\rdf2\rde3\rdddcdb10\rda13\r`. At terminal turn 1086783,
Home slot 14 contains the same kind with count=4, charges=pval=28 and name
`岩石溶解の魔法棒 (28回分)`. These mappings were printed directly from the
recorded JSON. This is pooled wand charge/count merging, not consumption.
The first and second historical restore macros leave precisely this debt.
An unchanged-code replay printed the same two macros and then
`town:blocked:calibration-restore-target-absent`.

The extra `way` equips the West-country mace; `wb` equips the Pattern war
hammer. Neither is the missing wand. `town:recover` posts `R&\r`, a rest,
not a use command. The final inventory contains neither the wand nor its
charge-renamed equivalent; the final Home catalogue positively contains it.

Existing identity handling before the fix:

| Change in calibration window | Current handling / location |
| --- | --- |
| Identification, awareness, newly revealed flags or bonuses | Misses: equipment_optimizer.py:356-385 hashes name and knowledge fields; policy_home.py:116-130 compares this digest. |
| Merge/split stack count | Handles count and staff `Nx` name prefix: equipment_optimizer.py:400-404; owed quantities: policy_home.py:2031-2051. |
| Pooled wand charges when merging/splitting | Misses: name and pval both hashed at equipment_optimizer.py:364,383. This incident is positive recorded evidence. |
| Inscription / printed annotations | Misses name changes: equipment_optimizer.py:364. |
| Charge use / recharge | Misses device name/pval changes. No charge-use command in this recorded calibration window; do not infer consumption from absence. |
| Light fuel / recharge timeout | Light name ignored: equipment_optimizer.py:362; timeout is excluded. |
| Wear/wield/takeoff, inventory relabel | Positive worn/carried observation: policy_home.py:73-109; physical slots excluded from move identity. |
| Consumption/destruction | No general positive command/effect reconciliation here. Restore batch observes actual quantity gain at policy_home.py:2223-2239. A disappeared item remains a typed terminal at policy_home.py:2503-2534; rest alone cannot prove consumption. |

The repair must compare observed physical properties with their transport
semantics: quantities and pooled resources can change; per-staff charges still
distinguish live28's debts. Previously known equipment properties cannot be
discarded just because identification or a printed annotation changes.
