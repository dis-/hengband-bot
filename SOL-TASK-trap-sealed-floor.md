# SOL-TASK: a trap line seals the floor and the hazard-allowing explore pass never runs

User reports, 2026-09-09: 「ダンジョン『迷宮』の地形忘却特性を考慮した探索になっているか確認」→
「袋小路は存在しない。かならず階段までの経路が保証されている。」→
「トラップへの対処ができずに探索が停止している可能性は？」

The last hypothesis is the correct one. Supervisor investigation below; every figure is
reconstructed by feeding the **1,888 live 16F snapshots through the bot's own
`_build_grid_index`**, not by a re-implementation.

## Two supervisor findings that were WRONG and are retracted

1. "FORGET wiped the map 741 -> 15" — **wrong**. That drop was an ordinary DESCENT: the preceding
   decision is `descend` at t=1695378 and `visited_cells` reset 333 -> 1.
2. "The bot is boxed into a 16-cell pocket" — **wrong as stated**, and the user is right that no
   real dead end exists. The BFS only traversed cells the bot had already SEEN, so unseen corridor
   counted as impassable. The pocket is not geometry.

Also retracted: the self-maintained map is NOT lost. `_remembered_known_t` et al. accumulate by
union in `policy_navigation.py:951 _build_grid_index` and are cleared ONLY on a floor change
(`policy_observation.py:598`, `snapshot.floor_key != self._floor_key`). Across all 1,861 16F
decisions the remembered cell count **never decreased once**. FORGET does not change `floor_key`,
so the bot's own map already survives it.

## What actually happened

Reconstructed 16F state at the stop (turn 1715411):

```
remembered: known=697  walkable=301  wall=396
remembered down_stairs: []          <- none ever found
remembered up_stairs:  [(8,44), (12,26)]
player: (8,14)
```

**Remembered traps: (7,10), (8,10), (8,12), (11,54).**

The bot oscillated over `y=8, x=13..18` — 4 full cycles — then `loop-detected` stopped it.
`(8,12)` and `(8,10)` sit between that segment and everything west; `(6,11)` is reached via
`(7,10)`, also a trap. **Both frontiers that a hazard-free route could otherwise reach — (8,6) and
(6,11) — are behind trap cells.**

Corroboration from the same decisions:

```
objective: "Explore and break out of dead ends"
loot: known=[(6,10), (6,11), (16,20)]  target=null  blocker="navigation-ledger:loot"
```

The loot it wants is west of the trap line, and routing to it is retired.

## The mechanism — why the trap is never disarmed

Disarm logic exists and is bounded:

```python
# policy_navigation.py:1582
if grid is not None and grid.trap:
    yx = (step.y, step.x)
    if self._floor_trap_disarm_attempts[yx] < CHEST_DISARM_BUDGET:
        self._floor_trap_disarm_attempts[yx] += 1
        return CHEST_DISARM_KEY + key + tail
```

But it only runs once a route has already CHOSEN to step onto the trapped cell. **On 16F, across
1,861 decisions, no trap/disarm reason was ever emitted** — the reasons are `explore` 1648,
`melee` 70, `seek-loot` 45, `ranged:fire` 36, `breakout:seek-frontier` 8, `probe` 1.

The explore planner is two-pass and the fallback is correct in principle:

```python
# policy_navigation.py:1364
def _plan_explore_path(self, snapshot):
    path = self._plan_explore_path_pass(snapshot, allow_damaging=False)
    if path:
        return path
    return self._plan_explore_path_pass(snapshot, allow_damaging=True)
```

`_is_avoidable_hazard_grid` (`policy.py:11278`) treats `grid.trap` as a hazard, so the first pass
cannot cross the trap line. **The second pass only runs when the first returns an EMPTY path.**

And the first pass keeps succeeding, because `_plan_explore_path_pass` stops at the first popped
cell that is either an unvisited remembered floor cell or a remembered frontier — and inside the
trap-free segment there is always such a cell. The ledger shows all six oscillation cells visited,
with `(8,14)`, `(8,15)`, `(8,16)`, `(8,18)` recorded as probed frontiers. With `VISIT_PENALTY` and
`BACKTRACK_PENALTY` shuffling which end is cheapest, the goal alternates between the two ends of the
segment forever.

**So the hazard-allowing pass — the only path to the disarm branch — is never reached, because the
hazard-free pass never fails.** A non-empty path is treated as success even when it leads nowhere.

Compounding it: `policy.py:5211` explicitly disables the stuck-escape / Word-of-Recall exit on a
forgetting maze (`and (not forgetting_maze or completed_forgetting_maze)`). The one remaining valve
was `loop-detected`, which stopped the bot.

## The work

**D1 — the real defect.** A hazard-free path that cannot reach any NEW information must not count as
success. Establish the right criterion from the code (candidates: the goal is a cell already visited
this cycle; the reachable hazard-free frontier set is exhausted; the planner returns a goal inside
an oscillating set) and make the hazard-allowing pass run in that case, so the disarm branch at
`policy_navigation.py:1582` can fire and `CHEST_DISARM_BUDGET` can be spent.
**Do not simply always run the hazard-allowing pass** — that would walk the bot onto traps whenever
a hazard-free route merely looks longer. Say what criterion you chose and why.

**D2 — investigate, then propose.** `policy.py:5211` disables the recall escape on forgetting mazes.
With D1 fixed the bot has a way out through the trap, so the escape may not need touching. Determine
whether the disable is still correct, and PROPOSE rather than implement if changing it is a policy
decision (spec-change-propose-not-implement).

**Record, do not fix:** the telemetry reports `open_frontiers: 300` while the supervisor's
reconstruction of the same state finds 7 frontier cells (2 reachable). That may be a definitional
difference rather than a defect, but a number that far from the actionable count is a poor operator
signal. Note it as a task candidate.

## Hard requirements

1. **Pin it from the live substrate.** The 16F snapshots are in `jsonlog/bot-state-fixed.jsonl`
   (`floor.dungeon_id == 4 and floor.level == 16`, 1,888 of them) and reconstruct through
   `parse_snapshot(data, monrace_knowledge)` + `policy._build_grid_index(s)`. Build the pin through
   the REAL producer on ONE instance — PIN-FIDELITY at
   `../.claude/skills/bot-ops/PIN-FIDELITY.md`. A synthetic corridor with a hand-placed trap is NOT
   acceptable as the primary pin.
2. **No new death path.** Stepping onto traps is a damage source. The pin set must include a case
   where a hazard-free route to genuinely new information still WINS over the trap route.
3. **No new guard constant, latch, or budget** (standing anti-enbug rule). `CHEST_DISARM_BUDGET`
   already exists and already bounds the disarm attempts.
