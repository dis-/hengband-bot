# Home knowledge catalogue fix event

The authoritative Home catalogue is the one-snapshot knowledge response to
`~9`. Store pages do not populate or complete `OwnedEquipmentCatalog`; they
only bind a displayed page ordinal, letter, stack count, and item identity for
an actual withdrawal. The emitter's `stock_num`, `page_top`, and `page_size`
are parsed and used to reject inconsistent address-burst observations. They
are never evidence that the displayed page is the whole Home.

## Request preconditions

The policy requests `~9` when it is outside a store and in town; Home is known
to exist; the player is not recalling or standing on a store entrance; the
catalogue is incomplete; no knowledge request, store leave, or store entry is
in flight; and no equipment transaction, withdrawal-address workflow, or
address burst already owns the decision. Town/outside and Home availability
make the command meaningful. Recall, entrance, and in-flight checks preserve
input ownership. The incomplete/request checks preserve the one-shot contract.
The workflow checks prevent catalogue acquisition from interrupting an already
bound operation. No prior Home visit, completed Home leave, observed store
page, identification need, or next-store selection is required.

## Pins and historical disposition

- `test_plain_town_requests_home_knowledge_before_any_home_visit` is the public
  `choose_key` pin. At `2cc2475` it failed exactly as expected: `AssertionError:
  '6' != '~9'`. No Home page or leave state is injected at tip.
- `test_knowledge_response_records_all_101_items_and_source` proves a complete
  101-item response records source `~9`, telemetry count 101, and 101 equipment
  catalogue entries.
- `test_store_page_metadata_is_parsed_for_address_verification` pins the three
  emitter page-verification fields.
- `test_public_composer_requires_complete_ordinal_provenance_guard` remains the
  public withdrawal pin: its key still depends on wrap-proven page ordinals.
- The unique `catalogue-incomplete-knowledge-unreachable` absorbing seed reaches
  the named knowledge-request terminal at tip and exhausts historically.

## Verification record

- Mutation battery: 5/5 expectations met; `repo_tree_untouched: true`.
- Fakery lint ratchet: 9 existing undeclared violations, 115 declared findings
  in 92 tests; the figures are unchanged from the base ratchet.
- Test names: 2,521 definitions at tip versus 2,518 at `2cc2475`; zero losses.
- Full suite run 1: 2,506 tests in 327.052s, pass, one opt-in skip.
- Full suite run 2: 2,506 tests in 327.439s, pass, one opt-in skip.

## 2026-08-08 mutation-invalidation fix event

Two rules now have separate owners. A Home mutation always invalidates the
page-relative address record: displayed pages, ordinals, letters, page count,
and wrap proof are discarded and must be re-observed before withdrawal. Home
contents are instead updated from a bound operation: a posted deposit is added
once and an owned withdrawal is removed after its inventory gain is observed.
An unbound command whose content effect cannot be proved explicitly invalidates
the contents and reacquires them through `~9`.

An incomplete catalogue is requestable while equipment work is outstanding.
The old `not self._outstanding_equipment_work()` veto is gone. In particular,
an optimizer preparation naming `home-scan-incomplete` authorizes `~9` without
Home existence, availability, route, visit, or shopping-approach permission.
An observed Home remains an alternative trigger for ordinary initial catalogue
acquisition; it is not a veto on a catalogue already required by optimization.

The retained request terms are:

- `snapshot.store is None`: a knowledge command cannot steal store-menu input.
- `snapshot.in_town`: Home knowledge is a town-maintenance prerequisite, not a
  dungeon tactical action.
- `home-scan-incomplete` blocker or observed Home: the former is independent of
  all Home availability and routing; the latter starts unsolicited first
  acquisition without preempting unrelated synthetic/tactical town decisions.
- `not snapshot.player.recalling`: preserves recall input/action ownership.
- not standing on a store entrance: preserves the entrance/departure invariant.
- catalogue incomplete: the command has no purpose after authoritative content
  acquisition or an exactly recorded mutation.
- no request already requested: preserves the confirmed-post one-shot latch.
- no store leave or entry posted owner: preserves an in-flight store boundary.
- no prepared address scan and no pending address burst: preserves the address
  command's one-shot and wrap-proof ownership. Address work never makes Home
  availability a prerequisite for `~9`.

Pins and historical disposition:

- `test_public_deposit_preserves_catalogue_or_incomplete_work_requests_it`
  drives public `choose_key` after a complete catalogue and one recorded Home
  deposit. It proves contents remain complete and usable, every address is
  stale, and explicit incompleteness requests `~9` on the next decision despite
  `home-scan-incomplete`, outstanding equipment work, an active Home approach,
  and no Home tile. At `3f335e3` it fails with `AssertionError: False is not
  true : home-scan-incomplete persisted after a proven Home deposit`.
- `test_invalidated_address_refuses_until_home_is_reobserved` remains the
  withdrawal provenance pin: a mutation forces the atomic address burst before
  any displayed letter can authorize withdrawal.
- The unique `catalogue-invalidated-equipment-work-repetition` absorbing seed
  reaches the named `home:request-knowledge-scan` terminal at tip. Its
  `home-scan-incomplete` preparation and active Home approach reconstruct the
  old refusal/town-repetition mechanism, which exhausts historically.

Verification: mutation battery 5/5 with `repo_tree_untouched: true`; fakery lint
at its green ratchet of 9 existing violations and 116 declared findings in 93
tests; 2,522 test definitions versus 2,521 at `3f335e3`, zero losses. Full suite
run 1 passed 2,507 tests in 340.904s with one opt-in skip; run 2 passed 2,507
tests in 338.756s with one opt-in skip.
