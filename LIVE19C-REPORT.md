# live19c

Worktree: `C:\hengband\bot-client-decl-r3b`, branch `decl-r3b`, starting HEAD `958ef917`.
No existing expectation or EXPECTED_FIRST was edited. The pre-existing untracked
`.live8b-revert.py` was left intact. No other worktree, game, executable, bot
process, or read-only jsonlog was modified.

## Causes and fixes

| Reported item | Cause and final fix (current source lines) |
| --- | --- |
| town_progress_invariant: five NoneType errors | `policy_calibration.py:96` applied calibration ownership even with both switches OFF; `policy.py:5796` consequently deferred purchases. Gate physical ownership with cross-area OR S3.3 at `policy_calibration.py:89`. `_shop` can legitimately return None for an enforced deferred purchase; declare its optional result at `policy_shop.py:3423` and return an explicit no-step composition outcome at `:4989`, retaining the observed page. |
| absorbing_states: NoneType and two changed withdrawal reasons/macros | Unconditional restore reactivation (`policy_calibration.py:885`) and restore priority (`policy_home.py:1416`) took over legacy Home work. Gate both. Source/log inspection only: execution is prohibited by the inherited DO NOT RUN block. |
| device_purchase_preemption_trajectory: NoneType and repetition reason | Same unconditional ownership suppressed an affordable purchase and its invariant counterfactual. The ownership gate and legitimate deferred-composition outcome fix both; existing pins pass. |
| town_restock_trajectory: NoneType | Same OFF purchase suppression returned None from `_shop`; gate calibration ownership. Existing remembered-stock purchase pin passes. |
| latch_onset_capture: old checkpoint macro changed | `policy_home.py:1915` replaced historical full-shelf batch counts with owed quantities unconditionally. Retain legacy counts/slot selection when both switches are OFF; enforce debt quantities and cumulative weight when either switch is ON. |
| policy_calibration: blockers None, p1/p2/p3, blocking_leave, floor-change, same-page macro | Ownership suppression made departure preparation None (`policy.py:5877`). Restore gates at `policy_calibration.py:885,906,1031`; gate Home selection at `policy_home.py:1416`, batch quantities at `:1915`, legacy posting retirement at `:2085`, and unobserved-debt retention at `:2411`. The legacy knowledge request, departure blockers and batch macro pins pass unchanged. |
| calibration_restore_deposits_recorded: exhausted Home reason | `policy_calibration.py:1031` selected the new restore terminal unconditionally. OFF again selects the legacy identity-bearing redress terminal; existing pin passes. |
| calibration_visit_blocked_loop_recorded: blockers None | Unconditional calibration ownership suppressed the departure producer. The ownership gate permits the OFF producer and its calibration-required blocker again. Existing pin passes. |
| policy_home: reactive recorded route became None | Broad OFF absent-target stops affected the historical restore routing drive. Preserve the existing no-step calibration family and confine the OFF exception to debt whose items are already worn, as observed for the live19 missing glove (`policy_home.py:1704`, `policy_calibration.py:1293`). The recorded reactive route pin passes. |

The existing `test_absent_restore_and_overweight_are_typed_with_all_switches_off`
is recorded evidence for the explicit OFF-loop exception in the dispatch. Its
missing glove is already worn on the final recorded board. The OFF terminal
continues to retain that debt; generic OFF restoration retains legacy behavior.
Cross-area/S3.3 ownership, terminal behavior, overweight excess deposits and
restore-stack protection remain active under enforcement.

## Pins and verification

New `test_recorded_restore_switches_preserve_legacy_or_enforced_batch` uses the
frozen live19 boards and real deposit/withdraw producers. The recorded merged
Home shelf holds 57 torches, with a five-torch deposit debt. OFF emits 57; either
switch ON emits five. All three switch configurations are checked before and
after pickle restoration, along with purchase deferral. No new policy attribute
or threshold was introduced. Existing older-checkpoint protection coverage passes.

Single revert check: temporarily made `_calibration_restore_enforced` unconditional.
The new pin failed in both OFF checkpoint cases (5 != 57). Exact source bytes were
restored in finally; the module subsequently passed.

Each module ran in its own Python process with `PYTHONPATH=src;tests;scripts`,
using the installed Python313 executable, not WindowsApps.

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_town_progress_invariant | 22 | PASS |
| tests.test_absorbing_states | ? | NOT RUN: inherited prohibition |
| tests.test_device_purchase_preemption_trajectory | 4 | PASS |
| tests.test_town_restock_trajectory | 21 | PASS |
| tests.test_latch_onset_capture | 7 | PASS |
| tests.test_policy_calibration | 75 | PASS |
| tests.test_calibration_restore_deposits_recorded | 6 | PASS |
| tests.test_calibration_visit_blocked_loop_recorded | 10 | PASS |
| tests.test_calibration_live19 | 10 | PASS |
| tests.test_calibration_crossarea_debt | 5 | PASS |
| tests.test_town_calibration_owner_retired_recorded | 6 | PASS |
| tests.test_home_entry_capture | 8 | PASS |
| tests.test_ownership_claims | 24 | PASS |
| tests.test_live8 | 11 | PASS |
| tests.test_policy_home | 184 | PASS (4 existing skips) |
| tests.test_test_fakery_lint | 13 | PASS |

Earlier intermediate policy_home and live19 failures were diagnosed and corrected;
the table reports final results, not those intermediate attempts.

Authorized fixtures (separate processes):
- stuck OFF: 4 rows, SHA256 `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5`.
- stuck S3.3: no divergence, no trajectory defect.
- withdraw OFF: 34 rows, SHA256 `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9`.
- withdraw S3.3: first divergence index/sequence 20, matching existing EXPECTED_FIRST;
  no trajectory defect. Declaration mismatch counts and gap rows are empty in all four.
  Existing detector declaration omissions and withdraw OFF's 20 gate-final rows remain.

## Commits and decision needed

- `2f60d517`: gate live19 restoration; restore legacy OFF behavior; handle legitimate deferred purchase composition.
- `ca659bc0`: retain recorded OFF loop terminals.
- `b8628c60`: recorded switch/checkpoint macro pin.
- `f87af821`: scope OFF exception to carried debt.
- `a2dc8fd0`: narrow that exception to already-worn equipment and preserve the legacy no-step family.

The dispatch requests `tests.test_absorbing_states` but explicitly inherits a DO NOT
RUN block naming it, with only stuck/withdraw fixtures excepted. Decision needed:
explicitly permit that module, or have Claude run it. Until then, the requested
all-modules-green verification is incomplete; no claim of full completion is made.

{"topic":"live19c","implementer":"gpt-6.1-sol","status":"verification-restricted","modules_passed":15,"tests_run":406,"tests_passed":402,"skipped":4,"not_run":["tests.test_absorbing_states"],"decision_needed":"Explicitly permit tests.test_absorbing_states despite inherited DO NOT RUN, or have Claude execute it.","single_revert":"caught-two-OFF-checkpoint-cases","fixtures":{"stuck_off":"c63d582c","withdraw_off":"a9b34420","stuck_s33":"no-divergence","withdraw_s33":"existing-EXPECTED_FIRST-20"},"commits":["2f60d517","ca659bc0","b8628c60","f87af821","a2dc8fd0"]}
