# Review: SOL-DESIGN-town-progress.md (branch town-progress-design-1006, base 4d864cb3)

Reviewer: Claude (Fable 5.1), 2026-10-06. Read-only; claims checked against `src/hengbot` and
the two capture logs (sampled with targeted reads, SHA-256 not recomputed).

## Verdict: **approve with changes** (must-fix items below before dispatching slice 0/1)

The analysis of why the existing watchers missed (a) and (b) is accurate at this base:
`_command_state_signature` includes `turn` (cli.py:633-651), `_cell_loop_guard_applies` returns
False for `in_town` (cli.py:494-505), blocked fuse = 30 (cli.py:395) with streak reset on any
fingerprint change (cli.py:570-585), residence stop = 1500 (cli.py:400), detectors get a fresh
2-decision claim per rewrite (claim_id 550, 554, ... in capture (b), `budget: 2`), and the
log-only path both calls `forgive_retirement` (cli.py:453-454, town_arbiter.py:360-379) and
carries a wall-clock 3-in-600s exception (cli.py:411-427). The work-kind table is the right
shape (observed effect per kind, finite obligations, tombstone per visit). The design is
honest that the call-site reconciliation is not certified.

Verified against capture (a) (rows 8479-8518): rows 8480/8484/8488 show three retirements
within ~8 s, row 8490 is a restart marker, i.e. the **wall-clock guard already stopped the
bot once** that night. In the final restart (8507-8518) the arbiter marks `retired: true`
from row 8509 while the policy keeps emitting `town:blocked:home-full-no-sellable-surplus`
with key `5`; the owner silently changes town-plan -> town-errand at 8510. So retirement
is recorded without ever relabeling to `owner-retired` -- the log-only hook at cli.py:4377
never fired. The design's statement at lines 273-274 is correct.

Verified against capture (b): row 876 `shop_selector.wanted_purchase` = identify-staff
(2x12, 734G), `composition_refusal: shop:sell-rebuy-churn-defect` at 880, cross-town claim
545 `Reach (37,119) distance 13`, and the detector rewrite at 881 carries
`execution.work_id: route:store:38,106` (`route.resume` back to store 5). This is the
substitution path at policy_town.py:1540-1575 (`_town_procurement_progress_key` wins
because `_town_result_makes_progress` accepts any store route, policy_town.py:848-905).

## Must-fix

1. **Tombstone must gate the selectors and the detector rewrite, not only admission.**
   (b) closes only if `_town_procurement_progress_key` (policy_town.py:1094),
   `_next_purchase_unreserved` (policy_shop.py:2607), `_town_observed_purchase_is_composable`
   (policy_town.py:1187) and the rewrite at policy_town.py:1540-1575 all treat a tombstoned
   `(store, target_identity)` as non-existent for the rest of the visit. The text says
   "freeze target selection during the leg" and "the procurement rewrite must not substitute
   a return to store 5" (lines 106-107, 244-245), but it does not name the mechanism. State:
   tombstones are an input of every selector listed after the table, and a rewrite whose
   substituted work targets a tombstone is refused and the original proposal stands.
   Otherwise the single seam closes the buy and the detector reopens it under a new claim ID.

2. **Live effect arrives too late (slice 7).** Lines 337 and 74-93: the generic watcher is
   activated only after all seven slices (~640k tokens). Until then (a)-class loops stop only
   via the 30-decision fuse and (b)-class loops never stop. Activate the bounded rule **per
   completed table row**: when a row's producers are all mapped (manifest gate) and its
   observer landed, that row's work is admitted/closed under the new rule; unmapped rows stay
   under the old watchers. This is not scene-by-scene (the entrance is still single and the
   rule generic); it is row-by-row activation. Reorder so the (b) closers (churn refusal ->
   immediate impossible closure, selector tombstone, route high-water) are in slice 2 and go
   live, and the (a) closers (relief no-candidate proof) in slice 3 or 4. Name, per slice,
   which live behaviour changes.

3. **Remove the wall-clock exception in slice 1, not slice 7.** cli.py:411-427 is a time guard
   (`time.monotonic`, 600 s) and the design itself says it conflicts with the decision
   (line 276-277), yet lines 304-306 keep it until graduation. Delete the window in slice 1
   and replace with nothing (log-only means record only; the fuse/cycle watchers still stop
   real repetition). If a count-based burst stop is wanted (e.g. 3 retirements in one town
   visit with no admitted work between), that is a user decision -- see open question 1.

