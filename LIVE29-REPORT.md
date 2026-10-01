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
`policy_town.py:1343` calls the approach producer as
`town-progress-invariant:approach`, whose writer family is detectors. The new
gate calls `_defer_town_errand` for detectors without checking the shared
`_town_gate_exempt` rule (`policy.py:5910`). It returns None, aborting the
existing progress repair. The final blanket test at `policy.py:3155` calls the
uncomposed entry wait "unbound" (`policy.py:5982`) despite the live posted
entry declaration, and emits the misleading declaration-missing stop. Thus
the route delegate's completion did not erase the parent's declaration.

OFF's reason at 3706 is an existing fixture divergence, explicitly documented
in `tests/test_overweight_home_unreachable_recorded.py:62` and `DIVERGENT`.
`policy_town.py:1378` wraps the progress repair with its proposed/result reasons.
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
