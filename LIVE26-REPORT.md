# live26: Home catalogue replay investigation

**RULING applied after a4a33abc:** the earlier decision-boundary report below
is historical. See Step 4 for the authorized implementation and new validation.

Worktree: `C:/hengband/bot-client-live21`, branch `live24`, initial
HEAD `2b573a70`. Other worktrees and the live runtime are untouched.

## Step 1: reproduce and preserve recorded evidence

The authorized `tests.test_unaffordable_claim_tour_recorded` module ran in
one Python 3.13 process with `PYTHONPATH=src;tests;scripts`: 7 tests,
679.248 seconds, 2 failures, exactly those reported in the dispatch:
next-row Reach completions 1346 versus 1347, and a new S3 owner change at
decision 2658 from equipment-txn to home-scan.

The preserved new-code ledger shows decision 2657 (list index 2659) opening
claim 2302 under equipment-txn, work `equipment:acquire-home-catalog`, goal
Observe(knowledge). Decision 2658 (list index 2660) selects
`~9 ESC / home:request-knowledge-scan`, creates home-scan claim 2303, and
records the owner change. The next recorded knowledge response completes
claim 2303 at decision 2659.

The fixture's board at list index 2660 contains only 52 of 116 Home items.
That page cannot confirm the complete-catalogue effect. Completing the
equipment catalogue claim merely on entry would contradict live23.

Evidence: `validation/live26/head-summary.json`, `head-tour.log`, and
`recorded-context.json`. `tour_probe.py` compares historical source revisions
against the unchanged authorized tour replay, extracting only `src/` into
a temporary directory under this worktree. Its prefix option stops before
list index 2661, immediately after the disputed decision. No pins,
expectations, or production files have been changed at this step.

## Step 2: revision bisection and the required decision

Each comparison uses the same unchanged tour module, one process per
revision, stopped before list index 2661. The prefix covers 2661 decisions
including the owner change; it is not presented as a full historical run.

| Source revision | Next-row Reach completions in prefix | S3 violations in prefix |
| --- | ---: | --- |
| `f424d3b4` (immediate parent of live23 code fix) | 830 | none |
| `70b9772b` (main, includes live23) | 829 | decision 2658, equipment-txn -> home-scan |
| `2b573a70` (initial HEAD, full module) | 1346 in full run | same 2658 plus the four unchanged later violations |

The dispatch supplies the previously passing `2fe5a02e` full-module result;
that revision was not rerun. The measured good/bad boundary is
`f424d3b4` -> **`ddebaf64`**, whose subject is
`fix(live23): keep registered Home catalogue work through acquisition`.
`git diff ddebaf64..70b9772b -- src` is empty, so the measured main source
is exactly the first bad source. Live24's subsequent policy changes affect
bounty routing, not the catalogue declaration or continuation.

Cause at current file/line:

- `src/hengbot/policy.py:3903`: `_claim_goal` unconditionally turns the
  catalogue execution offer into Observe(knowledge).
- `src/hengbot/policy.py:6723` and `:8761`: physical catalogue continuation
  requires cross-area or S3.3 enforcement. Both are OFF in the tour replay,
  so the old home-scan producer can still take the turn. The newly open
  equipment-txn Observe makes that handoff a real recorded violation.

The prefix's completion-set difference is **exactly**
`(2657, equipment-transaction:travel-home)` removed, with no additions.
Before live23, claim 2302 was Reach(45,123) and completed `reached` at 2658,
even though its execution declaration expected `home-catalog-available`.
After live23, it is Observe(knowledge), and the 52-of-116-item page cannot
complete it. The full new-code ledger has only this one equipment catalogue
acquisition declaration. Thus the 1347 -> 1346 loss is the intended live23
correction of a premature completion, not a missed confirmed effect.

The dispatch explicitly says:
> Change an expectation only if the recorded evidence shows the new behaviour
> is the intended live23 behaviour - then stop and state the decision needed.

**Decision needed:** accept next-row Reach completion count **1346** for
live23's intended Observe semantics, instead of requiring 1347. Correcting
the OFF catalogue handoff must then retain the registered equipment work
until actual catalogue evidence; its completion should be assessed as Observe,
not fabricated as a Reach completion. The 2658 handoff is still a defect;
accepting the count does not excuse it.

