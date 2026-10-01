# live32 — step 1 investigation

Base: `92b455ad`; worktree: `bot-client-decl-r3b`, branch `decl-r3b`.
Frozen evidence: `tests/fixtures/live32-shop-leave/provenance.json` (source and fixture hashes).

* At 4216 the outside route producer `_shopping_approach_key`
  (`src/hengbot/policy_shop.py:4797-4907`) probes the captured shelf via
  `_atomic_shop_transaction_key`. Its `_shop` call sets `shop:leave`
  (`policy_shop.py:4997`, `:4370`); composition returns None at `:5157`
  without restoring the caller's reason. The fallback emits direction `1`
  with a store-router Reach/route offer, but reason attribution selects
  shop-sell. `_claim_goal` falls through the `shop:leave` Observe typing
  (`claim_goal_typing.py:210`, `policy.py:4127`) and opens an unbound,
  generic store-operation Observe. The offer does not match shop-sell;
  execution is absent. Recorded claim 3266 confirms both facts.
* At 4217 the town-plan result `town:blocked:equipment-calibration-required`
  escaped the final gate against that phantom holder. The final deferred row
  names that exact pre-stop reason. `_enforce_town_claim_result`
  (`policy.py:7052-7054`) produces `ownership:gate-missing:town-plan`.
  `_refuse_no_progress_cycle` is the last decorated call, not evidence that
  it detected a cycle: its only refusal result is `livelock:exhausted`
  (`policy_helpers.py:153`), which is absent. It saw the outside board at
  (46,83), turn 1140181, same pack/equipment as the leave seam. The unchanged
  equipment-calibration terminal reached the gate. The detector decoration
  explains the rung and detectors owner on the stop row.
* `_next_required_store_type` recomputes live needs and drops stores with an
  observed no-effect pass (`policy_shop.py:1052-1068`), then rebuilds the
  ordering projection (`:1086`). The recorded categories drop quest-speed /
  black-market at 6 and launcher-enchant at 4, leaving equipment-catalog /
  equipment-work at Home. `_build_town_errand_plan` records the changed next
  stop (`policy_town.py:3513`). This is not permission to abandon an actual
  route: the adopted 2026-09-27 user decision requires walking to arrival.
  A phantom sale must never become its holder; the real route remains held
  until arrival. Rebuilding the future-stop projection alone needs no stop
  or fabricated operation completion.
* OFF `_s33_shadow_verdict` on this same recorded gate seam predicts
  `ownership:gate-missing:town-plan` (`policy.py:6850-6853`), agreeing with
  ON `_enforce_town_claim_result`. It is pure (pickle identity checked).
  Thus this evidence does not demonstrate a shadow-verdict defect; absence
  of this report in the earlier shadow session does not establish that the
  same sequence occurred there.

Step 1 pin: historical gate verdict agrees; production route-ownership pin
fails before the fix (`shop-sell` instead of `store-router`). No EXPECTED_FIRST
change and no live runtime changes.
