# Home/store observed-input regression

Base: bb722bf3 (homeexec).

## Step 1: cause and scope

`src/hengbot/observed_input.py:71-79` preserves the established English store plan only for `shop:one-shot-buy`. All other composed store keys fall through to `_store_plan` at lines 185-189. `_store_plan` at lines 211-225 changes `dn\x1b` into `d` followed by a Japanese-only item chooser answer and a store escape. The production Home pin supplies the established English store boundary followed by a command boundary, so the remaining chooser/escape continuation cannot complete and the sender returns TERMINAL. The pin must remain unchanged.

Operations missed by A2: Home atomic deposit and withdrawal (including paged and quantified withdrawals), calibration deposit/restore-withdraw, equipment-transaction atomic deposit/withdraw, Home errand withdrawals, other composed Home deposit/get operations, ordinary shop purchases and composed page-switch purchases. Shop sales already retain baseline because the Japanese sale chooser has no capture; preserving an observed English store plan must include these too. Store-entry `5` remains separate; map-screen store commands remain rejected. Knowledge, character dumps and equipment actions are not store transactions and must retain their own modal plans.

Fix: extend the existing A2 English STORE-boundary preservation rule to composed store command keys (`p`, `d`, `g`, space), independent of producer name. Keep existing quantity/confirmation continuations and Japanese recorded chooser staging. No new UI classification, invented screen, policy state or checkpoint attribute is needed.

Hard-rule verification: tests.test_cli appears in the requested list but remains in the inherited DO NOT RUN block; the prompt explicitly exempts only tests.test_policy_home and tests.test_shop_one_shot. Do not run tests.test_cli. Catcycle is absent from this base and is explicitly excluded. Other requested modules and stuck/withdraw off+s33 will run individually. Do not edit the two assigned ammo failures or EXPECTED_FIRST.

## Step 2: implementation and verification

Corrected source references (base bb722bf3): the A2 owner restriction is at observed_input.py:71; STORE dispatch is at :160-164; `_store_plan` begins at :175 and chooses Japanese item features at :185-188. In the fixed file the generalized preservation rule is at :72. The earlier Step 1 references to :185-189 and :211-225 were inaccurate; these are the inspected references.

The fix preserves composed `p`/`d`/`g`/page-space transactions when the executor already observes the English STORE boundary used by A2, for any owner. Existing continuations are kept unchanged; non-store modal operations still go through their dedicated plans. Shop sale keys already fell back unchanged and remain unchanged. The Japanese recorded store paths and entrance staging retain their existing gates. This extends A2's compatibility rule; it does not claim a newly captured English chooser or complete English UI coverage beyond that established boundary.

| Verification (one module per process) | Result |
| --- | --- |
| tests.test_policy_home | 184 run, 4 skipped, only 2 assigned ammo failures; unchanged production Home entry/deposit pin passes |
| tests.test_shop_one_shot | 53 run, 1 skipped, 1 ammo failure; production one-shot entry/buy pin passes |
| tests.test_classA_observed_input | 30 pass, including added 13-case preservation pin and recorded Japanese gates |
| tests.test_input_executor | 73 pass |
| tests.test_live23_home_cycle | 7 pass |
| tests.test_test_fakery_lint | 13 pass |
| tests.test_cli | Not run: inherited explicit DO NOT RUN block, no explicit exception for this module |
| tests.test_catcycle | Omitted as requested: absent from base |
| Lone revert of code | New pin fails in 11 subcases; original code restored in finally |
| Assertion audit | No changed pre-existing assertions or forbidden test edits. |
| git diff --check | Pass |

Failures left untouched:
- test_matches_game_weight_limit_and_preserves_plain_plus_highest_ammo: [14, 0, 27] != [72, 0, 27].
- test_overweight_rearm_tracks_successful_deposit_progress_to_weight_limit: 3 != 4.
- test_recorded_ammo_top_up_buys_71_plain_bolts_into_q: 64 != 71 (additional unrelated ammunition failure).

Stuck OFF: 4 rows, OFF hash c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5. Stuck S33: no first divergence, gate_final_count=0. Withdraw OFF: 34 rows, OFF hash a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9. Withdraw S33 stops at its unchanged EXPECTED_FIRST (index 3, sequence 3): historical `~9\x1b` / home:request-knowledge-scan versus `\x1b` / equipment-transaction:catalogue-leave-for-scan; trajectory_defect=null, gate_final_count=0. No claims about later divergent boards. OFF withdraw gate_final_count=20 and missing detector declarations are baseline observations, not fixed here.

PowerShell treats unittest stderr progress as NativeCommandError in these captured pipelines even when unittest ends OK; the result above follows the actual unittest summary. Raw logs and replay JSON accompany this report. No fixture hashes, pre-existing assertions, policy checkpoint state or EXPECTED_FIRST were edited.

Step 1 commit: e965fb4a. Step 2 commit: the commit containing this report and the code/pin change.