No production fix or expectation change was applied. Restoring 1347 by
reverting that row to Reach, completing on a partial page, or adding an
unrelated completion would violate the recorded evidence and the dispatch.
`EXPECTED_FIRST` and every existing assertion remain unchanged. The task
stops at its explicit decision boundary; both original tour failures remain.

Bisect evidence is in `validation/live26/bisect-result.json`,
`pre-live23-prefix.json`, and `main-prefix.json`, with direct-process logs.
Historical source extractions were automatically removed after each process.

## Step 3: authorized verification and final status

All seven requested modules ran separately, using the normal installed
Python 3.13 executable, never the WindowsApps stub. No prohibited runner,
gate, long replay other than the authorized tour, or producer-purity sweep
was executed. No new attributes or tests were introduced.

| Module | Tests | Result |
| --- | ---: | --- |
| `tests.test_unaffordable_claim_tour_recorded` | 7 | 2 original failures reproduced |
| `tests.test_live23_home_cycle` | 6 | pass |
| `tests.test_live22_bounty` | 12 | pass |
| `tests.test_policy_home` | 184 | pass, 4 existing skips |
| `tests.test_town_progress_invariant` | 22 | pass |
| `tests.test_ownership_s2a_classification` | 16 | pass |
| `tests.test_test_fakery_lint` | 13 | pass |

Total: 260 tests run, 254 passed, 4 skipped, 2 unresolved failures.
Logs and `validation/live26/test-results.json` preserve the results. Log
encoding and line endings are normalized for review; assertion text and
measurements are unchanged.

Authorized fixture measurements were run in OFF and S3.3 modes, one fixture
and mode per process:

| Fixture | OFF rows | OFF SHA256 | S3.3 first difference |
| --- | ---: | --- | --- |
| stuck | 4 | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | none |
| withdraw | 34 | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | index/sequence 3: `~9 ESC / home:request-knowledge-scan` -> `ESC / equipment-transaction:catalogue-leave-for-scan` |

The withdraw difference matches the previously disclosed live23 partial-page
correction: 52 of 131 items were visible. Measurement stops at the first
changed key; no later board is treated as its confirmed effect. The script
still labels it `early-divergence` against unchanged `EXPECTED_FIRST` row 20.
Neither this discrepancy nor the tour failures are reported as passing gates.

Commits: reproduction `66602343`; bisect and decision evidence `0189decc`;
the final reporting commit contains this verification and `LIVE26-EVENT.json`.
There is **no fix commit**, because the dispatch's evidence-based stop
condition was met. Only reporting and bounded diagnostic artifacts changed.


## Step 4: apply Claude's 2026-10-01 09:10 RULING

Continued from `a4a33abc` in this worktree only. The accepted next-row Reach
completion count is now **1346**, with the requested `ddebaf64` and ruling
comment. No `EXPECTED_FIRST` entry or other numeric expectation was changed.

The bisect boundary remains `f424d3b4` -> `ddebaf64`. The unconditional
catalogue Observe declaration was correct; the legacy scan producers still
opened a separate home-scan work even when the equipment catalogue work was
registered. The physical continuation was gated on the cross-area/S3.3
switches, while the new Observe was unconditional.

Final code: `src/hengbot/policy.py:6731` centralizes the two knowledge-request
execution offers. When the scan serves registered equipment catalogue work,
it declares that holder's producer, work id, expected effect and continuation,
instead of opening unrelated home-scan work. At `:3208` the census family reads
that explicit, key-specific catalogue offer. `_claim_goal` consequently
continues the holder's original Observe(knowledge), and catalogue adoption
closes it through the existing observed-effect path. An ordinary scan without
registered catalogue work keeps its ordinary home-scan declaration. Both
legacy scan sites use the helper. This preserves OFF keys/reasons and does
not change ON physical Home continuation.

No new attribute, threshold, fabricated completion or unnamed release was
added. The new recorded pin replays exactly the withdraw capture's unchanged entry/scan actions
and their recorded knowledge response with both switches OFF, directly and after checkpoint
restoration. It checks the same equipment-txn claim id and acquisition work
on the scan row. A single revert check extracts pre-fix `a4a33abc` src under
this worktree and runs that pin: it fails because the original scan changes
owner to home-scan. No production source is temporarily reverted.

