# Live22 implementation and verification

Implementation commit: `6a9dcdcbd4cefc248984f5ebabf20b9cbdc054c8`. Evidence commit: `2873dec5`. Baseline: `2fe5a02e`.

The code is committed; the complete requested verification remains blocked by contradictory test instructions. No game, live bot, executable, other worktree, or jsonlog was changed. The pre-existing untracked `.live8b-revert.py` was left untouched.

## Recorded cause and fix

See `live22-investigation.md` for the four step-1 answers with baseline file/line references. The bounty wants the Hunter Office at (25,71), not store 4. A stale supplier goal at (37,91) incorrectly rejects the office walk and composes a supplier-entry key, while retaining the bounty label. Splitting route ownership from leave ownership prevents one budget from bounding the cycle.

* `src/hengbot/town_arbiter.py:154` and `claim_goal_typing.py:484`: bounty approach/step-off/cashout/leave now all belong to quest-request.
* `src/hengbot/policy.py:5556`: a claim carrying the named bounty work identity is a town holder, including after suspension. This does not migrate every fixed-quest operation into S3.
* `src/hengbot/policy.py:16056` and `policy.py:6432`: bound `normal-step4-bounty` execution resumes the actual bounty producer; no supplier route is reconstructed as its continuation.
* `src/hengbot/policy_town.py:810`: measured movement uses the winning producer's declared Reach destination.
* `src/hengbot/policy_town.py:1195`: a repeated ineffective declared route resolves to `town:blocked:route-nonprogress:<family>`; it cannot alternate with a replacement supplier route. This uses the existing progress history and blocked-state mechanism, with no new threshold or attribute.
* `src/hengbot/policy_town.py:1750,1773`: ask the quest-request family gate before selecting/mutating bounty work; supplier entry emits an explicit `nothing-to-do-here:supplier:4` release; bounty disappearance emits a typed done observation. Missing routes stop visibly.

## Recorded acceptance boundary

Original state archive holds only the late cycle, turns 647164?647858; it cannot replay initial decisions 3731?3735. Five original state lines and four original decision lines are frozen under `tests/fixtures/live22-bounty`, with a hash manifest.

The production prime -> bounty producer -> procurement seam -> claim recording reaches live 5123 (7), then 5124 (live 3, new 7). Both fixed surface decisions keep the same quest-request claim and work identity. Their shadow has no gate-missing, declaration gap, or mismatch (`live22-seam-measurement.json`). Replay ends at 5124; later boards are not attributed to the changed 7.

The store-4 board is an independent attachment: the typed supplier release sends the same ESC as live 5125. Therefore its recorded outside board is a valid continuation and sends the live 5126 office walk 7, targeting (25,71), not re-arming the supplier approach. Route failure and ineffective-route stop are supplemental unit attachments, not claims of successful live cashout. Actual office cashout after the changed route is not verified live.

Eight new pins pass, including checkpoint restoration. A single whole-source revert to the baseline fails 4 assertions and errors on 3 absent declaration/gate paths; the recorded pin emits the original 3/invariant result. Output is preserved in `live22-single-revert.txt`. Later changes only add stronger holder/shadow assertions and the matching typed dispatch eligibility; the single-revert run was not repeated.

## Verification (one module per process)

| Module | Tests | Result |
| --- | ---: | --- |
| `tests.test_live22_bounty` | 8 | OK |
| `tests.test_town_progress_invariant` | 22 | OK |
| `tests.test_s33_shadow_recorded` | 6 | OK |
| `tests.test_live8` | 11 | OK |
| `tests.test_ownership_claims` | 24 | OK |
| `tests.test_test_fakery_lint` | 13 | OK |
| `tests.test_policy_quest` | 335 | OK, 7 existing skips |
| `tests.test_quest34_target_dead_recorded` | 3 | OK |
| `tests.test_quest_ammo_not_bought` | 8 | OK |
| `tests.test_quest_building_approach_progress` | 2 | OK |
| `tests.test_quest_carry_departure_recorded` | 4 | OK |
| `tests.test_quest_carry_town_block` | 4 | OK |
| `tests.test_quest_enter_approach_progress` | 5 | OK |
| `tests.test_quest_knowledge` | 12 | OK |
| `tests.test_quest_navigator` | 17 | OK |
| `tests.test_quest_prepare_return_stage2` | 10 | OK |
| `tests.test_quest_strategies` | 7 | OK |
| `tests.test_quest_travel_progress` | 3 | OK |

18 named module processes, 494 tests, 0 failures, 7 existing skips. All pre-existing module names containing bounty or quest are listed in this table; the only newly added such module is live22_bounty. Modules were invoked individually by name; no full-suite or matching-module runner was used.

Allowed stuck/withdraw OFF+s33 checks are saved in `live22-stuck-s33.json` and `live22-withdraw-s33.json`. OFF hashes are c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 and a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9. Stuck has no divergence; withdraw retains its declared first divergence at index 20 (rkc/enchant -> ESC`n%./shop:travel). No EXPECTED_FIRST change.

Before each commit, assertion audit output:

```
No changed pre-existing assertions or forbidden test edits.
```

## Pending clarification

The live22 prompt says to inherit the ownership S3.3 DO NOT RUN block, naming only stuck/withdraw fixtures as an exception. The block prohibits `tests.test_absorbing_states` and town producer purity parts. Later, live22 requires both. Neither was executed while the clarification request is pending. The required purity part would be `tests.test_town_producer_purity_part1`.

Origin: `C:/hengband/bot-client/jsonlog/fixer-live22-prompt.txt` and `fixer-ownership-s3-3-prompt.txt`. Their exact conflict is: "INCLUDING ITS DO NOT RUN BLOCK (exception: stuck/withdraw off+s33 fixtures)" versus "tests.test_absorbing_states" and "ONE town producer purity part if you touched a producer".

The JSON report is `live22-event.jsonl`.
