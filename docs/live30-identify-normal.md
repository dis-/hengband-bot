# Live30 step 1: recorded evidence (base c3280a6c)

Evidence: read-only `C:/hengband/bot-client/jsonlog/incident-20261001-1142-identify-normal-unrecognized.{decisions,state,posted-characters}.jsonl.gz`, stdout/stderr, and `live-screen-20261001-1142-identify-normal-unrecognized.json`.

1. Decisions JSONL line 4801 (sequence 4796) posts `pi2\r\r\x1b`; line 4802 (4797, turn 984227) posts `uoq`. Its messages explicitly say two **Word of Recall scrolls** bought for $494 and ten scrolls obtained at `g`. This was not a potion purchase. State JSONL lines 297 (store before purchase), 298 (store purchase result), 299 (player turn before identify) have the same 19 inventory addresses: `g` recall, `o` Identify staff (10 charges), `p` Identify staff (2x2 charges), `q` unknown excellent halberd. Neither the staff nor target letter shifted.
2. State JSONL line 300 (turn 984235) records `杖をうまく使えなかった。` (staff use failed), with the same inventory. Thus `o` was the correct Identify staff; the failure omitted the target chooser. The prompt file's alternative explanation (wrong staff/purchase shift) is contradicted by the recorded boards.
3. `src/hengbot/policy_town.py:1984` calls `_carried_identify_command` with the current snapshot; `src/hengbot/policy_identification.py:934` returns command + source slot + target slot without staging any chain. In contrast `policy_equipment.py:2542` stages full-equipped identify, and `input_executor.py:1155` binds its answers to observed prompt state. Normal identify therefore validates neither answer.
4. Posted-characters JSONL lines 5209-5211 send `u`, `o`, `q` under one composed `uoq`, at 11:42:18.298/299. `cli.py:2141` creates an operation with all keys when no chain is staged. `input_executor.py:1104` first reads the screen **after** posting that segment. The recorded quaff chooser is unknown to the classifier (`input_executor.py:242` lists staff/rod/scroll source prompts, not quaff); the named `stuck-prompt` at request 14713 correctly stops subsequent operations but is too late to prevent the already queued `q`.

Step 2 must stage normal carried identify, bind source and target identities separately on their observed choosers, and drop an unused target only on source-proven staff failure; unexpected choosers/ambiguous command returns must stop without the target. Recorded screens are primary. No intermediate staff/target screens were captured for this incident, so any intermediate protocol screens in pins must be explicitly declared derived, not called recorded.

## Step 2: implementation and validation

`policy_identification.py:934` composes from the caller's current board and stages normal carried identify with separate source/target gates (the live driver already selects `executor.ready_board`, `cli.py:3779`; no stale-slot cache was found). `cli.py:2569` allows the authoritative Japanese/English prompt tuple for normal identify. `input_executor.py:1145` extends the existing full-equipped binding path to normal carried identify: at each chooser it requests current state, resolves the original item identity (`tval`, `sval`, `name`) to exactly one current inventory slot, requires its visible chooser label, and validates source type/subtype. The target must be on an inventory identify page. Wrong source, missing or duplicate identity, missing visible address, another collection, or another prompt stops visibly before the answer. A fresh command boundary with the recorded staff-failure message drops the pending target through the existing source-proven result handling; an ambiguous missing prompt stops. Normal result returns to the command boundary without a blind dismissal suffix.

No new policy attributes, tunable thresholds, or changes to `EXPECTED_FIRST` were introduced. Existing `_staged_prompt_chain` is per-decision state, and the new chain uses the existing ownership and settlement mechanism. Only this worktree was written. Recorder directories, other worktrees, game/bot/executable, and the pre-existing untracked `.live8b-revert.py` were untouched.

Fixtures are unchanged recorded JSON boards and the recorded quaff screen, extracted by `tests/extract_live30_identify_normal_fixture.py`; `tests/fixtures/live30-identify-normal/provenance.json` identifies original JSONL line numbers and SHA256 hashes. Intermediate choosers, address changes, and the ordinary success result are explicitly declared derived protocol variants. Address pins stop at the first new target answer; no post-divergence live result was fabricated.

The **single revert check** temporarily restored all three production files to `c3280a6c`, ran only the new pin module and the authorized withdraw/S3.3 baseline fixture in separate processes, then restored the exact edited bytes in `finally`. New pins: **9 tests, 13 subtest failures and 1 error before; 9 tests pass after**. The error is the expected absent staged-chain metadata in the current-board composition pin. See `docs/live30-revert-check.json` for the captured baseline result.

| Required module | Tests | Result |
| --- | ---: | --- |
| `tests.test_live30_identify_normal` | 9 | PASS after single revert |
| `tests.test_live13_full_equipped_identify` | 1 | PASS |
| `tests.test_live15_identify_source` | 2 | PASS |
| `tests.test_live17_identify_observation` | 2 | PASS |
| `tests.test_live18_identify_result` | 2 | PASS |
| `tests.test_input_executor` | 73 | PASS with read-only fixture path repair described below |
| `tests.test_policy_identification` | 45 | PASS |
| `tests.test_test_fakery_lint` | 13 | PASS |

Every module ran in its own normal Python process with `PYTHONPATH=src;tests;scripts`; 147 tests passed. The direct `python -m unittest tests.test_input_executor` first passed 72 tests and errored once because its pre-existing recall-depth pin reads `jsonlog/incident-20260919-2230-recall-depth-prompt.jsonl` relative to the worktree (`tests/test_input_executor.py:1835`). The unchanged file exists in the main checkout's recorder directory. For the complete 73-test rerun, an in-process infrastructure wrapper redirected **only that exact Path.read_text call** to `C:/hengband/bot-client/jsonlog/incident-20260919-2230-recall-depth-prompt.jsonl`, read-only. No fixture was written to jsonlog, no test/assertion or production behavior was replaced. This limitation is explicit rather than silently claiming the direct command passed.

| Authorized fixture | OFF identity | S3.3 ON result |
| --- | --- | --- |
| stuck | 4 rows; `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | No first divergence; gate count 0; no declaration gaps/mismatches |
| withdraw | 34 rows; `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | Existing early divergence at index/sequence 3: OFF `~9\x1b`, `home:request-knowledge-scan`; ON `\x1b`, `equipment-transaction:catalogue-leave-for-scan`; gate count 0; no declaration gaps/mismatches |

Withdraw's frozen `EXPECTED_FIRST` names index/sequence 20, shop travel. The index-3 `early-divergence` is **identical on unmodified c3280a6c**, as proven during the single revert; it is pending for Claude, not a live30 regression. The script returns exit 0 while reporting this defect; that exit is not treated as a clean ON trajectory. `EXPECTED_FIRST` remains unchanged. OFF gate counts: stuck 0, withdraw 20. Existing missing declarations: stuck detectors 1, withdraw detectors 2.

Pending for Claude (DO NOT RUN respected): `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`, `scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`, `tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`, long tour/town/overweight recorded replays, town producer purity parts, full-fixture runs of `scripts/first_divergence_s3_3.py` (only the specifically authorized stuck/withdraw OFF+S3.3 exception ran), and any all-matching-module sweep.

Step 1 commit: `6767cacc` (evidence). Step 2 is the separate implementation/pins/report commit immediately following it on `decl-r3b`.