Commits: `6d3f268b` applied 1346 and an initial physical-continuation fix;
`80439cd5` added partial-page and diagnostic coverage; **`8c7bbd71`** replaces
the initial OFF physical change with registered scan continuation and adds
the recorded/restored OFF pin; `eca564eb` extends it through the real scan
response and confirms completion. The final diff against `a4a33abc`, rather than
the intermediate approach, defines the implementation.

The initial physical attempt broke withdraw OFF identity and introduced tour
violations downstream of a changed exit key. Its logs are preserved under
`ruling-*`; it is superseded by `final-*` logs and `ruling-tour-final.log`.
Those failed measurements are not final passing evidence.

Final fixture verification (one fixture/mode per process):

- stuck OFF: 4 rows, unchanged
  `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`;
  S3.3 has no first difference and no holder-silent stop.
- withdraw OFF: 34 rows, unchanged
  `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`.
- withdraw S3.3: the **pre-existing** live23 first difference remains historical
  sequence/list index 3: `~9 ESC / home:request-knowledge-scan` becomes
  `ESC / equipment-transaction:catalogue-leave-for-scan` because the visible
  page contains 52/131 items. It retains equipment-txn claim 3. The measurement
  stops there; no later board is claimed as the effect of the changed action.
  Against unchanged `EXPECTED_FIRST` row 20, this is still `early-divergence`,
  not a passing expected-row gate. Live26 does not change that ON behavior.

Final requested module results (one module per process):

| Module | Tests | Result |
| --- | ---: | --- |
| test_unaffordable_claim_tour_recorded | 7 | 1 aggregate expectation failure |
| test_live23_home_cycle | 7 | pass |
| test_live22_bounty | 12 | pass |
| test_policy_home | 184 | pass, 4 existing skips |
| test_town_progress_invariant | 22 | pass |
| test_ownership_s2a_classification | 16 | pass |
| test_test_fakery_lint | 13 | pass |

Total: 261 tests, 256 passed, 4 skipped, 1 failure. The final tour process
ran 544.731 seconds, 4,267 claim rows. Its unchanged remaining-violations pin
passes exactly: (2701, owner-change, store-router, home-scan),
(3035, retarget, calibration, calibration),
(3037, transaction-contention, calibration, equipment-txn),
(3052, owner-change, store-router, home-scan). The 2658 violation is gone.
The accepted 1346 pin and all Observe completion-label counts pass.

Recorded evidence: at decision 2657 claim 2302 opens as equipment-txn
Observe(knowledge), work equipment:acquire-home-catalog. Decision 2658 posts
the unchanged scan key/reason under that same claim 2302, with no violation.
At 2659 the real knowledge response closes claim 2302 **complete**, reason
home-knowledge-current, execution evidence home-knowledge-current. Thus the
catalogue is actually adopted before the Home-visit owner can take the turn.

**Remaining decision:** accept `S2A1_ENDINGS["equipment-txn/Observe"]["complete"]`
**7 instead of 6**. The additional completion is exactly the now-correct
catalogue adoption described above; equipment abandoned falls from 1 to 0
and satisfies its unchanged 0 pin. The RULING explicitly authorized 1346,
but did not name this additional aggregate change. The dispatch says:
> Change an expectation only if the recorded evidence shows the new behaviour
> is the intended live23 behaviour - then stop and state the decision needed.

Accordingly, the complete=6 expectation remains unchanged, its one failure is
disclosed, and implementation stops at that decision boundary. No fabricated
completion or unrelated change is used to keep the old aggregate. The withdraw
ON row-3 early-divergence is also disclosed as pre-existing, with EXPECTED_FIRST
unchanged. This is not an all-green gate report.

Evidence: `validation/live26/ruling-tour-summary.json`, `ruling-tour-final.log`,
`final-test-results.json`, `final-*.log`. All modules used normal Python 3.13
with PYTHONPATH=src;tests;scripts. No prohibited runner or test module, other
worktree, game executable, jsonlog write, or live-runtime change was used.
