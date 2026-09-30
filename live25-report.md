# live25: calibration restore weight limit

Base: `70b9772b`, branch `decl-r3b`. Evidence is the read-only live25
`incident-20261001-0812-calibration-restore-weight-limit` capture.

## Step 1: recorded cause

References below are decompressed JSONL line numbers in that capture's state log.
The committed fixture preserves them as `live25_source_line`.

* state:3991 (688489): total carried weight 2247, limit 1700.
* state:4002 (688498): after first overweight deposit, weight 2049.
* state:4013 (688511): after both overweight deposits, weight 1004.
* state:4019 (688516): after calibration pack deposit, weight 404.
* state:4037 (688636): after re-equipping, weight 404, pack empty.
* state:4051 (688644): restore response weight **1700**, exactly the limit;
  the terminal is raised because the next owed item cannot fit, rather than
  because the current board exceeds the limit.

Equipment is identical before and after calibration (state:4013,4037,4051),
with total weight 404. Level 21 and all stat indices `(27,0,5,20,24,3)` are
identical. The 72 bullets were carried before calibration; they were not a
merged-stack over-withdrawal. The actual cause is that overweight deposits
made while calibration's phase is `deposit` become restore debt too.
`policy_home.py:1316` registers all deposited quantities in that phase,
including the prior overweight disposal. The restore then brings back spare
armor/weapons (870 weight) and bullets (360), plus supplies, filling the limit.
These are heavier than the 1004 board because that board had already stashed
the armor, weapons, devices and supplies.

`policy_home.py:19` retains every restore signature after debt discharge;
`policy_home.py:1073` excludes matching items from overweight disposal during
enforced restoration. The restored corpse, recall scrolls, devices, spare
armor/weapons and bullets are all protected. Remaining restore debt cannot
fit; `policy_home.py:1858` emits the weight-limit terminal before withdrawal.
Protection makes arbitrary deposit/withdraw cycling impossible, but the debt
must distinguish required restoration from excess intentionally kept in Home.

## Verification scope

Only the expressly requested modules and stuck/withdraw OFF+S3.3 fixtures will
run, each in its own process. No EXPECTED_FIRST values will be changed.
Pending for Claude: `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`,
`scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`,
`tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`,
`tests.test_absorbing_states`, long tour/town/overweight recorded replays,
town producer purity, full-fixture `scripts/first_divergence_s3_3.py`, full suite.
