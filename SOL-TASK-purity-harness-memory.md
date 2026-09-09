# SOL-TASK: the town-producer purity harness holds 8.9 GB of parsed snapshots

This is the root cause of the memory incident that made the machine unusable and forced the user's
hard 16 GB budget. It is a TEST HARNESS defect, not a policy defect.

## Measured

`tests/town_producer_purity_matrix.py:274` eagerly parses and retains every in-town snapshot of both
incident captures for the whole test:

```python
snapshots_by_capture = {
    capture: _snapshots(capture)[0] for capture in CAPTURES
}
```

Measured on this machine:

```
RSS before parsing captures:     39 MB
  equip-swap      snapshots=145
  no-actionable   snapshots=226
RSS after:                    8,948 MB     (+8,909 MB)
```

**14.2 MB of JSONL on disk becomes 8.9 GB of live objects — about 630x.** Per-snapshot cost measured
directly: **20.7 MB each**, because one snapshot carries ~10,342 `GridState` objects.

Per-module RSS growth, one process, modules run in sequence:

```
tests.test_town_producer_purity_part5     1 test     +9,000 MB    <- this module alone
tests.test_town_acquire_bypass_recorded   4 tests      +227 MB
tests.test_equipment_optimizer           78 tests        +0 MB
(10 heavy policy modules, 1,055 tests, total growth 127 MB)
```

There are six such partitions (`part1`..`part6`), each loading the same 8.9 GB. Two suites running
concurrently reached 40 GB.

## What this is NOT — three supervisor hypotheses that measurement refuted

1. "Tests read the 5 GB `home-entry-capture.jsonl`" — they do not. Tests read committed fixtures
   (74 MB compressed) and these two incident JSONLs (14.2 MB).
2. "Memory accumulates across modules in one worker process" — it does not. 1,055 tests across ten
   heavy modules grew 127 MB total, with deltas going both up and down.
3. "The 10.7 MB checkpoint pickling dominates" — it does not. Partition 4 makes ~372
   `observable_policy_state()` calls at ~2.3 MB each ≈ 0.8 GB of transient pickling, an order of
   magnitude below the 8.9 GB of retained snapshots.

## The fix

Each cell names exactly one snapshot:

```python
snapshots = snapshots_by_capture[cell.capture]
snapshot = snapshots[cell.row]
```

So the harness only needs the rows its own partition references — a partition is 186 of 1,116 cells.
Parse lazily, keyed by `(capture, row)`, and do not retain rows the partition never asks for. An LRU
or a per-partition prefetch of just the referenced rows both work; choose one and say why.

### Hard requirements

1. **The check must not get weaker.** Same cells, same order, same snapshots, same assertions. This
   is purely about WHEN a row is parsed and WHETHER unreferenced rows are retained. If a lazy scheme
   would change which snapshot a cell sees, stop and report.
2. **Measure it.** Report RSS for `tests.test_town_producer_purity_part5` before and after, using
   the same one-module-per-process method that produced the +9,000 MB figure above. A repair that
   does not move that number is not the repair.
3. **All six partitions.** `part1`..`part6` share the harness; report the RSS of each after the fix.
4. **No new guard constant, latch, or budget.**
5. **Operational limits still apply**: suites run SEQUENTIALLY, total process memory under 16 GB.
   A watchdog kills `test_timing_runner` / `test_parallel_runner` workers above that.

## Expected payoff

If a partition drops from ~9 GB to a few hundred MB, `--workers` can return from the emergency 2 to
the normal 6, and a full suite returns from ~40 minutes to the ~7-10 minutes it used to take. That
payoff is the reason this task outranks the other queued memory work.

## Related but separate (do not fix here)

`_threat_prediction_memo` keys on `id(snapshot)` and stores `(snapshot, result)` so it can guard
against id reuse (`policy_combat.py:1714-1720`). It holds whole snapshots and is 2.33 MB in a live
checkpoint. That is a real defect for CAPTURE size, and the user has approved fixing it, but it is
not what makes this test take 9 GB.
