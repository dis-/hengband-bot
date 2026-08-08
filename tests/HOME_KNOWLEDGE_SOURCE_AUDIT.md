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

## 2026-08-08 verified Home paging fix event

The queued address burst was lost at the store-entry boundary. Moving onto a
store calls `disturb(player_ptr, false, true)` in
`player/player-move.cpp:240-243`; `disturb()` calls `flush()` when the live
`flush_disturb` option is enabled (`core/disturbance.cpp:44-55`); `flush()` sets
`inkey_xtra` (`term/screen-processor.cpp:23-31`); and the next `inkey()` clears
the terminal input queue with `term_flush()`
(`io/input-key-acceptor.cpp:195-206`). The store emits its first snapshot and
then requests that first key (`store/cmd-store.cpp:145-148`), so characters
already queued behind entry are discarded. This matches the measured one-page
result and explains why commands posted by a later decision, after Home is
already open, work normally.

The address scan now enters with `WAIT` alone. Each Home snapshot must carry
valid `stock_num`, `page_top`, and `page_size`. The exact page count is
`max(1, ceil(stock_num / page_size))`; page zero is required first; each single
posted `SPACE` must be followed by the exact next `page_top`; and a final
`SPACE` must produce `page_top == 0` before addresses become valid. No next key
is posted without observing the previous key's effect. Missing metadata, a
stale or skipped top, an outside snapshot after scanning began, or any other
truncation terminates at `home:address-burst-short`. The existing complete
ordinal and wrap provenance guard remains the withdrawal authority.

`test_public_verified_two_page_scan_addresses_page_two_target` is the public
`choose_key` through sender pin. With `stock_num=101`, `page_size=52`, it posts
`WAIT`, `SPACE`, `SPACE`, `ESC`, observes tops 0, 52, 0, and then composes the
page-two target as `5 pW ESC`. At `fb9efd9` the same pin fails exactly:
`AssertionError: False is not true : home:address-burst-short`.
`test_verified_scan_truncation_reaches_address_burst_short` pins the genuine
truncation terminal. The unique `verified-two-page-home-address-scan` absorbing
seed reaches a visible bounded terminal after observing both pages and making
the page-two withdrawal.

Verification: mutation battery 5/5 with `repo_tree_untouched: true`; fakery
lint unchanged at 9 existing violations and 116 declared findings in 93 tests;
2,511 tests at tip versus 2,509 at `fb9efd9`, zero test-name losses. Full suite
run 1 passed 2,511 tests in 209.404s with one opt-in skip; run 2 passed 2,511
tests in 210.488s with one opt-in skip.

## 2026-08-08 delayed Home entry observation fix event

MEASURED from the retained sender stream: `home:scan-address-burst` selected
and posted `WAIT` (`5`). The immediately retained record was a `player_turn`
surface snapshot at the same turn, with `store` absent (therefore no
`page_top` or `stock_num`) and `messages: []`; the following open-Home record
was store type 7 with `stock_num: 105`, `page_size: 52`, `page_top: 0`, and no
messages. The pending scan required `_store_entry_posted_owner` before it would
wait on that unchanged entrance snapshot. When sender/entry correlation was
not yet visible, it instead called `_home_scan_step` on `store=None`, which
classified the burst short and posted Escape. The later Home page then met the
ordinary posted-entry guard, which consumed that proving snapshot with
`store:entry-await-observation` and an empty key. Thus the 47 empty decisions
did not consume scan pages: each followed a separate scan-short/exit/re-entry
cycle. `page_top: 0` was never accepted as a complete three-page scan, and the
SPACE branch was never reached.

The scan entry boundary now treats the pending scan itself as authority to
await an unchanged Home-entrance snapshot before any page has been observed.
Positive refusal evidence still terminates entry; an outside snapshot after a
page has been recorded still terminates at `home:address-burst-short`. Once
Home is observed, the existing metadata step machine requires tops 0, 52, 104,
then 0, posting exactly one SPACE after each non-wrapped page and Escape only
after the verified wrap. Page-relative letters are recorded with ordinals
0, 1, and 2 before the page-three target is composed.

