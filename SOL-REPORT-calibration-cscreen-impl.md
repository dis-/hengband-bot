# Equipped C-screen calibration implementation - 2026-10-02

Implemented in `C:/hengband/bot-client-c2`, branch `calib-design`, against `d77817f2`. The live bot, game, executable/emitter, other worktrees, and live JSON logs were not modified. The supplied design and review requirements R1-R7 were applied. Verification evidence is in [CALIBRATION-VERIFICATION.json](CALIBRATION-VERIFICATION.json).

| Requirement | Implemented behavior and evidence |
| --- | --- |
| R1 | Missing, stale, ambiguous or unsupported calibration skips optimization and permits departure with current equipment. The calibration-required terminal mapping is removed. Real equipment transactions retain their own obligations. Required depth abilities still use current `ability_sources`; the current-gear pin checks chaos/nether refusal independently and covers a blocked Home. |
| R2 | Parse natural Base values up to 148 and apply `M(N, I+E)` once. Invert drained Current within the visible Base ceiling; floor ambiguity uses the minimum candidate. Saturated Actual/Current is a lower bound, not a blanket rejection. Only STR/DEX/CON constrain arithmetic consistency and visible Base epoch matching. The mixed-sign pin distinguishes 23 from the old double-application result 28. |
| R3 | Freeze the real L28 CP932 dump and legacy strip record; reproduce all 12 semantic fields. Also freeze September 11/17 inputs and provenance, with a declared synthesized-from-raw English display table used only in tests. Runtime never synthesizes missing tables. Numerical results appear below. |
| R4 | Reuse the existing periodic equipped `C` dump, with `--character-dump-file` (installation default `C:/hengband/lib/user/bot-test.txt`). Require a prepared and posted request, fresh mtime/hash, correlated response sequence, matching visible identity/equipment/stat epoch, and existing character metadata. Calibration saves use atomic replacement. Old physical strip debt refuses startup with `LegacyCalibrationDebtError`, naming phase/suspension/stripped-unrestored/restore-signatures/session-target/redress-obligation as applicable; manual recovery is required once. No migration executor exists. Persisted debt is not reread on every policy turn. |
| R5 | `normalize_policy_state` is the one upgrade function used by decisions, observation, checkpoint restore and direct unpickle. Fresh/restored key sets are equal; normalization is idempotent. Restart clears observations, optimizer signature and confirmed loadout and creates a fresh session identity, so a new dump is required. Legacy strip records remain readable for historical diagnostics, but live disk loading accepts only current-session v2 observations. |
| R6 | Subtract known temporary AC/HP bonuses before deriving constants. AC chooses +100 ultimate resistance/musou over the +50 shield group, then bless +5 and berserk -10. HP accounts for hero +10, berserk +30, tsuyoshi +50 and hex extra-might +15/build-up +60 after the floor; tsuyoshi STR/CON +4 is also removed during stat inversion. Unknown timed effects defer observation without stopping. |
| R7 | Consumer single-application arithmetic and optimizer-input schema 3 were committed separately in `f3457b13`; the additional weapon comparison helper was corrected in `2fd5abd9`. Old confirmed loadout inputs are invalidated. |

L28 equivalence: natural stats `(84,15,18,61,45,10)` yield equipment-free effective stats **`(164,5,9,91,115,6)`**, neutral HP **403**, residual AC **0**, and HP floor 29. Shown HP 501 minus CON contribution 98 gives 403. The 12 equal fields are race/class/personality/level, `stat_cur`, `base_stats`, `base_hp`, `base_ac_bonus`, intrinsic abilities, pinned identities, mutation signature and intrinsic TR flags. Intrinsic abilities are cold/nether/poison resistance and see-invisible; flags are `{10,47,51,52,60,78,80}`. Observation turn/source/version/hash are new evidence metadata, not equivalence claims. Frozen dump SHA256: `789dee90dcd63d9f1fca9983f618e103c61af0d2f605cf7259d47a13e103cbe2`.

September equivalence: both inputs have natural stats `(70,12,17,18,17,15)` and effective base stats **`(150,3,8,48,78,11)`**, residual AC **0**, identical intrinsic abilities/flags and empty pins/mutations. Ten comparable semantic fields match. September 11 is L26 with base HP 367; September 17 is L27 with derived base HP 380 (447 - 67). Different-level HP is deliberately not an equality claim. `0917-provenance.json` names original JSONL line 24 and source SHA256; the display-table synthesis is explicitly test-only.

The removed production paths are deposit-all calibration, strip takeoff, naked capture, restore equipment/supplies, redress recovery, calibration Home reservations/obligations, calibration ownership declarations/delegations and departure conjuncts. [CALIBRATION-OBSOLETE-PINS.md](CALIBRATION-OBSOLETE-PINS.md) lists **179 retired unittest method IDs**, two retired absorbing-catalogue cases, retired sub-pins, and 14 preserved/renamed methods. Four historical fixture fact tests were moved into an independent module. Ordinary Home withdrawals, weight-overload deposits, command composition/quantity/one-post transport, mutation dispatch, stale one-shot and empty entry-wait assertions remain. The test-fakery declared-site ratchet decreases from 127 to 120 after removal; the undeclared set and its exact 13-instance expectation are unchanged.

