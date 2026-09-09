# SOL-TASK: `town:blocked:departure-unsatisfiable` — a three-way sealed absorbing state

The bot stopped itself in town at turn 1736334 with `town:blocked:departure-unsatisfiable` and has
not produced a decision since. CL23, HP 406/406, gold 3565 — no danger, no progress.

**The user's standing instruction is that an unmeetable quest requirement means go explore or mine,
never stop.** Quest readiness is NOT what stopped it (`quest_carry_ready` is OK). The town departure
gate is, and the bot cannot reach the dungeon at all.

Every figure below was produced by restoring a live predecision checkpoint from
`jsonlog/home-entry-capture.jsonl` and driving public `choose_key`, then evaluating the predicates
on that same instance.

## Only two of 26 departure leaves are false

```
equipment_departure_ready   FALSE
home_candidate_resolved     FALSE
(the other 24 — recall/food/light/quest_carry/teleport/hp/mp/organization/... — are OK)
```

`_town_departure_conjuncts` is `policy_town.py:772`.

## The equipment leaf, and why it cannot clear

`_prepare_equipment_optimization` returns `blockers=('equipment-transaction-failed',)`,
`transaction=None`, `ready=False`; `_equipment_transaction_session is None`;
`_current_worn_loadout_confirmed` False. The blocker comes from
`_equipment_transaction_failed_items`, currently holding two keys:
`identity:e4cc76ab18be2ac6` and `pack:e4cc76ab18be2ac6:0`.

That set is cleared in exactly two places:

1. `policy_observation.py:516` — inside `if not snapshot.in_town:` — **only on leaving town**.
2. `policy.py:7889` — gated on `_equipment_failure_unexecutable_this_visit(...)` returning True.

Path 1 is unreachable: leaving town is what the blocker forbids.

Path 2 is the intended escape valve (`policy_equipment.py:2095`). Its seven clauses were evaluated
on the live state:

| # | clause | measured |
|---|---|---|
| 1 | blockers == `('equipment-transaction-failed',)` | True — passes |
| 2 | `_equipment_transaction_session is None` | True — passes |
| 3 | `_current_worn_loadout_confirmed` | **False → returns False** when `require_confirmed=True` |
| 4 | `_home_owner_goal_pending` | False — passes |
| 5 | `STORE_HOME not in _town_store_attempted` **and** `_town_need_supplier_reachable(Home)` | **True and True → returns False** |
| 6 | `_equipment_quarantine_readmitted_ids` | empty — passes |
| 7 | `_equipment_quarantine_second_chance_ids` | empty — passes |

**Clause 5 is the seal.** It reasons "Home has not been attempted this visit and Home is reachable,
so there is still equipment work to do" — and refuses to retire. But `_town_store_attempted` is
per-visit state, `_home_candidate_waiting` is True so the Home work never completes, and departure
never opens, so the visit never ends and Home is never marked attempted. Clause 3 is independently
false, so even the `require_confirmed=False` call at `policy.py:7880` stops at clause 5.

**All three release paths are blocked by the very state they would release.**

## This is a known defect class, twice over

- `bot-absorbing-survival-state`: the exit is not bot-reachable. The Home-deferral absorbing state
  repaired earlier today (commit `4ca8361`) had exactly this shape — its clear also required a
  transition that the blocked state itself prevented.
- `bot-alternating-owner-defect-class`: equipment work waits for Home work, Home work does not
  complete, neither retires.

## The work

**D1 — break the seal.** The governing principle, already established by the earlier repair: **a
release condition must not depend on a transition that the blocked state itself prevents.** Clause 5
must not treat "Home not yet attempted this visit" as evidence of remaining work when the visit
cannot end. Derive the correct condition from the code; candidates: require positive evidence that
Home work is actually routable and progressing (the ledger has `unsatisfied_passes` and
`approach_fails` for exactly this, used by `_equipment_work_home_route_available` at
`policy_equipment.py:2130`), or bound the clause by the same applicable-bound logic that function
already applies. Say which you chose and why.

**D2 — `home_candidate_resolved`.** `_home_candidate_waiting` is True. It is set at `policy.py:1953`
and `policy.py:2798` / `policy_home.py:2098`, and cleared at eight sites. Determine why none fired
here, and whether D1 alone releases the deadlock. If D1 is sufficient, say so with evidence and do
NOT change the Home path — a second speculative change would confuse cause and effect.

**D3 — record, do not fix here.** The `bot-town-departure-home-skip-deadlock` note says optional
Home surplus work must not gate departure. Whether clause 5's "equipment work" is optional in that
sense is a design question; write it up if you conclude it is.

## Hard requirements

1. **Reproduce first, from the live substrate.** `jsonlog/home-entry-capture.jsonl` (269 rows, all
   with `predecision_policy_checkpoint_pickle_b64`). The last usable row reproduces the exact state:
   two false leaves, `blockers=('equipment-transaction-failed',)`, clause-5 seal. Pin THAT, through
   the real producer on one instance — PIN-FIDELITY at `../.claude/skills/bot-ops/PIN-FIDELITY.md`.
   A hand-built policy with `_equipment_transaction_failed_items` assigned directly is NOT
   acceptable as the primary pin.
2. **The bot must LEAVE, not merely stop differently.** The acceptance condition is that from the
   captured state the policy reaches a departure or dungeon-directed decision — not a different
   `town:blocked:*` reason. Pin the actual transition.
3. **Do not weaken a real gate.** Genuinely outstanding, routable equipment work must still hold
   departure. Pin that case too: a state with reachable, progressing Home equipment work must NOT
   retire early.
4. **No new guard constant, latch, or budget** (standing anti-enbug rule). The ledger counters and
   applicable-bound helpers already exist.
