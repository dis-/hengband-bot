# Class C3 implementation

Worktree: `C:\hengband\bot-client-c2`, branch `classC2`. Started at
`01869e27`. The requested first `git merge main` merged exactly `b24fd077`
without conflicts, producing `6aabf2ea`; no later movement of the shared
`main` branch is included.

## Item 1: attempted non-Home stores

The first plan projection filtered `nonhome_attempted_without_effect`, but
the projection rebuilt after terminal transitions did not. Consequently an
empty Alchemist stop could be returned again after its attempted latch was
reopened. `policy_shop.py:1314` applies the same no-effect ledger protection
to that final route selection, without issuing a departure verdict there.

With the erroneous shop route gone, `_terminal_equipment_blocker` could expose
an incidental calibration blocker before the existing supply remedies.
`policy_town.py:5752` preserves the exhausted shop supply's remedy evaluation;
`policy_town.py:5853` handles the corresponding no-recall-destination case
only in the departure evaluator, after recovery, restock and cross-town
remedies. The unchanged `test_non_home_leave_blocks_reopened_out_of_stock_stop`
pin passes, as do the Class C stockout/recovery/restock pins.

Item 1 commit: `a774ae8b`.

## Item 2: fitting launcher ammunition

- `policy_home.py:1120`: the common normal-dive ammunition target computes
  available weight from the current worn/pack kit and the retained two-stack
  ammo plan, caps the result at the existing 99 target, and uses an offered
  item's actual unit weight when available. Quest-floor retention and the
  separate fixed-quest force/readiness accounting keep their existing target.
- `policy_home.py:810`: retention exposes only the ammunition excess needed
  after other safe retention surplus. This also applies when an equipment
  owner has retired. The ordinary deposit candidates and their protection
  checks are shared by `policy_home.py:1177`, avoiding a separate approximation
  of required supplies. Matching launcher ammo is selected after other excess.
- `policy_home.py:1305`: the existing overweight deposit selector consumes
  those candidates in the existing priority order. Partial deposits still
  leave their retained stack in the projected batch board at line 2932.
- `policy_home.py:3880`, `policy_supply.py:723`: Home top-up and generic
  procurement quantities use the fitting target, so Home stock cannot undo
  the weight remedy on the same kit, including a fresh policy/next visit.
- `policy_shop.py:2334`, `policy_shop.py:2343`, `policy_shop.py:2358`,
  `policy_shop.py:2975`: shared purchase provenance, eligibility and emitted
  quantities respect the fitting target, including quest-supply procurement
  in town. A zero fitting shortfall cannot emit a one-ammo purchase.
- `policy_town.py:2331`, `policy_town.py:2702`, `policy_town.py:2815`: ordinary
  ammo routes and pending quest-ammo supplier claims stop at the fitting town
  target. Fixed-quest entry still requires its raw force count of 99; its
  readiness implementation is unchanged.

No new tunable threshold or state attribute was introduced. No equipment
comparison or depth requirement was changed. `EXPECTED_FIRST` is unchanged.

Item 2 commit: `19a6fd1f`. The fitting purchase clamp applies to the currently
wielded launcher's ammunition; explicitly named other quest ammunition keeps
its pre-existing procurement treatment.

## Pins and fidelity

`tests/test_classC2_departure_recorded.py` retains the byte-faithful 16:16
fixture hash and its declared attachment seam. New/updated exact assertions
cover 1768/1750, a four-shot deposit (`di4\r`), 95 retained shots, 1748 remaining
weight, both fresh and checkpoint-restored selectors, and the real public Home
route as the first changed decision. A constructed extra-phase-scroll board
asserts the batch order: phase scroll first, then four shots.

A constructed next-visit shop board with the same kit and 90 shots buys
exactly five, stops at 95, neither buys nor withdraws above that fitting count,
and buys at most 95 if starting with no ammo. Matching sling shots, bow arrows
and crossbow bolts receive the same minimum-weight treatment. The raw fixed
quest force status remains `{measured: 95, required: 99, ready: false}` and
quest travel is refused.

The post-deposit board is an explicitly constructed effect board, not a later
historical response. Weight relief makes optional launcher-enchantment work
live, so the public router may visit that shop before departure. The departure
evaluator separately retains the guardian remedy, selects Orc cave 18F rather
than refused Yeek cave 12F, and has every ordinary/recall departure conjunct
ready with the 1748 kit. No subsequent historical board is driven as an effect
of a changed key. The no-alternate guardian refusal remains visible.

`tests/test_live36_weight.py` keeps its existing staff-first and all required
supply/charge pins. Its old no-safe-staff/no-weight-owner assertion is replaced
by the new decision's exact fallback: six shots only, rather than a false claim
that no weight owner exists. No pin is deleted or assertion loosened.

## Pending for Claude (DO NOT RUN)

The explicit Class C3 verification list overrides the earlier ban on
`tests.test_policy_shop`; it ran as one module/process under 60 seconds.
The following remain unrun and pending for Claude:

- `scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`,
  `scripts/hunk_guard.py`, `scripts/verify_scope.py`, `scripts/mutation_battery.py`.
- `tests.test_cli`, `tests.test_policy_town`, `tests.test_absorbing_states`.
- `tests.test_unaffordable_claim_tour_recorded`,
  `tests.test_town_approach_retired_recorded`,
  `tests.test_overweight_home_unreachable_recorded` (long recorded replays).
- `tests.test_town_producer_purity` and
  `tests.test_town_producer_purity_part1` through
  `tests.test_town_producer_purity_part6`.
- Full-fixture `scripts/first_divergence_s3_3.py` runs beyond the explicitly
  requested stuck/withdraw OFF and S3.3 cases, and any all-matching sweep.

Per-module counts, replay measurements, the semantic single-revert checks and
the final implementation commit are recorded in the accompanying Class C3
verification/result artifacts.