One equipment pin was retired because its purported terminal checkpoint actually has no terminal latch or exhausted owner: its old "no supplier" expectation relied on calibration-required being terminal. Removing that expectation is R1, while independent launcher purchase/registration and actual equipment-failure pins remain. The complete method name and rationale are in the obsolete-pin list.

Each verified module ran in its own process with the Codex runtime Python and `PYTHONPATH=src;tests;scripts`:

| Module | Passed tests |
| --- | ---: |
| `tests.test_character_sheet_calibration` | 10 |
| `tests.test_policy_calibration` | 9 |
| `tests.test_calibration_checkpoint` | 4 |
| `tests.test_calibration_departure` | 1 |
| `tests.test_calibration_single_application` | 1 |
| `tests.test_calibration_historical_fixtures` | 4 |
| `tests.test_policy_equipment` | 191 |
| `tests.test_equipment_optimizer` | 93 |
| `tests.test_warrior_equipment_evaluator` | 11 |
| `tests.test_warrior_optimization` | 36 |
| `tests.test_dualwield_recorded` | 6 |
| `tests.test_ownership_s2a_classification` | 16 |
| `tests.test_test_fakery_lint` | 13 |
| `tests.test_stuck_prompt_staged_tail_recorded` | 4 |
| `tests.test_home_withdraw_failed_stock_present_recorded` | 6 |
| `tests.test_home_withdraw_deposit_alternation_recorded` | 2 |
| Total | **407** |

An additional **28 focused preserved/changed pins** pass: 16 Home methods, six ownership attribution/requester/completion methods, three town-arbiter suppression methods, one supply rearm method, and two shadow identity methods. These were qualified-method runs, not whole-module sweeps. The seven R1-R7 single-revert checks each failed their intended pin; original source bytes were restored after each check. Changed Python files parse; code whitespace checks pass. The complete diff against the base reports only intentional fixed-width padding / final blank bytes in the frozen CP932 dump fixtures; those bytes are preserved.

Bounded OFF/S33 measurements use only four rows per case and stop at the first changed action. No response after that change is fed. The fixture's existing stop-rung wall is retained for stuck; this is not a full trajectory/live-game proof.

| Case/mode | Rows | S3 violations | Holder-silent stops | Deferred rows |
| --- | ---: | ---: | ---: | ---: |
| stuck OFF | 4 | 0 | 0 | 0 |
| stuck S33 | 4 | 0 | 0 | 0 |
| withdraw OFF | 4 | 0 | 0 | 2 |
| withdraw S33 | 4 | 0 | 0 | 2 |

Stuck keys/reasons match across modes, including the final `ESC + backtick + n%.` approach. Withdraw first differs at index/sequence **3**: OFF `~9 + ESC`, `home:request-knowledge-scan`; S33 `ESC`, `equipment-transaction:catalogue-leave-for-scan`. This matches the untouched `EXPECTED_FIRST`. The existing withdraw module's later checks retain its declared counterfactual walls; the OFF/S33 measurement makes no action-consistency claim beyond the bounded prefix.

Commits, in order:

- `919f398b` - freeze the L28 real fixture pair.
- `f3457b13` - separate single-application consumer/schema change (R7).
- `a7c49766` - current-gear fallback without calibration terminal (R1).
- `d9fe2d38` - equipped derivation, checkpoint normalization, startup debt refusal and September fixtures.
- `2fd5abd9` - correct the weapon comparison helper.
- `e71bce52` - remove strip/restore executors and ownership paths.
- `c26adc35` - observation lifecycle, equivalence, freshness and fallback pins.
- `1ddadb46` - validate identity/epoch and request freshness.
- `e7f5e71a` - avoid per-turn persisted-debt reads; remove obsolete comments.
- `4c995499` - mixed-module phase cleanup while preserving ordinary transport and historical facts.

Remaining validation belongs to Claude's gate workflow: the forbidden broad modules/scripts and long recorded trajectories below were not run. Mixed CLI/shop/town/absorbing-catalogue changes have syntax/AST checks but no broad behavioral gate result. No live bot/game trial was performed. Initial derivation is intentionally limited to the supported Warrior/no-mutation/no-active-form envelope; unidentified stat gear, unsupported AC mechanics, unknown timed effects and floor-concealed HP rolls defer optimization safely. Permanent nether immunity is retained as a capability, but the current evaluator cannot represent it and skips optimization rather than discarding it. Expansion of those models is future work, not a fallback to strip calibration.

DO-NOT-RUN list carried into the Claude handoff:

- `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`, `scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`.
- `tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`.
- Long tour/town/overweight recorded replays; town producer purity parts.
- Full-fixture `scripts/first_divergence_s3_3.py`, full suite, and any all-matching-module sweep.

The user's preexisting untracked `REVIEW-calibration-cscreen-fable.md` is preserved and not committed. No Claude review was invoked.

{"topic":"calib-impl","implementer":"gpt-6.1-sol","implementation":"complete","broad_validation":"pending-Claude-gates","module_tests_passed":407,"focused_pins_passed":28,"revert_checks_caught":7,"retired_method_ids":179,"expected_first_edited":false,"live_game_touched":false}
