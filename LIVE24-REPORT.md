# live24

Worktree: `C:\hengband\bot-client-live21`, branch `live24`, starting commit `70b9772b`.
Only this worktree was written. Runtime/game files and other worktrees were not changed.
`EXPECTED_FIRST`, fixture hashes, recorded expectations and thresholds were not changed.

## Causes and fixes

References below use the final source line numbers; the offending changes were introduced by `6a9dcdcb`.

| Reported failure | Cause and fix | Evidence / remaining verification |
| --- | --- | --- |
| 1. `BountyCashoutTest.test_unreachable_office_never_latches_a_town_block` | `src/hengbot/policy.py:16196` and `:16213`: live22 replaced both unavailable-office skips with a sticky `town:blocked:bounty-office-*` WAIT. Restore `None`; offer a named quest-request no-step release so an existing ON holder can relinquish the route without a silent-holder stop. | Bounty tests and restored-holder/closed-in-office pins pass. Restoring the old method makes the pins fail. |
| 2. `TownTurnArbiterAcceptanceTest.test_recorded_bounty_approach_does_not_spend_stall_budget` | `src/hengbot/policy_town.py:167`: after the family move, the quest-request branch only found an office goal through the per-decision slot. The recorded read-only vector calls have no slot; the old store-router office branch was unreachable. Add office lookup when no matching slot exists. | Keep all recorded distances and budget assertions; change the expected locomotion family to quest-request. Full module passes. |
| 3. Goal typing prefix test, two subtests | `src/hengbot/claim_goal_typing.py:483`: the arbiter registered `bounty:` for quest-request but the typing table had only its specific children. Add a Terminal fallback row; `bounty:approach` remains the more specific Reach row. | Full closure module passes, including prefix resolution. |
| 4. Departure overweight replay, extra difference at index 57 | `src/hengbot/policy_town.py:810` and `:1190`: live22 applied bounty's declared-goal override and repeated-route stop to every matching Reach owner. Index 57 is recorded as `9`, `town-progress-invariant:defect:shop:approach=>town:entrance-step-off:home:scan-step-off`, not a bounty decision. Restrict both additions to bounty reasons with a quest-request slot. | Recorded row read directly; non-bounty progress and resolution pins pass, including restored checkpoints. Full replay pending Claude. |
| 5. Town replay, extra difference at index 1943 | Same two overscoped additions at `policy_town.py:810` / `:1190`. Recorded index 1943 is `1`, `shop:approach` (historical sequence 1940), not the live22 bounty loop. Restore the pre-live22 non-bounty path. | Recorded row read directly; unit containment pins pass. Full replay pending Claude. |
| 6. Town S3 measurement missing sequence 1941 | The same broad progress/route changes alter the router claim before the Home request, removing the recorded router-to-home-errand violation. Preserve the original non-bounty path instead of editing the expected violation list. | Suite-ca369103 log establishes the missing row. Exact contribution of the two source changes and restored metrics still require Claude's forbidden long replay. |
| 7. Tour S3 measurement missing sequence 3052 | The same broad progress/route changes remove the expected router-to-home-scan handoff measurement. Restrict the bounty fix instead of changing the expected list. | Suite-ca369103 log establishes the missing row. Exact contribution of the two source changes and restored metrics still require Claude's forbidden long replay. |

The bounty sequence remains quest-request-owned, asks its family gate, retains `bounty.resume`, and measures movement against its declared office destination. Its repeated ineffective route still stops visibly. No new attributes were introduced; changed behavior has restored-checkpoint pins.

## Verification

Each module ran in its own Python process, with `PYTHONPATH=src;tests;scripts` and the installed Python 3.13 executable (not WindowsApps).

| Module | Tests | Final result |
| --- | ---: | --- |
| `tests.test_policy -k Bounty` | 8 | PASS |
| `tests.test_town_arbiter` | 29 | PASS |
| `tests.test_ownership_s2a1_closure` | 80 | PASS |
| `tests.test_live22_bounty` | 12 | PASS |
| `tests.test_live23_home_cycle` | 6 | PASS |
| `tests.test_town_progress_invariant` | 22 | PASS |
| `tests.test_ownership_s2a_classification` | 16 | PASS |
| `tests.test_test_fakery_lint` | 13 | PASS |

Total: 186 tests. Targeted checks and baseline failures are not included in that total. `git diff --check` passes.

Revert checks loaded the original `70b9772b` methods into an isolated process without changing files. Reverting `_bounty_cashout_key`, `_town_result_makes_progress`, and `_town_procurement_decision` each produces assertion failures in the corresponding new pins, with zero test errors. Office-holder release and unavailable step-off also fail against the original bounty method.

The explicit stuck/withdraw exception was used for `scripts/first_divergence_s3_3.py`, one fixture and mode per process:

| Fixture / mode | Result |
| --- | --- |
| stuck OFF | 4 rows; SHA `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`, matches pin |
| stuck S33 | No difference; trajectory defect null; gate-final count 0 |
| withdraw OFF | 34 rows; SHA `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`, matches pin |
| withdraw S33 | First difference at index/sequence 3: OFF `~9\x1b`, `home:request-knowledge-scan`; ON ESC, `equipment-transaction:catalogue-leave-for-scan`. `early-divergence`, because EXPECTED_FIRST requires index 20. |

The withdraw S33 difference also reproduces with all four changed policy methods restored in memory to `70b9772b`. It predates this work; it is not accepted as a new expectation. The measurement stopped at the first difference and no post-divergence board was fed.

## Decision / follow-up needed

Keep `EXPECTED_FIRST['withdraw']` unchanged. The existing equipment catalogue continuation emits ESC on recorded sequence 3 while the required unchanged trajectory emits the Home knowledge request. A follow-up must resolve that continuation against the existing ruling and preserve the designed first difference at 20; accepting 3 by changing the pin is not a fix. No recorded non-bounty decision examined here is the live22 bounty loop.

## Pending for Claude (DO NOT RUN respected)

The inherited DO NOT RUN explicitly covers the long tour/town/overweight replays, with only stuck/withdraw excepted. Therefore these requested modules were not run:

- `tests.test_departure_unsatisfiable_weight_recorded`
- `tests.test_town_approach_retired_recorded`
- `tests.test_unaffordable_claim_tour_recorded`

Claude must verify original live decisions and S3 measurements for failures 4-7; they are not claimed green here. Other inherited prohibited checks were also not run: `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`, `scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`, `tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`, town producer purity parts, full-fixture first-divergence runs outside the explicit stuck/withdraw exception, any matching-module sweep, and full-suite/gate runners.

## Commits

- `028434cc`: Restore skipping unavailable bounty offices without a town block.
- `c77c8020`: Contain bounty progress changes and retain typed quest ownership; named office release and regression pins.
- This report is committed separately as the final reporting step.

{"topic":"live24","implementer":"gpt-6.1-sol","status":"implemented-verification-pending","commits":["028434cc","c77c8020"],"tests_passed":186,"stuck_off":"c63d582c","withdraw_off":"a9b34420","withdraw_s33":"preexisting-early-divergence-at-3","expected_first_changed":false,"pending_claude":["tests.test_departure_unsatisfiable_weight_recorded","tests.test_town_approach_retired_recorded","tests.test_unaffordable_claim_tour_recorded"]}
