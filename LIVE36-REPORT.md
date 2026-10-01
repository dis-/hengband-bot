# live36 — departure weight recovery

Base `d1bf7c28`; branch `live36`; only this worktree changed.

## Step 1

Frozen evidence: `tests/fixtures/live36-weight.json:1` (verbatim board,
decision records 7514–7520, Home page and serialized shelf memories; source
hashes included). Extraction: `scripts/extract_live36_weight.py:15`.

* Stop 7520: carried pack plus equipment 1780 tenth-pounds, limit 1750;
  STR index 29. Only `inventory_weight_ready` failed. Weight calculation:
  `src/hengbot/policy_home.py:1100`; `policy_helpers.py` sums pack and worn.
* Actual retention, reproduced using the recorded optimization depth 20
  and the sanctioned pending Q2 profile: a oil 5/5, b speed 2/2, c cure 10/10,
  d healing 4/4, e teleport 15/15, f recall 10/10, g light 6/6, h light wand
  1/1 (MANA food), l iron shot 99/99. No surplus in these stacks.
  i Identify staff 1/0, j Identify staff 2/0, k Identify staff 2/0 are outside
  the quantity retention table (`policy_home.py:815`). They are not all safe
  to remove: i's 17 charges are needed; j or k can be removed independently
  while preserving Identify and MANA food. Existing charge-aware selector
  with its count-cap bypass chooses k (2 × weight 50), leaving 27 Identify
  charges, above the unchanged 20-charge requirement. The recorded pack has
  no unidentified loot or unknown items.
* `policy_home.py:1187` rejects required-category items with reservation 0;
  `:1237` applies that filter to all three staff stacks. Thus the overweight
  producer has no candidate. The typed verdict follows that failure, rather
  than preempting an available deposit. Independently, cumulative
  `need_attempts[weight-overload]=5` exceeds its budget 1 and would suppress
  the repaired need at `policy_town.py:3059`. Home had zero unsatisfied passes,
  no blocked store and no approach failures; this is not a failed deposit.
* Last observed Home page: stock 57, capacity 240 (183 free slots), followed
  by the successful withdrawal at 7510. No subsequent deposit could have
  filled it. Home room is not the blocker.

The seam attachment primes the real outside board and supplies captured
depth, shelf/attempt memories, Q2 abandoned force requirements and ledger.
It does not reconstruct the entire prior process. No recorded board after
a changed key is interpreted as its result (R4). No UI classification or
modal continuation changes are proposed, so R2 needs no new screen.

Initial pin run: 3 tests, 1 passed, 2 failed (no deposit; no weight claim).
No existing assertions changed; EXPECTED_FIRST untouched.

## Step 2

`policy_home.py:1148` asks the existing charge-aware surplus selector before
its unquantified-required-category refusal. Only the selector's independently
safe staff stack may bypass that refusal (`:1194`). Its Identify charge
floor, MANA edible-charge requirement and device reserve remain intact
(`policy_supply.py:511-579`). The new `for_weight_overload` argument bypasses
the optional sale count cap and the purchase-sale prohibition: required
excess bought this visit must be depositable too. It never bypasses quantity
retention or the charge/food checks. No new persistent attributes.

`policy_town.py:3068` stops treating successful historical weight operations
as exhaustion of a later overload. Approach failures, unsuccessful Home
passes, the Home executor ceiling, rejected deposits and abandonment still
bound real failures. The normal registry/router therefore finds Home before
the departure-unsatisfiable fallback (`:5764`). General surplus and unknown
items continue through the existing retention-based deposit selector. No
supplies, purchase guards, resistance requirements or speed gates changed.

