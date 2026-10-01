# Reconcile: diagnosis (STEP 1)

Scope: `fixer-reconcile-prompt.txt`, starting at merged reconcile `9b61a37d`.
Only this worktree is modified. No game, bot, executable, live JSON logs,
other worktrees, prohibited runners, or EXPECTED_FIRST edits.

All nine originally failing assertions have a legitimate equipment-choice
divergence. Their shared first decisions are:

| Pin purpose / failures | First divergence | Verdict and captured values |
| --- | --- | --- |
| Town A1 walk, A1 full stream, S2b2, S3 violations, B1 latch, B1 recall (six failures) | Index 48, sequence 47, turn 5328458: live `\x1b`n%.` / `shop:travel`; corrected `\x1b`n(.` / `equipment-transaction:travel-home` | Legitimate. Old weapon/shield keeps equipped Theoden axe, DPS 113.88679069, survival 16.80939145; selector correction chooses Home Avavir scythe with shield, DPS 157.90346946, survival 16.24382859. See `validation/reconcile/town-optimizer-evidence.json:3`. All six failures share this continuous replay; later failed walk/latch observations are consequences, not six independent first divergences. |
| Live27 mining | Index 11: live `{f.\r`, corrected `{g.\r`, both `equipment:suppress-random-teleport` | Legitimate. Old hammer/mace dual wield DPS 13.38018547; selector correction chooses hammer two handed DPS 112.01172916. See `validation/reconcile/live27-optimizer-evidence.json:3`, pin decision loop `tests/test_identify_staff_live27_recorded.py:57`. |
| ClassC2 public ammo route, residual-surplus route, guardian remedy (three failures) | Independent capture seams at sequence 11411, turn 1493887; public route expects ``\x1b`n(.`` / `shop:travel`, corrected `tb` / `equipment-transaction:takeoff`; constructed guardian seam first adds `equipment_departure_ready` to failed conjuncts | Legitimate. Old Defender spear/Avavir scythe dual wield DPS 16.81640718, survival 7.32982252; selector correction chooses spear two handed DPS 87.23033856, survival 6.97176867. See `validation/reconcile/classC2-optimizer-evidence.json:3`; public assertions originally `tests/test_classC2_departure_recorded.py:193`, `:242`, `:282`. Constructed boards are independent counterfactuals, not historical effects. |

The extraction loads only the two historical selector functions and melee
bonus function from git revision `d7429e7b`, without modifying production.
Comparisons isolate the corrected selector on the **same old arithmetic**:
`equipment_optimizer.py:1127` applies the half-max-melee filter before survival;
`:1321` uses maximum field DPS as unconstrained baseline. Therefore the
selection change occurs even without the separate launcher/ring arithmetic
corrections (`warrior_equipment_evaluator.py:258`, `:262`). This is causal
evidence of the intended selector correction, not an unexplained mock.
The old-selector capture runs pass unchanged pins: town 8, live27 1, classC2 9.
The native corrected baseline reproduces the reported 6/1/3 failures.

The recorded equipment result is a collaborator input, keyed by catalog,
current IDs, depth, requirements, and obtainable ammunition. The frozen files
contain 12/7/2 observed results respectively. Uncaptured inputs raise an error;
there is no fallback to fabricated readiness or success. Extractor provenance
and complete selected slots/metrics are committed alongside the fixtures.

STEP 1 assertion audit (verbatim):

```text
No changed pre-existing assertions or forbidden test edits.
```

Event: `{"topic":"reconcile","implementer":"gpt-6.1-sol","step":1,"verdict":"legitimate optimizer consequences","changed_preexisting_assertions":[],"assertion_audit":"No changed pre-existing assertions or forbidden test edits."}`

# Replay inputs (STEP 2)

Use frozen optimizer results only within the three named pin modules. Town
wraps its shared replay; live27 wraps its mining test; classC2 enters the wall
in setUp, including checkpoint restores and independently constructed seams.
Comments at each application cite this prompt and the specific pin purpose.
All existing assertions are unchanged. Production optimization still uses
the corrected selector and arithmetic. Fixture payload hashes normalize CRLF
to LF (R9); missing signatures fail closed.

The original native baseline is also the single wall-removal revert check:
without frozen inputs the three modules fail 6/1/3 assertions; with them the
same purpose assertions pass. No expectation or EXPECTED_FIRST is changed.

STEP 2 assertion audit (verbatim):

```text
No changed pre-existing assertions or forbidden test edits.
```

Event: `{"topic":"reconcile","implementer":"gpt-6.1-sol","step":2,"changed_preexisting_assertions":[],"assertion_audit":"No changed pre-existing assertions or forbidden test edits."}`
