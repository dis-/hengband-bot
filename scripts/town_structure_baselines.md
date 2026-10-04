# Town ownership structural checks

Run `PYTHONPATH=src python scripts/item_sink_lint.py`. It includes the producer
and item-intent checks from `town_structure_lint.py`; neither checker updates
its own baselines. `tests.test_town_structure_lint` and
`tests.test_item_sink_lint` exercise their failure cases with AST mutations.

## Producer baseline

`town_producer_baseline.json` grants exceptions at exact `file:qualified-function`
sites. A new string/key producer reachable from `HengbotPolicy.choose_key` must
have both an `@claims` marker and a producer entry in `claim_ladder.py`.
Exceptions have one reviewed reason: dungeon-only, pure helper, delegated
adapter, or town producer to migrate. There are no module/family exemptions.
An exception that disappears, becomes unreachable, or becomes registered fails
the check and must be removed in the same reviewed change.

The AST census respects imports (including relative imports, subpackages and
aliases), expands reachable method/callback calls, and tracks returns through
assignments, aliases, compositions and conditional expressions. It retains
string-annotated/literal-returning functions and return-value dependencies
conservatively: data helpers and dungeon paths appear in the explicit baseline
even when they cannot independently emit a town action. Branch predicates and
arbitrary generated Python are not evaluated. Literal `getattr` dispatch is
resolved; computed reflection requires manual review.

Do not refresh the baseline to make a failed check pass. Register a new
producer; migrate old producers by removing their exceptions. The existing
`reserved_item_command` adapter handles consumption and prompt tails so the
consumption migration introduces no new unregistered producer definitions.

## Item-intent baseline

`item_reservation.ITEM_RESERVATION_SOURCES` lists exact policy attributes, their
component of the composed reservation predicate, and a reason. The check scans
HengbotPolicy and its mixins/ancestors for pending/retry/reserve/deferred/inflight
names, signature/identity/item values, selectors, container-key writes,
in-place collection additions, and literal `setattr` writes. It propagates
local assignments rather than checking only direct identity-function calls.

`item_intent_baseline.json` contains individual, reasoned exclusions: observed
catalogues, negative eligibility caches, completed-operation reports, scalar
observations, and navigation/claim/UI state are not selected item operations.
New attributes require registration or an explicitly reviewed exclusion;
deleted sources/exclusions and unknown predicate components fail the check.

Existing reservation semantics are preserved. Atomic Home work, retry deposits,
equipment transactions and the curse-scroll reserve retain their existing
exclusive owners. Retention remains a quantity, never an invented owner.
Queued selections and use observers are registered in their existing
non-exclusive role; they do not acquire a new exclusive owner merely because
their state is inventoried. The active transfer/transaction seam confers
ownership as before.

## Item command serialization

Town and dungeon consumption uses `reserved_item_command`, which obtains an
item-bound `ReservationVerdict` and calls the sole `item_command` serializer.
Kinds `read`, `quaff`, `eat`, `staff`, `wand`, `rod`, `fire`, `throw` and `refill`
serialize the actual keys `r`, `q`, `E`, `u`, `a`, `z`, `f`, `v` and `\F`.
Identification's observed source-command keys are normalized by the adapter.
Prompt tails, aiming and read rebinding retain their original spelling.

The prefix lint also covers constants, imported aliases, local/module prefix
aliases and common string formatting. Three building-menu sites are pinned to
exact existing expressions and multiplicity: library identification (`a`),
quest-building request (`q`) and the rumor menu macro (`r`). They are menu
selections; new item-command compositions at those sites still fail the check.
