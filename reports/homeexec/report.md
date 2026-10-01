# Home/store observed-input regression

Base: bb722bf3 (homeexec).

## Step 1: cause and scope

`src/hengbot/observed_input.py:71-79` preserves the established English store plan only for `shop:one-shot-buy`. All other composed store keys fall through to `_store_plan` at lines 185-189. `_store_plan` at lines 211-225 changes `dn\x1b` into `d` followed by a Japanese-only item chooser answer and a store escape. The production Home pin supplies the established English store boundary followed by a command boundary, so the remaining chooser/escape continuation cannot complete and the sender returns TERMINAL. The pin must remain unchanged.

Operations missed by A2: Home atomic deposit and withdrawal (including paged and quantified withdrawals), calibration deposit/restore-withdraw, equipment-transaction atomic deposit/withdraw, Home errand withdrawals, other composed Home deposit/get operations, ordinary shop purchases and composed page-switch purchases. Shop sales already retain baseline because the Japanese sale chooser has no capture; preserving an observed English store plan must include these too. Store-entry `5` remains separate; map-screen store commands remain rejected. Knowledge, character dumps and equipment actions are not store transactions and must retain their own modal plans.

Fix: extend the existing A2 English STORE-boundary preservation rule to composed store command keys (`p`, `d`, `g`, space), independent of producer name. Keep existing quantity/confirmation continuations and Japanese recorded chooser staging. No new UI classification, invented screen, policy state or checkpoint attribute is needed.

Hard-rule verification: tests.test_cli appears in the requested list but remains in the inherited DO NOT RUN block; the prompt explicitly exempts only tests.test_policy_home and tests.test_shop_one_shot. Do not run tests.test_cli. Catcycle is absent from this base and is explicitly excluded. Other requested modules and stuck/withdraw off+s33 will run individually. Do not edit the two assigned ammo failures or EXPECTED_FIRST.
