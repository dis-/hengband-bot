# SOL-TASK: calibration start timing — do not calibrate against a pending invalidator

**USER DECISION (2026-09-09, verbatim):**
「提案を許可する。較正タイミングの指定は最適化してよい。」

This APPROVES sol's Phase-D2 proposal — *do not start calibration while a drained stat has an
actionable restoration path* — AND authorizes optimizing calibration start timing more generally.
It does NOT authorize redesigning calibration itself.

## The evidence this comes from

On the live run the bot completed a full calibration cycle at t=1574209, drank a Constitution
restoration potion at t=1574597 (`restore:quaff-con`, key `qe`), and started a second identical
cycle at t=1574625 — depositing and restoring the same pack, quantities 9/29/6/87/30/2/47/29 in both
directions, net change zero.

That second cycle was **correct**, not a defect. `WarriorCalibration.stale_reason`
(`warrior_optimization.py:150-181`) invalidates the cached constants on exactly five approved
triggers, and the CON change hit one of them:

```
warrior_optimization.py:170  return "character-identity"
warrior_optimization.py:172  return "level"
warrior_optimization.py:174  return "stat_cur"      <- the potion hit this one
warrior_optimization.py:176  return "pinned-set"
warrior_optimization.py:181  return "mutations"
```

The waste was ordering: the bot calibrated, THEN did work it already knew would invalidate the
calibration.

## The principle to implement

**Do not start a calibration cycle while the bot is holding an actionable, known invalidator.**

Two of the five triggers are predictable from state the bot already has:

- **`stat_cur`** — a drained stat with an actionable restoration path (a restore potion carried, or
  withdrawable from Home, or purchasable with gold on hand). This is the approved case.
- **`pinned-set`** — a cursed worn item with an actionable remove-curse path. Same shape of
  reasoning; include it only if the actionability test is already available in the codebase and
  cheap. If it is not, say so and leave it out rather than inventing one.

The other three are NOT predictable and must NOT be gated on: `character-identity` never changes,
`level` cannot be scheduled, and `mutations` are observed, not planned.

## Hard requirements

1. **NO DEADLOCK.** If the restoration path is not actionable — no potion carried, none at Home,
   not affordable — calibration MUST proceed. A gate that waits for something unreachable is the
   `bot-absorbing-survival-state` defect class and would be a worse bug than the one being fixed.
   Prove the non-actionable case reaches calibration, with a pin.
2. **BOUNDED DEFERRAL.** The gate must be state-based, not count-based
   (`bot-town-count-retirement`): defer while the invalidator is actionable, proceed the moment it
   is not. Do not add a new guard constant, a new latch, or a retry budget
   (standing anti-enbug rule).
3. **VISIBLE.** When calibration is deferred, the reason must be observable in the decision
   telemetry — the `equipment_optimization.calibration` block already carries `phase` and
   `entry_blocker`; use the existing `entry_blocker` channel rather than inventing a parallel one.
4. **NO WIDENING.** Do not change what calibration does, what it deposits, how it strips, or the
   invalidator list itself. This task is only about WHEN a cycle may start.

## Separate finding — record, do not repair

In the observed window the calibration phase machine advanced only when the bot's own
`town-progress-invariant:defect:*` detector fired (14 times, including
`calibration:strip-installed=>...` and `boxed-breakout`). A phase machine that depends on its own
defect detector to make progress is unhealthy and deserves its own task. Note it in the ledger; do
not fix it here.
