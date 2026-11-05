# Town ownership structural checks

Run `PYTHONPATH=src python scripts/item_sink_lint.py`. It includes the
item-intent check from `town_structure_lint.py`, which does not update its own
baseline. `tests.test_item_sink_lint` exercises the failure cases with AST
mutations.

## Dungeon ladder

`item_sink_lint.py` also runs `dungeon_ladder_lint.py`: the order of the rungs of
`HengbotPolicy._decide`, read from the AST, against the table in
`src/hengbot/dungeon_ladder.py`, and the owner rules' places in that table. Adding
or moving a rung changes the table in the same commit (`--print` lists the rows).
`tests.test_dungeon_ladder` exercises the failure cases.

## Producer census

The producer baseline (`town_producer_baseline.json`) and
`tests.test_town_structure_lint` were retired on 2026-11-01 (owner: the list
duplicated `town_work_review.json` and was no longer maintained). A new
string/key producer reachable from `HengbotPolicy.choose_key` is selected by
`town_structure_lint.producer_census`, and `scripts/town_work_manifest.py`
fails with "unmapped candidates" until it has a reviewed entry in
`town_work_review.json` (or is proved observational data by
`town_work_data_proof.py`). `tests.test_town_work_data_proof` exercises the
census.

The AST census respects imports (including relative imports, subpackages and
aliases), expands reachable method/callback calls, and tracks returns through
assignments, aliases, compositions and conditional expressions. It retains
string-annotated/literal-returning functions and return-value dependencies
conservatively: data helpers and dungeon paths are selected even when they
cannot independently emit a town action. Branch predicates and arbitrary
generated Python are not evaluated. Literal `getattr` dispatch is resolved;
computed reflection requires manual review.

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
