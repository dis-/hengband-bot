# SOL-TASK: the Home-entry capture is 14 MB per row — slim it

User: 「5GBのログはどう考えても過剰だが何を記録しているか確認」→ measured → 「推奨順で着手してよい」.

## Measured

`jsonlog/home-entry-capture.jsonl` is **5.35 GB for 269 rows** — **14.2 MB per row**. With rotations
`.1`, `.2`, `.3` the capture files total **41 GB on disk**.

One row's field sizes:

```
predecision_policy_checkpoint_pickle_b64   14.20 MB   99.8%
next_snapshot_pickle_b64                    0.02 MB
decision_snapshot_pickle_b64                0.02 MB
everything else                            <0.01 MB
```

The checkpoint is a 10.7 MB pickle of `vars(policy)` — 550 attributes. The largest:

| attribute | pickled size | shape |
|---|---:|---|
| `_threat_prediction_memo` | 2.33 MB | dict, **len 2** |
| `_map_predicate_snapshot` | 2.20 MB | a whole `Snapshot` |
| `_remembered_grid_sources` | 2.19 MB | dict, 13,068 entries |
| `_town_fact_snapshot` | 2.04 MB | a whole `Snapshot` |
| `_decision_input_snapshot` | 2.04 MB | a whole `Snapshot` |
| `_remembered_grids` | 2.03 MB | dict, 13,068 entries |
| `_remembered_grid_signatures` | 0.93 MB | dict, 13,068 entries |
| `_emission_occurrences` | 0.73 MB | dict, 798 entries |
| `_monrace_knowledge` | 0.50 MB | dict, 1,417 entries — **static, reloadable from lib/edit** |
| `_town_emitted_entrances` | 0.22 MB | set, 13,068 entries |

(Individually-pickled sizes sum above the 10.65 MB total because the three Snapshots share grid
objects that one combined pickle stores once.)

Note the contrast: the separately stored `decision_snapshot_pickle_b64` is **0.02 MB**, while the
Snapshot held in policy state is **2.2 MB** — the policy-held ones carry the full remembered map.

## Why this matters beyond disk

The same bloat is behind the memory incident: test workers restoring these checkpoints reached
**10.5 GB each**, and two concurrent suites hit **40 GB**, which is why the user imposed a hard
16 GB budget. Slimming the checkpoint attacks the disk cost and the memory cost together.

## The work

Reduce what `latch_onset_capture.checkpoint()` writes. An exclusion mechanism already exists —
`latch_onset_capture._CAPTURE_STATE_NAMES` — and the town-latency round already used it to keep two
derived caches out of the checkpoint.

Candidates, in descending value. **Justify each inclusion or exclusion from the code, do not assume:**

- `_monrace_knowledge` (0.50 MB): static data loaded from `lib/edit/MonraceDefinitions.jsonc`.
  A restored policy can reload it. Strongest candidate.
- `_remembered_grid_sources`, `_remembered_grid_signatures` (3.1 MB): derived indexes over the same
  13,068 grids as `_remembered_grids`. If they are rebuildable by `_build_grid_index`, they are
  derived state, not decision state.
- `_threat_prediction_memo` (2.33 MB for two entries): a memo holding Snapshots as values. It is a
  per-decision derivation; establish whether anything reads it across a decision boundary.
- The three held Snapshots: `_map_predicate_snapshot`, `_decision_input_snapshot`,
  `_town_fact_snapshot` (6.3 MB). **HIGH RISK — read the warning below before touching these.**

## Hard requirements

1. **BACKWARD COMPATIBILITY IS MANDATORY.** Four committed fixtures contain OLD-format checkpoints
   and must still restore and still produce the same decisions:
   `tests/fixtures/home-deferral-absorbing-state.json.gz`,
   `tests/fixtures/calibration-restore-batch-live.jsonl.gz`,
   `tests/fixtures/trap-sealed-floor-dungeon4-level16.jsonl.gz`, and the untracked
   `tests/fixtures/departure-unsatisfiable-live.json.gz` if present. Pin at least two of them
   restoring after the change.
2. **THE SNAPSHOT IDENTITY TRAP.** `_fixed_quest_is_offered` branches on
   `snapshot is self._map_predicate_snapshot` and `snapshot is self._decision_input_snapshot` —
   **object identity**. Dropping those attributes from the checkpoint changes which branch a
   restored policy takes, which is a BEHAVIOUR change disguised as a size fix. If you exclude them,
   you must prove by replay that no decision changes; if you cannot, leave them in and say so.
3. **ZERO BEHAVIOUR CHANGE.** `decision_equivalence` reports 0 changed decisions and replay stays
   identical 400/300. This is a storage change, not a policy change.
4. **MEASURE.** Report bytes per captured row before and after, and the pickled size of the
   checkpoint, using the same first row of `jsonlog/home-entry-capture.jsonl`.
5. **No new guard constant, latch, or budget.**

## Out of scope this round (record only)

- Rotating or capping the capture files (41 GB on disk) — the next item in the user's order.
- Why `_threat_prediction_memo` holds 2.33 MB in two entries, if you do not exclude it.
