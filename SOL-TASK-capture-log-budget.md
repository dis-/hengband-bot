# SOL-TASK: the disk budget counts the capture logs but cannot evict them

The user's disk rule is **jsonlog must total at most 5 GB** (verbatim:
「ディスク容量の圧迫のため、全ログで5GBにおさめてほしかったのだが」). The budget mechanism that
exists today cannot enforce that, and the reason is structural, not a tuning mistake.

## Measured

`jsonlog` reached **45 GB**, of which `home-entry-capture.jsonl` plus its rotations were **40 GB**.
The supervisor has since reclaimed it operationally to **2.51 GB** (deleted 2,046 stale fixer
`.log` files = 2,130 MB; truncated `home-entry-capture.jsonl` from 269 rows / 4.98 GB to the
newest 77 rows / 1.48 GB). That is a one-off cleanup, not a fix: nothing prevents the regrowth.

Two settings make regrowth certain:

```
flight_recorder.py:22   DEFAULT_CAPTURE_LOG_ROTATE_BYTES = 5 * 1024**3
cli.py:2098             --recorder-log-generations   default 8
```

5 GiB per generation x 8 generations = **40 GiB for this one log**, eight times the whole budget.

## The write rate is the primary driver, and a stall feeds it

`home-entry-capture.jsonl` does not record Home *entries*. `HomeEntryCapture.record_decision`
(`home_entry_capture.py:176`) latches `self.active = True` on the first decision where
`_home_owned` is true, and clears it only when Home ownership ends. While that latch is set,
**every decision writes a full row**, and each row carries **three pickles**:
`predecision_policy_checkpoint_pickle_b64`, `decision_snapshot_pickle_b64`, and
`next_snapshot_pickle_b64`.

**Measured** on the surviving tail: the newest 77 rows have `decision_index` 1171..1248 —
**77 consecutive decisions, one row each**, no gaps. At the observed 20.7 MB/row and the
`total_ms: 2108` measured at turn 1736334, that is **~9.9 MB/s, ~35 GB/hour**.

This closes the loop on the 45 GB: the `departure-unsatisfiable` stall is itself a Home-owned
state, so **the stall keeps the latch set and the capture bills 20 MB per stalled decision**.
The longer the bot is stuck, the faster the disk fills. Sizing the rotation alone does not fix
this; the write rate must be bounded too.

Decide and justify a bound. A capture that re-records the same stalled state hundreds of times has
no diagnostic value beyond the first few decisions — `CAPTURE_DECISIONS_AFTER_ONSET = 2` already
expresses that judgement for the latch-onset capture. State the retained history in DECISIONS.

## The defect in `prune_budget` (flight_recorder.py:491)

`total` is computed over **every file** under `self.root` (`self.root.rglob("*")`), so the pruner
correctly *sees* all 45 GB. But its eviction candidates are only:

```python
rotated = [... for path in self.snapshot_dir.glob("snapshots-*.jsonl.gz")
           if path != self.snapshot_path]
...
for path in incident_dirs: ...
```

`home-entry-capture.jsonl` and its `.1`..`.8` rotations live in the `jsonlog` **root** — neither in
`snapshots/` nor in an incident directory. **They are counted in `total` but are never candidates.**

So once the capture logs alone exceed `budget_bytes`, the eviction loop deletes every rotated
snapshot generation it can reach, never gets `total` under budget, runs out of candidates, and
returns silently. There is no warning and no ratchet.

**Corroborating artifact** (observed 2026-09-10 00:39): `jsonlog/snapshots/` contains only
`snapshots-current.jsonl.gz` (36.8 MB) and **zero** rotated generations, while
`DEFAULT_DISK_BUDGET_BYTES` is 3 GiB. A healthy pruner would let rotated snapshots occupy most of
that budget. Their total absence is exactly the predicted signature of a pruner that evicted
everything reachable and still could not reach its target.

## What to fix

1. **Make root-level rotated logs evictable.** The oldest rotated generations of root-level logs
   (`*.jsonl.1`, `.2`, ...) must be eviction candidates, oldest first, alongside rotated snapshots.
   Never evict a live (unrotated) log, and never evict `sol-events.jsonl` or its rotations.
2. **Size the capture rotation to the 5 GB rule.** `DEFAULT_CAPTURE_LOG_ROTATE_BYTES` x generations
   must fit inside the total budget with room for every other log. Propose the pair of numbers, show
   the arithmetic against the 5 GB ceiling, and state the retained history in DECISIONS, not bytes —
   the reason this log exists is Home-entry replay, so say how many entries survive.
   Note when sizing: rows written before `1aa901b` are ~20.7 MB, rows after it should be ~7.9 MB.
   **That reduction is unverified in production** — the file's last write was 15:38:59 and `1aa901b`
   landed 17:30:30, so no row in the current file was produced by the slimmed code. Measure the
   real post-fix row size on the first rows the bot writes after it resumes, and size from the
   measurement, not from the projection.
3. **The budget must not fail silently.** If a prune pass ends with `total` still over budget, that
   is a defect signal and must be recorded where the supervisor reads it. Report what you chose and
   why. Do not add a new guard constant or latch to accomplish this.

## Hard requirements

- **Runtime evidence is not yours to delete beyond the stated policy.** Only rotated generations are
  evictable. The live log, `sol-events.jsonl`, and receipts are never candidates.
- No new guard constant, latch, or budget beyond re-sizing the two existing settings.
- A pin must fail on a targeted production-only revert of each behavioural change. Run each revert
  and name the test that actually failed, with its assertion.
- The bot is STOPPED and `jsonlog/maintenance.hold` is present; both must stay that way.
  `Hengband.exe` is running — read-only observation only.

## Operational limits — hard

1. Total memory across all processes you start: **under 16 GB**.
2. **Suites run SEQUENTIALLY.** Never two full suites at once.
3. `jsonlog` must stay **under 5 GB total**. It is currently 2.51 GB. Do not create multi-GB logs;
   if a probe would write one, cap it and say so.

## Not in scope

`_threat_prediction_memo` needs no work: it is already excluded from captures
(`latch_onset_capture.py:49`, landed in `1aa901b`) and `_observe` clears it every decision
(`policy_observation.py:46`). The earlier note calling it a capture-size defect is superseded.
