# live21: dispatch moment conflict (step 1)

Base: e6f9aa6aac4cf234bd7afb219ce56c923c00b01b, branch live21.

## Production moments

1. Composed, entry not posted: `policy_shop.py:4990-5051` composes the
   purchase/sale tail but emits the entrance activation key (`WAIT_KEY`, `5`).
   `_record_execution_declaration` (`policy.py:3505-3517`) records acting work;
   it only prepares a transition on successful posting when `post_on_emit`
   permits it. The purchase tail has not been sent.
2. Entry posted, matching store page not yet observed: the CLI calls
   `confirm_key_posted(key)` after successful sending (`cli.py:4342-4351`;
   once mode `cli.py:3458-3459`). That callback changes eligible declarations
   to awaiting (`policy.py:13121-13139`). The continuation is
   `shop.one-shot.send`, with `store-page-open` as the expected effect.
   This is an entry observation wait, not a posted purchase.
3. Matching page observed: `_release_staged_store_operation`
   (`policy_shop.py:314-342`) emits the bound purchase/sale tail as acting
   `shop.one-shot.send`. Successful posting changes it to awaiting
   `shop.one-shot.observe`, expecting the inventory/gold effect.

## Pins and contradiction

* `tests/test_live11.py:57-63` composes the entry, records its declaration,
  calls `confirm_key_posted(key)`, and expects awaiting. Lines 69-80 then
  release and confirm the tail on the matching page. Its changed-store pin
  (`:90-101`) likewise confirms entry posting before requiring declaration-stale.
  The plan advancement affects the bound store identity, not whether entry
  was posted.
* `tests/test_s33_shadow_recorded.py`,
  `test_live11_bound_shop_operation_and_changed_store`, repeats that recorded
  entry-posted setup and checks the outside wait, matching page and changed page.
* `tests/test_execution_declaration.py:169-207` is a constructed case with
  mocked purchase selection, not a recorded capture. Lines 186-189 describe
  composition before posting; acting is appropriate there. However lines
  192-195 explicitly confirm the **entry key** was posted and still require
  acting and no operation reference. Lines 196-207 subsequently release and
  confirm the purchase tail. Its assertion after entry confirmation conflicts
  with the requested posted/awaiting-entry-observation semantics.

The blanket `post_on_emit=False` at `policy_shop.py:5051` suppresses the entry
posting transition as well as avoiding a premature purchase posting transition.
It produces acting after entry confirmation, so live11 cannot dispatch its
awaiting `shop.one-shot.send` continuation (`policy.py:6372-6381`). A changed
store instead falls through acting dispatch to holder-silent. Changing that
flag to true would correctly track entry posting but violate the explicit
acting assertion in the constructed test. The shared flag cannot express
both incompatible assertions at the same confirmed-entry moment.

Neither observation generation, enforcement switch, plan cursor, store type nor
the test's manually chosen claim goal establishes a different transport moment.
Using those differences merely to preserve both assertions would not follow
the real posting event.

## Required decision and stop

Authorize correcting the constructed pin to require acting **before** entry
confirmation and awaiting the store page **after** entry confirmation, keeping
the purchase tail unposted until its own confirmation. Alternatively specify
a distinct production event that the constructed pin should simulate instead
of `confirm_key_posted(wait_key)`.

The live21 prompt explicitly requires stopping when evidence shows a pin is
wrong; no expectations, EXPECTED_FIRST or production code were changed.

## Verification before stop

Each module ran in its own Python 3.13 process with PYTHONPATH=src;tests;scripts.

* tests.test_live11: 2 tests, 2 failures, reproducing acting vs awaiting and
  holder-silent vs declaration-stale.
* tests.test_execution_declaration: 29 tests, passed.

Remaining requested modules and stuck/withdraw OFF+s33 fixtures were not run
because the explicit decision-needed stop occurred before step 2. No full
suite, forbidden runner, game, bot, or other worktree was touched.

## Step 2: ruling applied (2026-10-01)

The Claude ruling at 05:10 resolves the decision above in favor of recorded
live11 evidence. The constructed test retains its name and purchase-tail
assertions: acting before entry confirmation, awaiting after confirmation,
and no operation_ref until the purchase tail itself is posted.

`policy_shop.py:5049` restores the normal post-on-emit entry transition.
`policy.py:13146` keeps operation_ref absent when the confirmed step is
shop.one-shot.dispatch; all other posted steps retain their decision reference.
`policy.py:6181` recognizes this store-page wait in declaration binding.
`policy.py:6756` validates the reference-free entry wait against the existing
posted visit, producer, claim goal, work identity, arguments and observed store.
The changed-store case still stops declaration-stale. No new persistent
attribute or threshold was introduced; recorded pins cover pickle restoration.

The original blanket post_on_emit=False conflated posting the entrance key
with posting the purchase tail. One flag suppressed both transitions, leaving
the entry declaration acting after transport confirmation. The fix permits
entry posting to await its page without falsely recording a posted purchase.

Each requested module ran in its own Python 3.13 process, with
PYTHONPATH=src;tests;scripts. Final results:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_live11 | 2 | passed |
| tests.test_s33_shadow_recorded | 6 | passed |
| tests.test_execution_declaration | 29 | passed |
| tests.test_shop_one_shot | 53 | passed, 1 skipped |
| tests.test_policy_shop | 279 | passed, 1 skipped |
| tests.test_town_progress_invariant | 22 | passed |
| tests.test_live8 | 11 | passed |
| tests.test_test_fakery_lint | 13 | passed |

The single revert check injected the old blanket post_on_emit=False into the
entry offer in memory. The corrected constructed pin failed at its post-entry
awaiting assertion, as required; no source file was reverted.

stuck and withdraw each ran separately in off and s33 modes using the explicitly
authorized fixture exception. OFF hashes match the frozen values:

* stuck: c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5
  (4 rows); s33 has no divergence, no declaration gaps/mismatches, no trajectory
  defect and no final gate escape.
* withdraw: a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9
  (34 rows); s33 first differs at index/sequence 20, changing recorded
  town:enchant-launcher-todam to shop:travel, exactly EXPECTED_FIRST. The
  first-divergence measurement has no declaration gaps/mismatches, trajectory
  defect or final gate escape; it intentionally stops at this expected boundary.

EXPECTED_FIRST and all other expectations are unchanged. The only corrected
expectation is the one explicitly authorized by the ruling. Work is confined
to the live21 worktree; no game, live bot, external log or other worktree changed.
