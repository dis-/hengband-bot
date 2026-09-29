# Cross-area fundraising: town replay index 1256

## Step 1: diagnosis

Reproduction: `PYTHONPATH=src;tests;scripts python scripts/crossarea_1256_diagnose.py`, with the existing town-approach replay fixture. The list index is 1256 and the policy decision sequence before the call is 1253. Both modes see the same Yeek 1F board, food state `normal` (mana-food race), gold 15,288, 12 pack items, a charged rock-melting wand (8 charges) edible in the pack, a charged healing staff (2 × 6 charges) edible at Home, ready light, no hunger, and spare pack capacity (12/23). Home knowledge is current; the Magic food shop (store 5) has not been attempted and no affordable food ware was recorded. The first-run waiver is false: ON has run count 2 and purpose `FundraisingPurpose(identity=59, mode='mine', first_run_food_waiver=False)`, with an active record and completed departure child posted at sequence 1190. OFF has no purpose record because that switch is disabled.

The `FundraisingFacts` values in both modes are `carried_edible=True`, `hungry=False`, `light_ready=True`, `pack_full=False`, `objective_achieved=True`, `procurement_exhausted=False`, `first_run=False`. `fundraising_run_verdict` gives `may_depart=True`, `may_continue=False`, `must_return=True`, `needs_procurement=False`. The **only positive return input is `objective_achieved`**: gold 15,288 exceeds `FUNDRAISING_GOLD_TARGET = 15000` ([policy_constants.py](src/hengbot/policy_constants.py), line 197). The verdict computes that return at [policy_fundraising.py](src/hengbot/policy_fundraising.py), lines 123-131; the fact is constructed at lines 208-216.

With the switch OFF the key is `7`, reason `fundraise:seek-loot`. With it ON the key remains `7`, reason `fundraise:seek-upstairs`, and `_last_return_trigger` becomes `fundraising-run-exhausted`. The ON town-return trigger comes from [policy_town.py](src/hengbot/policy_town.py), lines 5471-5480, which reads the shared verdict. OFF bypasses it at 5485-5486. Legacy fundraising at [policy_fundraising.py](src/hengbot/policy_fundraising.py), lines 987-996, returns at the gold target only for `scavenge` or when no known treasure remains. This run is `mine` with known treasure, so it continues to the loot route at line 1104. The shared verdict instead treats the achieved resource objective as a return trigger regardless of remaining known treasure. The stale OFF `_last_return_trigger` value `guardian-kit-insufficient` was not set by decision 1256; its active return predicates were false.

## Step 2: decision against the adopted design

The 2026-09-29 user decision 1 in `C:\hengband\bot-client\SOL-DESIGN-ownership-s3-draft.md:540-547` permits a food waiver only on a character's first run when there is no edible anywhere. This board is the second run and has edible devices both carried and at Home, so the waiver is irrelevant. The adopted astra design A1 (`C:\hengband\bot-client\jsonlog\design-ownership-crossarea-astra.md:21-26`) requires the same verdict on town admission and dungeon continuation, with the *resource objective* and current return triggers as explicit inputs. The current shared verdict says the declared 15,000 gold objective is achieved. Continuing solely because more treasure is visible would override that shared return result with the legacy mining exception. On the recorded facts, the shared return verdict is the design-consistent outcome.

Therefore the frozen `CROSSAREA_EXPECTED_FIRST` table is **not edited**, and no policy change is made to force 1256 to match OFF. The prompt's Step 2 says to write this argument and stop for Claude's decision when the verdict is right. Step 3's per-pair check is consequently pending; no reduction of the 33 descent / 32 ascent capture is claimed.

## Verification

Each module ran in its own Python process with `PYTHONPATH=src;tests;scripts`:

| Module | Tests | Result |
| --- | ---: | --- |
| `test_crossarea_fundraising` | 11 | pass |
| `test_calibration_crossarea_debt` | 5 | pass |
| `test_ownership_s3_3_first_divergence` | 3 | pass |
| `test_policy_town` | 598 | pass |
| `test_policy_home` | 184 | pass, 4 skipped |
| `test_town_approach_retired_recorded` | 8 | pass |
| `test_test_fakery_lint` | 13 | pass |

Total: 822 tests, 4 skipped. The diagnostic replay was also run separately under OFF and ON through decision index 1256.

{"topic":"crossarea-r1a2","implementer":"gpt-6-sol","index":1256,"cause":"gold-objective-achieved","off":["7","fundraise:seek-loot"],"on":["7","fundraise:seek-upstairs"],"decision":"shared-verdict-consistent; frozen-table-unchanged; stop-for-Claude","pairs_checked":0,"pair_check_status":"pending-by-step-2-stop","tests":822,"skipped":4}