4. **Slice 0 certification must include a runtime fail-closed check, not only the static
   census.** `producer_census` (scripts/town_structure_lint.py:84-) follows imports from
   policy.py; it cannot see keys written by the driver (cli.py:4381-4385 overrides `key` to
   `LEAVE_STORE_KEY`; prompt clears; executor-released one-shot tails where the policy returns
   `""`, policy.py:10262-10265). Certify closure by: (i) generated manifest with zero unmapped
   candidates (static), and (ii) a shadow receipt at the single emit seam
   (`_offer_execution*`, policy.py:3371-3435, plus the driver send) that records
   `work-contract:unmapped-producer` for any key sent while `in_town or store is not None`
   without a work record; the recorded corpus and the two captures must replay with zero such
   receipts before slice 2 goes live. Static coverage alone cannot prove the 10-04 decision.

5. **(a) counterfactual must decide the outcome from the capture and encode the 10-04 home-full
   decision.** User 10-04: home full -> sell surplus -> if nothing sellable, destroy the
   cheapest unneeded item. Rows 8495-8505 show that ladder was tried (`atomic-withdraw:
   full-home-discard`, `full-skip:identified-item-protected`, `identify:normal`,
   `full-skip:identification-effect-unresolved`) before `no-sellable-surplus`. Line 226-227
   leaves the ending as "stop if the pending mandatory deposit has no ... remedy". Pack was
   20/23 used (3 free), so the deposit was almost certainly optional: the pin must assert
   "relief closed impossible, tombstoned, deposit skipped, next admitted work = departure or
   another errand", not a stop. The Home-full relief row must list the remedy ladder in the
   Done/Impossible columns (sell -> destroy-cheapest -> impossible) so "impossible" is reached
   only after both remedies are evidenced exhausted.

6. **Fair play on the recall row (line 172).** "countdown high-water decrease" needs a counter
   the player cannot see; the snapshot exposes only `recalling: bool` (model.py:359, 1087).
   Redefine: progress for wait-recall = game turn advance while `recalling` is true, bounded
   by the game's maximum activation delay (a rule constant, not a timer). No hidden counter.

## Should-fix

- Executor-in-flight decisions: when the policy returns `""` (one-shot tail in flight,
  policy.py:10262-10265) define these as polls (not charged) but bounded by the executor's
  own tail length; otherwise N=3 sell / N=8 buy can close a legitimately running macro.
- Line numbers: `_RUNGS` is claim_ladder.py:212-418 (not 227-370); `_new_town_turn_arbiter`
  starts at town_arbiter.py:624. Two named tests do not exist as test files:
  `test_home_equip_enter_leave_loop_recorded`, `test_town_loot_supplier_alternation_recorded`
  (only `extract_*_fixture.py` exist in tests/). Name the real test modules or mark as new.
- Issue #2: add the 10-05 user requirement "replay the records with ON" to the graduation
  gate (lines 313-321): all recorded corpus fixtures replayed with `--enforce-town-claims`
  ON must produce zero `ownership:*` stops and zero new blocked reasons before the OFF path
  is deleted. Also list the OFF-only branches to delete (policy.py:5810-5830
  `preserve_home_hold`, `token_would_admit` deferred list) so the slice is reviewable.
- Live criterion for reverting log-only (lines 291-311): state a count-based one, e.g.
  "K consecutive town visits (K >= 20) across >= 3 dives with zero `owner-retired` and zero
  unexplained `would_retire` in bot-decisions.jsonl". "Short runs" is not a criterion.
- The 1-decision `remaining` fields in (a) (lines 219-221) did not reproduce in my sample
  (`arbiter.remaining` is null in rows 8507-8518); either cite the exact nested field or
  drop the numbers.
- (b) is partly self-inflicted: `_identify_staff_swap_purchase` (policy_shop.py:3631-3646)
  only allows a strictly fuller staff; the bot had sold identify staffs this visit and wanted
  2x12 back. Closing as impossible is correct for the watcher, but file the churn itself as a
  separate issue (the 10-03 decision wants the swap to succeed) so the cross-town trip for a
  19,618G full-identify source is not the only remedy.
- "Reaching 0 again is not a new minimum" is correct; also state that a route revision
  caused by one's own store exit (position changes from inside to outside) is not topology
  change, else every store exit resets the route rank.

## Open questions for the user (minimal)

1. While log-only remains, should a burst of retirements stop the bot at all? Options:
   (A) never (pure log-only, as decided 10-05); (B) count-based: 3 retirements within one
   town visit with no admitted work between them -> visible stop. The design assumes (A)
   after removing the 600 s window; the 10-05 live stop (equipment swap alternating) was
   the reason the window was added.

2. Confirm row-by-row live activation (must-fix 2) is acceptable under the 10-04 decision
   (one entrance, all call sites enumerated first). The enumeration still completes in
   slice 0; only enforcement is staged per row.
