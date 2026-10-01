# live29: posted router entry declaration

Worktree: `C:\hengband\bot-client-live21`, branch `live29`.
Starting head: `08fef4dc`; requested comparison endpoint: `2fe5a02e`.

## Step 1: evidence

HEAD's `tests.test_declarations_r14` fails at first difference index 3707,
historical sequence 3706, instead of the frozen index 3715 / sequence 3714.

The parent is store-router Observe(store-entry, store 4), with an ENTERING
visit and no posted purchase. It must hold the entry observation, independently
of any route child's completion. Contrary to the initial hypothesis, its entry
declaration IS present: work `store-entry:4:37,91`, awaiting operation
`decision:3705:5`, effect `store-page-open`, continuation `store.entry.observe`.
The pre-3706 checkpoint contains this declaration after entry confirmation in
both OFF and ON; the pure final validator (`policy.py:6957`) accepts it.

The regression is the new gate at `policy_shop.py:4785` in live23 `ddebaf64`.
`policy_town.py:1043` calls the approach producer as
`town-progress-invariant:approach`, whose writer family is detectors. The new
gate calls `_defer_town_errand` for detectors without checking the shared
`_town_gate_exempt` rule (`policy.py:5902`). It returns None, aborting the
existing progress repair. The final blanket test at `policy.py:3155` calls the
uncomposed entry wait "unbound" (`policy.py:5975`) despite the live posted
entry declaration, and emits the misleading declaration-missing stop. Thus
the route delegate's completion did not erase the parent's declaration.

OFF's reason at 3706 is an existing fixture divergence, explicitly documented
in `tests/test_overweight_home_unreachable_recorded.py:62` and `DIVERGENT`.
`policy_town.py:1379` wraps the progress repair with its proposed/result reasons.
It is included in the frozen OFF hash, so restoring the historical reason would
violate the requested hash. This task retains the existing OFF behavior.

Bisect:

* Full authorized r14 module: `2fe5a02e` passes; `08fef4dc`, `8c7bbd71`,
  and `028434cc` fail at 3707/3706.
* A checkpoint captured without changing decisions during the `028434cc`
  r14 run isolates entry confirmation plus the 3706 board. Git bisect then
  executes that short boundary: `6a9dcdcb` produces the correct `2` and
  invariant reason; `ddebaf64` stops declaration-missing. First bad:
  `ddebaf64ae89b4825d6ce9435890039dc1df5255`.
* The short boundary is a diagnostic attachment, not a claim that subsequent
  historical boards follow a changed key. Full r14 and the authorized gates
  remain required after the fix. See `reports/live29-bisect.txt`.

No code, assertion, or frozen expectation was changed in step 1.

## Step 2: fix and pin

`policy_shop.py:4787` now applies `_town_gate_exempt` before its errand gate,
matching the other town producer entry gates. Detectors/bookkeeping/survival
stay outside the town-holder judgement, as ruling #5 requires. Ordinary
errands remain gated. The parent's already-declared posted entry observation
is preserved; no replacement declaration is invented from the route child.
No persistent attribute, threshold or EXPECTED_FIRST entry was added/changed.

The new short pin in `tests.test_declarations_r14` loads an immutable compressed
checkpoint of the actual pre-confirmation 3705 boundary and the 3706 board.
It proves the parent's own awaiting declaration, OFF/ON result `2` with the
existing invariant reason, post-confirmation checkpoint restoration, and zero
ON final gate escape. Provenance is committed beside the fixture. The original
full r14 first-divergence pin is unchanged.

The single revert (`scripts/live29_revert_check.py`) restores only the old
shopping-approach gate, runs that short pin once, and restores source in finally.
Both ON subcases fail with `None != '2'`; OFF subcases pass.
See `reports/live29-revert.txt`. The fixed short pin passes all four subcases.

## Verification and scope

One module per process, codex runtime Python, PYTHONPATH=src;tests;scripts.
No assertions were loosened, deleted, or repinned.

| Requested module | Tests | Result |
| --- | ---: | --- |
| tests.test_declarations_r14 | 2 | pass |
| tests.test_live23_home_cycle | 7 | pass |
| tests.test_live22_bounty | 12 | pass |
| tests.test_town_progress_invariant | 22 | pass |
| tests.test_policy_home | 184 | pass, 4 existing skips |
| tests.test_ownership_s2a_classification | 16 | pass |
| tests.test_test_fakery_lint | 13 | pass |

Total: 256 run, 252 passed, 4 skipped, zero failures/errors. Full r14 verifies
the frozen 3715/3714 divergence, OFF `rjp` / identify:device, ON `ESC` /
home:leave-after-one-operation, and the operation-bound Home tail. Raw module
outputs are `reports/live29-test_*.txt`. `git diff --check` also passes.

Each authorized fixture/mode ran in its own CLI process:

| Fixture | OFF rows / frozen SHA256 | S3.3 first divergence | Verdict |
| --- | --- | --- | --- |
| overweight | 3782 / 8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b | index 3715, sequence 3714: ESC / home:leave-after-one-operation | frozen row restored |
| stuck | 4 / c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none | pass |
| withdraw | 34 / a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | index/sequence 3: ESC / equipment-transaction:catalogue-leave-for-scan | inherited early-divergence |

All three OFF hashes match in both modes. ON declaration gaps, declaration
mismatches and final gate escapes are zero in all measured prefixes.
Overweight ON measured 3716 decisions, then intentionally stopped at the
frozen first divergence. Its trajectory_defect is null. No post-divergence
historical board is claimed as an effect of the changed action.
Raw gate measurements are `reports/live29-{overweight,stuck,withdraw}-{off,s33}.json`.

Pending for Claude under the inherited DO-NOT-RUN block:

* `tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`,
  `tests.test_absorbing_states`, and town producer purity parts.
* `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`,
  `scripts/hunk_guard.py`, `scripts/verify_scope.py`,
  `scripts/mutation_battery.py`.
* Long tour/town replays, all other full first-divergence fixture runs,
  any full-suite or all-matching-module sweep. Only the explicitly authorized
  overweight/stuck/withdraw modes and r14 module were run here.

The withdraw ON row-3 difference is inherited from `ddebaf64`, documented in
`LIVE23-REPORT.md` and `LIVE26-REPORT.md`, and matches the committed
`validation/live26/withdraw-s33.json`: OFF `~9 ESC` / request-knowledge-scan
becomes ON `ESC` / equipment-transaction:catalogue-leave-for-scan. Its partial
page contains 52/131 items. This remains `early-divergence` against frozen row
20, not a passing gate. EXPECTED_FIRST is unchanged. Catalogue reconciliation
is outside this detector-entry fix and remains pending for Claude.

Temporary baseline source, diagnostic checkpoint JSON and capture scripts were
excluded from commits. Their cleanup was rejected twice by the execution
policy ("blocked by policy"), including with verified explicit workspace paths;
they remain untracked. No other worktree, game, running bot, or jsonlog was
modified.

Commits: step-1 diagnosis `8c2c1da0`; code, recorded pin and single-revert proof
`b4b60bf0`; the final reporting commit contains the module/gate artifacts and
`LIVE29-EVENT.json`. The three commits are on branch `live29`.