Printed evidence (`reports/live36-facts.json:1`):
`live=["1","town:blocked:departure-unsatisfiable"]`,
`after=["\u001b`n(.","shop:travel"]`, `selected_store=7`,
`deposit=[["k","鑑定の杖 (2x 4回分)",2]]`, `remaining_weight=1680`,
`remaining_identify_charges=27`, `food_ready=true`, `identify_ready=true`.
This is selection and a calculated inventory, not an observed live deposit.
The attachment omits the live optimizer cache, so it does not claim exact
whole-process reproduction of all departure conjuncts. The route pin uses
the actual recorded surface and real production registry/router and repeats
after the production checkpoint/restore path. It ends at the first changed
key. The generic typed terminal remains when no depositable candidate exists;
the genuine-failure pin retains `overweight-home-unreachable`.

Expanded pins: 7/7 pass. One revert of all runtime hunks: 5 of 7 fail
(`reports/live36-revert.txt`); files restored byte-for-byte, then 7/7 pass.
Frozen JSON has a `-text` attribute to preserve its byte hash on checkout.

| Module / selection | Tests | Result |
| --- | ---: | --- |
| tests.test_live36_weight | 7 | PASS |
| tests.test_departure_unsatisfiable_weight_recorded | 7 | PASS |
| tests.test_policy_home | 184 | PASS, 4 existing skips |
| tests.test_town_progress_invariant | 22 | PASS |
| tests.test_ownership_s2a_classification | 16 | PASS |
| tests.test_test_fakery_lint | 13 | PASS |
| tests.test_overweight_home_unreachable_recorded.HomeSuccessResetsTheVisitBoundTest | 5 | PASS |

Weight-named test modules are exactly `test_live36_weight`,
`test_departure_unsatisfiable_weight_recorded`, and
`test_overweight_home_unreachable_recorded`. The last module's long replay is
pending for Claude under the inherited DO-NOT-RUN block (only stuck/withdraw
were excepted); its five short Home-bound class pins ran separately.
Each module/selection ran in its own process, with `PYTHONPATH=src;tests;scripts`
and the installed Python313 executable, not WindowsApps.

Stuck OFF/S3.3: four rows, no divergence;
`c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`.
Withdraw OFF: 34 rows,
`a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`.
Withdraw S3.3 first difference: `(3,3,ESC,equipment-transaction:catalogue-leave-for-scan)`;
trajectory defect null. Reports: `reports/live36-{stuck,withdraw}-{off,s33}.json`.
EXPECTED_FIRST was never edited.

Pending for Claude (not run): `scripts/test_parallel_runner.py`,
`scripts/test_timing_runner.py`, `scripts/hunk_guard.py`,
`scripts/verify_scope.py`, `scripts/mutation_battery.py`, `tests.test_cli`,
`tests.test_policy_town`, `tests.test_policy_shop`,
`tests.test_absorbing_states`, long tour/town/overweight recorded replays
(including the remainder of `test_overweight_home_unreachable_recorded`),
town-producer purity parts, full-fixture `first_divergence_s3_3.py` runs
outside the explicit stuck/withdraw exception, and any all-matching sweep.

User decision conformance:

* 「まず、重量を原因に要求物資を緩和してはならない」: unchanged required
  stacks a–h/l; food and Identify readiness both true after removing k.
* 「重量超過した場合の対処について。まず要求物資の過剰分を自宅に預け入れる。」:
  Home 7 chosen, k's safe excess is the sole batch.
* 「購入側ではガードしない。必要物資は購入しなければならない。」:
  no purchase chooser changes; recovery happens on the recorded post-purchase
  surface. The surplus selector's purchase-sale restriction is bypassed only
  for depositing charge-safe excess.
* 「本当に預け入れに失敗するならそれは停止するべき事案である。町中で自宅への接近が不可能になるのは正常ではない。」:
  genuine approach failure still arms the named stop; no candidate leaves
  no weight owner, preserving the terminal fallback.

Assertion audit before both commits:
`No changed pre-existing assertions or forbidden test edits.`
`git diff --check` passes. Step 1 commit `e3adcc42`; step 2 is the following
live36 fix commit (SHA supplied in the final report). Existing untracked
live29 files were untouched. Game, bot and other worktrees were untouched.
