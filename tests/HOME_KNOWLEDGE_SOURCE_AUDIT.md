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
