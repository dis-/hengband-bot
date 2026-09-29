# S3.3 r8c recorded verification

Source: the r8c run log, on the code now at `16cb7678`. These are recorded
replays, not a live window. The fixed first-divergence expectations were
established before the final replay.

| Gate | Result |
| --- | --- |
| Six OFF key/reason streams | All six match their R4 SHA-256 pins below. |
| Fixed first divergence | All six match `EXPECTED_FIRST`; three diverge at the named operation boundary and three never diverge. |
| Full ON empty keys | Zero untyped empty keys in all six streams. Typed observation waits carry posted operation identity. |
| Holder-silent construction | Only the final ownership branch constructs `ownership:holder-silent:*`; the source pin passes. |

| Replay | OFF SHA-256 | First ON divergence: index / sequence / key / reason | Typed observation waits |
| --- | --- | --- | ---: |
| tour | `d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464` | 2703 / 2701 / `7` / `shop:approach` | 13 |
| town approach | `7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1` | 1179 / 1177 / CR / `equipment-transaction:atomic-deposit` | 11 |
| overweight Home | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` | 3724 / 3723 / `3` / `shop:approach` | 0 |
| Home withdraw | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | none | 0 |
| recall cancel | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | none | 0 |
| stuck prompt | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | none | 0 |

Full ON replay findings: tour had 2 later S3 violations (3054 calibration →
town-plan and 3059 calibration → home-scan), 193 `errand_deferred` rows, and
13 holder-silent decisions. Town had 3 later violations (1890 and 2033
home-errand → home-scan, 1915 duplicate purpose), 94 deferrals, and 7
holder-silent decisions. Overweight had no violations, 96 deferrals, and 15
holder-silent decisions. Withdraw had no violations, 1 deferral, and no
holder-silent decisions. Recall and stuck had none of these. The later ON
violations and stops are findings for the live confirmation, not a claim that
the recorded streams are violation-free.

The 14 newer recorded fixtures were checked for ON versus OFF stop/loop
reasons. Thirteen paired modules had no explicit new stop or loop reason:
`test_buy_deposit_loop_recorded`, `test_first_dungeon_entrance_prompt_recorded`,
`test_home_withdraw_deposit_alternation_recorded`,
`test_loot_ledger_mass_deferral_recorded`, `test_newchar_light_churn_recorded`,
`test_newchar_light_loop_recorded`, `test_newchar_town_wander_recorded`,
`test_quest34_target_dead_recorded`, `test_star_remove_curse_unused_recorded`,
`test_town_calibration_owner_retired_recorded`, `test_town_home_candidate_stall_recorded`,
`test_town_loot_store_20260926_recorded`, and `test_unseen_caster_death_recorded`.
The fourteenth, `test_town_approach_retired_recorded`, is the long town replay;
its current-commit module run passed.

Two initial sweep failures were resolved. The town recorded module is green
on the current commit. `test_test_fakery_lint` required declaration of the
released shop watch test state; commit `16cb7678` fixed it. The gates above
were measured after that correction.
