# SOL-TASK: town decision latency — `_fixed_quest_is_offered` recomputed ~4,000× per decision

User report (2026-09-09): 「町移動が凄まじく遅い。調査して改善。」

Supervisor measurements below are from the live decision log and from a cProfile run over captured
predecision checkpoints replayed through the real public path. Nothing here is inferred from
reading code.

## The shape of the problem

Live decision log, town vs dungeon (medians):

| | n | total | choose_key | parse_snapshot | poll_wait | nearby_grids |
|---|---:|---:|---:|---:|---:|---:|
| TOWN | 1408 | 253 ms | **106 ms** | 22 ms | 65 ms | 1185 |
| DUNGEON | 985 | 80 ms | **8 ms** | 12 ms | 44 ms | 621 |

Where the town wall-clock actually goes, summed over those 1,408 decisions:

```
total_ms            909.0 s
choose_key_ms       575.3 s   <- 63%, POLICY COMPUTE
poll_wait_ms        158.9 s   <- 17%, waiting on the game
parse_snapshot_ms    75.8 s   <- 8%
everything else       ~6 s
```

The slowest town reasons are dominated by `choose_key`, not by waiting:

| reason | n | total | choose_key |
|---|---:|---:|---:|
| `store:entry-await-observation` | 51 | 3482 ms | **2833 ms** |
| `home:leave-for-pending-withdraw` | 8 | 3919 ms | **3554 ms** |
| `town-progress-invariant:defect:seek-loot=>seek-loot` | 14 | 3722 ms | **3040 ms** |
| `shop:travel` | 36 | 1470 ms | 782 ms |
| `shop:approach` | 61 | 1305 ms | 574 ms |

`store:entry-await-observation` is a WAIT decision that spends 2.8 seconds computing. That is the
signature of an unconditional cost paid before the branch is chosen.

## The hot spot, from cProfile

Two captured town decisions replayed through `restore_checkpoint` + public `choose_key`:

```
=== home:route-claim-unfulfilled  (snapshot grids=0)     1.469 s ===
  3984 calls  0.712 s tottime   policy_quest.py:4301 _fixed_quest_is_offered
=== periodic:game-save            (snapshot grids=3257)  1.738 s ===
  2473 calls  0.835 s tottime   policy_quest.py:4301 _fixed_quest_is_offered
```

**`_fixed_quest_is_offered` is ~48% of `choose_key` in both samples, and it is the ONLY function
with significant `tottime` — everything above it is pass-through.**

The call chain that multiplies it (counts from the first sample, per SINGLE decision):

```
policy_town.py:1113  _town_need_candidates            11 calls
policy_home.py:635   _retention_surplus            1,316 calls
policy_home.py:361   _retention_reservation        1,336 calls
policy_home.py:371   _retention_reservation_detail 1,336 calls
policy_supply.py:675 _carry_procurement_strategy   1,328 calls
policy_quest.py:3962 _fixed_quest_head             1,328 calls
policy_quest.py:4301 _fixed_quest_is_offered       3,984 calls   <- 3x per head
```

`_fixed_quest_is_offered` builds a set by scanning `snapshot.grids.values()` — 3,257 grids in that
snapshot, up to 10,816 in an open town view. Four thousand scans per decision.

**Note the first sample had `grids=0` and still cost 1.47 s.** The cost is NOT proportional to the
grid count in the way the town/dungeon split first suggested; town is slow because the town code
path (`_town_need_candidates` → retention → carry strategy → quest head) is what runs there.

## The repair

Memoise per snapshot. The derived values are invariant for a given snapshot:

- the building-special set derived from `snapshot.grids`,
- `_fixed_quest_is_offered(snapshot, quest_id)` for each quest id,
- and, if it is equally safe, `_fixed_quest_head(snapshot)`.

There is precedent for snapshot-scoped reasoning inside this very function: it already branches on
`snapshot is self._map_predicate_snapshot` and `snapshot is self._decision_input_snapshot`, i.e. on
snapshot IDENTITY.

### Hard requirements

1. **ZERO BEHAVIOUR CHANGE.** This is a pure performance repair. `decision_equivalence` must report
   **0 changed decisions** and replay must stay identical 400/300. That is the acceptance condition,
   not a formality.
2. **Cache by snapshot IDENTITY, and make staleness impossible.** A cache that survives into the
   next decision is a correctness bug, and a wrong quest-offer answer is exactly the
   `abilities-parse` class of defect that once granted all 19 abilities from a truthy dict. Key on
   `id(snapshot)` plus a held reference, or clear at the public `choose_key` boundary — and pin the
   invalidation with a test that fails if the cache leaks across decisions.
3. **No behaviour-shaped state.** The cache must not be added to `home_entry_capture.STATE_FIELDS`
   or the flight recorder as if it were decision state; it is a derived cache. If it must be
   pickled-safe, prove `latch_onset_capture.checkpoint()` byte-size and hash are unchanged, as the
   Phase 13 review did.
4. **Measure and report.** Re-run the same two captured decisions before and after, and report
   `choose_key` wall-clock and the `_fixed_quest_is_offered` call count for each. A repair that does
   not move those numbers is not the repair.

### Out of scope for this round

Do NOT restructure `_retention_reservation_detail`'s 1,336 calls per decision or
`_town_need_candidates`. They are suspicious but they are a separate design question; fixing the
memoisation should collapse most of their cost for free. Report what the profile looks like AFTER
the memoisation so the next target is chosen from measurement, not guesswork.
