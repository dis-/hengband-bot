# Declaration enforcement round 8

This round switches the S3.3 holder path to the claim's execution declaration.
`policy.py` dispatches the bound route, equipment and calibration steps, checks
posted operation identities before waiting, and releases declared no-step work
on the same board. `policy_navigation.py` retries an unposted stair only when
the departure declaration binds the exact stair command, floor and position.
Missing or stale declarations produce a typed no-key stop; `cli.py` stops before
sending a command for that outcome. The old holder inference remains behind the
OFF switch for comparison.

The remaining OFF tour gap reported by `gates-decl7b/tour-off.json` was a
calibration claim retaining an older awaiting declaration at decision 3009.
The equipment town confirmation offer was labelled `equipment-txn`; claim exit
binds offers by final claim owner. It now labels the offer `calibration` when
calibration owns the session. The focused pin fails with that binding reverted.
The long tour replay was not run under the inherited DO NOT RUN rule.

## Changed existing S3.3 ON pins

* `test_final_town_result_cannot_emit_competing_errand`,
  `test_suspended_route_refuses_owner_retired_terminal`,
  `test_suspended_route_replaces_empty_entry_wrapper`, and
  `test_active_route_replaces_empty_entry_wrapper`: their synthetic route
  claims have no execution declaration, so they now expect
  `ownership:declaration-missing:store-router` instead of holder-silent.
* `test_town_holder_resumes_after_survival_before_another_errand`: its
  synthetic Home scan likewise has no declaration, so it expects
  `ownership:declaration-missing:home-scan`.
* `test_downstream_router_result_yields_to_awaiting_knowledge`: the test now
  supplies a posted, identity-bound knowledge declaration before expecting
  the scan observation wait.

No existing pin was removed. New incident pins cover the 11:54 short route,
19:04 next equipment action after Home effect, 21:34 unposted stair, and 23:22
posted calibration takeoff. Missing declaration, unposted wait and named
no-step release are also pinned. Reverting the ON dispatcher failed all seven
dispatcher pins; reverting the stair suppressor and calibration owner binding
failed their respective focused pins.

## Verification

* `tests.test_execution_declaration`: 28 passed.
* `tests.test_declarations_r3b`: 13 passed.
* `tests.test_ownership_s3a_record`: 107 passed.
* `tests.test_test_fakery_lint`: 13 passed.
* `first_divergence_s3_3.py stuck s33` and `withdraw s33`: no first divergence,
  no declaration gap rows. Their OFF hashes matched the frozen values.

The other four OFF hashes and the long ON fixtures were not measured here under
the inherited DO NOT RUN rule. The dispatcher is still incomplete for other
valid S3 holder `next_step` names; these currently stop as stale declarations.
This is a remaining implementation gap before broad S3.3 ON rollout.