The public sender pin uses the live `stock_num: 105`, `page_size: 52` shape and
posts exactly `5`, SPACE, SPACE, SPACE, Escape with each intervening top
observed. The delayed-entry pin fails at `5d01b77` with
`AssertionError: '\x1b' != '' : page_top: 0 repeated before Home entry
observation`. The genuine truncation pin still reaches
`home:address-burst-short`, and the unique absorbing seed is now
`verified-three-page-home-address-scan`.

Verification: mutation battery 5/5 with `repo_tree_untouched: true`; fakery
lint retained its green ratchet of 9 existing violations and 116 declared
findings in 93 tests; the `test_policy.py` census is 1,913/1,914 with zero
test-name losses. Full suite run 1 passed 2,512 tests in 213.067s with one
opt-in skip; run 2 passed 2,512 tests in 211.010s with one opt-in skip.

## 2026-08-08 Home entry sequence capture fix event

This round changes no scan, entry, or routing behavior. While a Home approach
or Home store session owns decisions, `jsonlog/home-entry-capture.jsonl` joins
each public `choose_key` result to every character successfully posted for its
decision and to the first subsequently read snapshot. That next-snapshot
projection names type, turn, Home page metadata (`store_type`, `stock_num`,
`page_top`, `page_size`, and item count), messages, and player position.

Each record also carries its decision index and reason, the decision snapshot,
and independent pickle checkpoints of the pre-decision policy and decision
snapshot. Replay therefore restores every record separately and calls public
`choose_key`; records are never chained. The explicitly named pre-decision
state comprises the shopping approach, all four entry-observation owner terms
and entry key, store-leave and last-store context, the Home operation and
pending item/batch/atomic-operation terms, every `_home_address_*` term, every
prepared/pending/count/wrapped/short/processing scan term, and the Home
knowledge request/inflight/retry/leave/source/count terms.

Hypothesis (not implemented): the live CLI may read an intervening snapshot or
post a character sequence that the hand-authored fixtures omit, causing the
entry owner or pending scan to flip on a different decision boundary. Only a
real capture can distinguish that timing mismatch; this commit deliberately
does not alter either state machine.

Verification: the capture/replay test and CLI tests passed (119 tests); the
mutation battery met 5/5 expectations with `repo_tree_untouched: true`;
fakery lint remained at the base ratchet of 9 existing violations and 116
declared findings in 93 tests; test-name census was 2,528 versus 2,527 at
`b15c5b0`, with zero losses. Full suite run 1 passed 2,513 tests in 211.663s
with one opt-in skip; run 2 passed 2,513 tests in 210.879s with one opt-in skip.

## 2026-08-09 Home entry capture Snapshot-type fix event

This instrumentation-only fix changes no scan, entry, routing, optimizer, or
other gameplay behavior. The CLI's ordered snapshot parser returns a
`list[Snapshot]`; the capture handoff had incorrectly treated its first
`Snapshot` as a `(Snapshot, line)` pair and subscripted it a second time. The
handoff now passes that real `Snapshot` object directly, while retaining the
existing once-per-distinct-failure marker unchanged.

Field-read audit for `src/hengbot/home_entry_capture.py`:

- Snapshot: `store`, `turn`, `messages`, and `player` are dataclass attributes;
  all are read by attribute access and capture entry points now explicitly
  accept `Snapshot`.
- Store: `store_type` and `items` are `StoreState` attributes; `stock_num`,
  `page_top`, and `page_size` are also attributes, with the existing `getattr`
  compatibility reads retained for older object shapes. No store field is read
  as a mapping key.
- Player: `position` is a `PlayerState` attribute and is read by attribute
  access before `jsonable` projects the `Position` value.
- Messages: `Snapshot.messages` is a tuple of strings and is projected with
  `list(snapshot.messages)`; no message collection or element is treated as a
  mapping.

The corrected end-to-end capture test now invokes the same CLI handoff helper
with real `Snapshot` instances for both joined observations. On base `433515c`
the equivalent production expression fails as observed live:
`TypeError: 'Snapshot' object is not subscriptable` at `next snapshot`.

Verification: the capture and CLI tests passed 120 tests; mutation battery met
5/5 expectations with `repo_tree_untouched: true`; fakery lint retained its
ratchet of 9 existing violations and 116 declared findings in 93 tests. The
base and both final runs collected 2,514 tests, so there were zero test-name
losses. Full suite run 1 passed 2,514 tests in 211.574s with one opt-in skip;
run 2 passed 2,514 tests in 211.399s with one opt-in skip.
