# Live19 recorded cause (step 1)

Base: main adf8f3e1, branch decl-r3b. Read-only evidence:
`C:/hengband/bot-client/jsonlog/incident-20261001-0317-town-loop-calibration-unrestored-home-withdraw.{decisions,state,posted-characters,ownership-claims}.jsonl.gz`
and `incident-captures/20261001-031647-loop-detected`.

(a) OFF admission: policy.py:5875-5876 returns the producer immediately when
S3.3 is OFF; _defer_town_errand:5800-5811 likewise only enforces when ON.
The debt check at 5778 is conditional on that switch. After the calibration-owned
restore-equip session completes (policy_calibration.py:924-940), the next
_equipment_transaction_town_key calls _prepare_equipment_optimization
(policy_equipment.py:2150). That method admits a calibrated character at 660
without checking that deposited supplies are still owed. Thus 3027 opens a new
foreign session while phase is restore-supplies, and 3028 withdraws pC.
3021-3026 are calibration's own equipment executor, not this foreign session.

(b) The remaining target at 3038 is ('????? [1,+0]',31,1).
The original inventory contains it (turn 549266); 3011 deposits it in dhdg...
It is withdrawn by 3028 pC and equipped by 3031 wa: at turn 549401 and 549419
it is in equipment slot arms. The 38-item Home scan before 3034 contains no
matching gloves. The restore batch selects 17 other signatures; its observer
only clears signatures with inventory increases (policy_home.py:2040-2044,
2067-2080). It never reconciles the glove already worn. It was neither consumed
nor renamed nor deposited by 3036. 3036 dm52 deposits 52 torches from a 57-stack,
leaving five. Unknown/average gloves in Home are distinct from these known +0 gloves.

(c) Batch planning limits pack slots but ignores weight and original deposit
quantities (policy_home.py:1846-1890). It uses owner_item.count for both the
macro and confirmation, withdrawing 57 torches instead of the original five,
16 cure-critical potions instead of ten, and two unknown scrolls instead of one.
The overweight branch explicitly yields to ordinary Home deposit processing
(policy_calibration.py:1242-1253); _atomic_home_deposit_key stages the home-visit
weight-overload operation (policy_home.py:2587-2597). That is 3035-3036.

(d) _defer_unobserved_home_withdrawal retains calibration debt when cross-area
is ON and sets town:blocked:calibration-restore-target-absent
(policy_home.py:2329-2340). Its caller immediately invokes _town_entrance_step_off_key
with the generic home:atomic-withdraw-target-unobserved literal (1674-1690),
overwriting the terminal at policy_town.py:1522-1526. The stale block is also
snapshot-local (1543-1555). The retained debt keeps requesting Home and
the successful movement continually supplies a new one-step Reach; the cycle
never spends a restore-operation bound. Only the driver's 1500-decision floor
loop bound stops it at 03:16:47.

The specified shadow-report command against gzip returns zero rows because
s3_live_report.rows_in_window uses Path.open, not gzip.open. The same report
will be run against a local decompressed copy, preserving the source read-only.

Step 2 implementation and bounded verification pending.
