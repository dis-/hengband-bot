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

Revision comparison and the decision on the contradictory count requirement
are pending. Do not treat the reproduced failures as resolved.
