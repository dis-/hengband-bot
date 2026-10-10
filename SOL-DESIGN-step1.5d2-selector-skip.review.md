# Review: SOL-DESIGN-step1.5d2-selector-skip.md (F2/F3)

Reviewer: Claude (adversarial design review), 2026-10-10. Base checked: worktree
`step1.5d2` = a8833b0b + bd51ff09 (design only). Read-only; no tests run, no game/bot touched.

## Verdict: APPROVE-WITH-CHANGES

The design's code citations are accurate on a8833b0b, every pin row exists with the stated
key/reason/turn, the fixture correction is right, and the owner decisions are quoted without
narrowing. Seven changes are required before implementation is ordered; most concern the
F3(b) yield scope and the F2(c) composition path, which as written can pre-empt the very
buy they protect or create a second mutating producer for one key.

## 1. Citations verified (file:line on a8833b0b)

- `policy_shop.py`: `_next_purchase` 2273, `_next_purchase_unreserved` 2915,
  `_legacy_next_purchase_unreserved` 2948, `_mandatory_purchase` 2858-2913 (no Identify branch:
  true), `_purchase_rungs` 2636, `_matching_live_purchase_rungs` 2748, `_live_purchase_need` 2618,
  churn guard 4823-4831, completed disposal 4273-4285, relief dispatch 4089-4093,
  `_identify_staff_swap_purchase` 3967 (uses the MAX sold charges, 3963-3965: "fuller than every
  sold staff" holds), `_batch_sell_key` ESC 3852-3853, `_atomic_shop_transaction_key` 5601,
  cached refusal 5653-5655, settlement 5763-5843, `_identify_staff_purchase_room` 3387.
- `policy_instore.py`: `_in_store_pure_scope` 169 (restores rebindings by identity only, so a
  nested set mutation would leak: the design's warning is correct), `_in_store_selection` 193,
  disposal 205-207, `_in_store_preconditions` 285 (own-inscription carveout 292-296),
  `_in_store_entry_key` 395, `_in_store_emit` 442, `_in_store_effect_confirmed` 617,
  `_in_store_cached_shop` 664.
- `policy_observation.py`: ledger epoch resets 101/123; `_resolve_observed_uncomposable_stop`
  1162 (design says 1161; harmless).
- `policy_home.py`: `_home_full_sale_candidate` 328, `_home_full_discard_candidate` 418,
  `_home_full_skip_key` 546, `_home_full_relief_key` 589, sale-effect accounting 827-857,
  foreign-store leave 858-862, pending refile 863-909, catalogue selection 919-1059,
  `_home_full_knowledge_key` 1081 (`@claims(HOME_SCAN)` at 1080; `claims` is a marker only,
  claim_register.py:1010, so a `str | None` return is harmless), `_atomic_home_withdraw_dispatch_key` 2573.
- `policy_supply.py`: `_identify_staff_ready` 433, `_carried_identify_staves` 652,
  `_identify_staff_acquisition_worthwhile` 699, `_identify_staff_release_plan` 743,
  `_mana_food_purchase` 911. `policy.py`: `_decide` relief dispatch 10185-10200, IST 10351,
  sale verification 8305-8342. `policy_types.py:410`, `policy_state.py:367`,
  `policy_constants.py:304` (`STORE_STUCK_LIMIT == 8` at 89, `STAFF_IDENTIFY_MAX_COUNT = 4` at 404),
  `cli.py:586`. All as described.
- Captures: all five `.bot-decisions.jsonl.gz` exist in `jsonlog/`; SHA-256 prefixes match the
  design table (224534 9dfea54a…, 040900 8b98eb15…, 014739 da41071a…, 040322 126cfb9e…,
  184438 bcd6f4bb…). Rows 69/70, 88/89, 92/93, 138-144, 4 carry exactly the stated seq/turn/
  key/reason/`composition_refusal` (e.g. 224534 row 70: `7`, `town:entrance-step-off:…`,
  refusal `shop:sell-rebuy-churn-defect`; 040900 row 89: `ESC\`n(.`, refusal
  `equipment:sale-complete`; 014739 row 93: `Cf\ryESCESC`, refusal `home:full-queue-surplus-withdraw`).
- Fixture `identify-staff-stockout-20261007.json.gz`: `board_rows.magic_shop/after_magic` turns are
  15004409/15004415, not s41/s42 (15003859/15003865). The correction is right;
  `test_recorded_worthwhile_magic_offer_keeps_a_live_owner` only uses those boards as supplier evidence.
- No pin is already fixed by F1/F4: F1 touched only the Home gate (`_procurement_class_matches`),
  F4 the fundraising block/rungs; the churn guard, completed disposal, relief exits and cap take
  are untouched. Dropping only the 224534 Home-first sub-pin is correct.

## 2. Required changes

1. **F3(b) yield must cover the whole relief dispatch on an ordinary store page, not only
   the leave sites.** After the one-time accounting (827-857: `sale=None`, `withdrawn=False`,
   `_invalidate_home_observation()`), the *next* decision on the same Magic page runs
   `_home_full_relief_key` from `_decide` 10185-10200 (before IST at 10351) and takes
   `if sale is None: if not self._home_knowledge_current: return _home_full_knowledge_key(snapshot)`
   (919-921, `leave_foreign_store=False`). `_store_page_can_request_knowledge` (1070-1077) is
   true for any fully rendered store page, so this emits `HOME_KNOWLEDGE_MACRO` (`~9\x1b`,
   constants 110) or the `home:scan-await-observation` WAIT on the shop page and pre-empts the buy.
   Required: a single guard at relief-dispatch entry (both 10185 and 4089 call sites), evaluated
   after the accounting: ordinary store page + live IST entry ledger for this visit +
   `_departure_blocking_page_operation` non-empty -> return None, covering leave keys, the
   knowledge macro, WAITs and catalogue selection. Make the 040900 S11 pin a two-decision pin
   (buy on S11, and the following constructed same-page decision must not emit `~9`).
2. **F2(c) must not compose after an `inner` that already mutated owner state.** In
   `_atomic_shop_transaction_key` the refusal `inner` comes from `_shop` (5655) and, for the relief
   leaves the design lists as recoverable (`home:full-leave-with-surplus`,
   `home:full-queue-surplus-withdraw`), `_shop` has already filed a Home errand and pending item
   (1048-1057) with its own execution offer. Running `_shop_purchase_key` on top makes two
   producers mutate for one key, which the design itself forbids. Required: enumerate the
   recoverable `inner` reasons explicitly; after F2(a)/F2(b)/F3(b) live inside `_shop`, the churn,
   completed-disposal and relief cases all return the buy from `_shop` directly (so the cached
   refusal at 5653 never carries them), and F2(c) reduces to "no settlement
   (`_resolve_observed_uncomposable_stop`, `nonhome_attempted_without_effect`, plan advance) while
   `_departure_blocking_page_purchase` is non-empty; emit `town:blocked:shop-required-operation-uncomposable`".
   If the designer keeps a composition path, name one concrete boundary where `_shop` cannot
   return the buy but the fallback lawfully can.
3. **F2(a) reset sites are misstated.** The churn authority `_town_visit_sale_signatures` /
   `_town_visit_sale_identify_charges` is cleared at `policy_observation.py:768-771` under
   `snapshot.floor_key != self._floor_key` (752), not at the `TownVisitLedger` replacements 101/123.
   Required: give `purchase_churn_exclusions` the same lifetime as the sale signatures (clear at
   770 too, or store the exclusions beside them), and state plainly that neither survives an
   autorecover restart (`scripts/bot_autorecover.py` only `resume`s a fresh process; no checkpoint):
   the per-visit bound is per process, exactly as today's churn guard. The design's "honor restored
   exclusions" applies only to replay/test checkpoints.
4. **F2(b) completed-disposal predicate is too loose.** `_pending_disposal(snapshot) is None`
   (policy.py 14816-14838) is also true for a Home-sourced dominated-armour disposal that has not
   been withdrawn yet (policy_home.py 4237-4241 sets `_pending_disposal_item` to a Home shelf
   signature and `_home_pending_item`). Required: "completed" = target absent from pack AND
   `_home_pending_item != _pending_disposal_item` AND `_home_atomic_withdraw_pending is None`;
   otherwise the clear-once-then-buy retires a live Home disposal. Seed the 040900 s42 pin through
   `_begin_pack_dominated_launcher_disposal` (14794-14812) as the design says, with the sold item's
   slot/signature, plus a control where the Home-sourced disposal is still pending and must not clear.
5. **New final reason: fix the ownership statement.** `town:blocked` is already a registered
   prefix of the town-plan family (`town_arbiter.py:151`, `claim_goal_typing.py:447`), like
   `town:blocked:overweight-surplus-rebuy-loop`. Required: say the new reason stays under that prefix
   (no new arbitration prefix, so the `tests/test_ownership_s2a_classification.py` digest must NOT
   change) and is published through the existing `_town_blocked_key` path; add it to
   `POLICY_FINAL_STOP_REASONS` (304) and the `messages` table in `_policy_final_stop_banner`
   (cli.py 597+). Drop the "shop-buy family" wording, or if a shop-buy prefix is intended, require
   the digest regeneration explicitly.
6. **Existing-test list is incomplete for the ledger field.** Add
   `tests/test_town_progress_invariant.py:51` and `tests/test_town_restock_trajectory.py:252`, which
   seed `_town_visit_sale_signatures` directly on restored/private-seam policies; a new
   `TownVisitLedger` field needs the `normalize_policy_state` default (367-370) and these tests'
   shims updated (LANDMINE: new policy attribute breaks restored checkpoints). The extra hits for
   `observed-operation-uncomposable` (`test_alchemist_observed_shop_alternation`,
   `test_oneshot_preempt_recorded`, `test_policy_town:1361`) and `_pending_disposal_item`
   (`test_home_full_relief_recorded:258`, `test_home_equipment_disposal`, `test_destroy_procurement_guard`)
   are Home-side and should not flip; list them as "checked, unchanged".
7. **014739 and 184438 pins need declared boundaries.** 014739: "once pending old input is
   genuinely reconciled" must name the row (or declare the constructed board with
   `_store_visit.operation_posted=False`) on which `5`/`shop:one-shot-buy` is asserted; otherwise the
   pin asserts nothing new. 184438: the Home catalogue, `_home_full_relief` dict (`mode`, `stock_count`,
   `deposits`) and `_home_knowledge_current=True` are wholly constructed (no Home page, no s11 state
   row); say so in the test name/docstring and keep the three+one cap-filling control as the
   primary F3(c) pin.

## 3. Checks that passed (brief)

- Owner decisions: no narrowing found. 20-charge/10F readiness untouched (433); cap four kept by
  `_identify_staff_purchase_room` and F3(c) `>=` rule; carried-only (Home used only in gates);
  BM reserve preserved (optional rungs are not `departure_blocking`, `_black_market_optional_purchase`
  2563-2590 keeps `_full_departure_resupply_reserve`); sale-no-preempt respected (F2(b) never
  discards a posted sale); equal rank kept (continuation at the release boundary, no new owner).
- Re-loop: F2(a) class latch per `(store,tval,sval)` bounds a visit to at most page-item count
  exclusions; sell->rebuy across *visits* remains possible only with a dungeon trip between
  (`_find_device_sale` sells any non-useful device, `tail:mana-food` 2722 wants any device) and is
  bounded by real progress, not a town loop; record it as a follow-up, not as solved. F3(b) cannot
  starve relief: the hold needs a lawful operation, each operation is bounded by
  `ops < STORE_STUCK_LIMIT` per `opened_sequence`, and a no-effect operation ends the entry
  visibly. F3(c) skip keyed on `(signature, Home count)` plus the capacity fingerprint cannot be
  reset by a Home<->Magic pair.
- Split and order: F2 first, F3 on F2's HEAD, shared `_departure_blocking_page_purchase`: sensible.
  Recommendation (not required): thread exclusions only through `_legacy_next_purchase_unreserved`,
  `_mandatory_purchase`, `_mana_food_purchase` and the two Identify rungs (3140-3150, 3326-3345),
  and for the remaining `*_purchase` helpers re-run the ladder with the rejected head's class
  added (bounded by page items) instead of changing eight signatures.

## 4. Open question for the owner (one)

- F3(c) forbids relief from taking an empty Identify staff that would bring carried staves to 4
  while identify is not ready, and the design correctly notes Hengband cannot sell or destroy a Home
  shelf item without taking it. With three carried staves and a Home full of 0-charge staves, Home
  therefore stays full until identify is ready (the 10-04 "sell, else destroy cheapest unneeded"
  ladder cannot reach those staves). Once F3(a) works, taking ONE empty staff to the cap and
  swapping it at Magic (release plan sells the emptiest when a strictly fuller affordable shelf
  staff is observed) would both relieve Home and progress identify. Should relief be allowed to take
  one cap-filling empty staff when a strictly fuller affordable shelf staff is already observed
  this visit, or must Home stay full until identify is ready? (Everything else in F3(c) follows
  from the task text as written.)
