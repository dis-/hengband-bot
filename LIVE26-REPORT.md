# live26: Home catalogue replay investigation

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
