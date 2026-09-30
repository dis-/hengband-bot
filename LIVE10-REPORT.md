# Live10 weapon restoration

Base: main 0e7a20e6, fast-forwarded before implementation.

Cause on the base: policy_equipment.py:2928 overwrote the sub-hand takeoff offer with `equipment.restore-combat-hand`, empty arguments, and no continuation. The accepted `tb` became awaiting with continuation `equipment.restore-combat-hand`; policy.py:6185 onward handled `equipment.next-action` but not this continuation, reaching the stale fallback even after success. Claim 193 was stale. The decisions log contains execution declarations; the ownership-claims log omits execution fields. The 435 declaration used the weapon name/tval/sval signature, already independent of pack letters. The 436 declaration compared no item identity at all. This was an unsupported observed-success continuation, not a slot-letter mismatch.

Fix: each mining hand action offers its own declaration with target hand and equipment_identity. Town restoration preserves that offer. Main-hand fallback also declares its stable identity. `equipment.restore-observe` verifies the exact equipped weapon or the exact removed digger present in inventory with its hand empty, then calls the restoration producer for the next action. After the recorded takeoff, the producer releases with no-restoration-required. An unrelated equipped item stops stale. No new persistent attributes or thresholds.

Pins: tests/test_live10.py uses recorded boards at turns 458183 / 458195 / 458200 (decisions 435 / 436 / 437). The first pin sends wga, observes the weapon, sends tb, observes the digger removed, and releases the holder, both with and without checkpoint restoration. The second substitutes a different equipped weapon and requires a stale stop after checkpoint restoration. Both fail with the implementation reverted; removing only the identity comparison also fails the second pin (it wrongly returns tb).

Verification: test_live10 2 passed; test_policy_equipment 192 passed; test_declarations_r3b 15 passed; test_test_fakery_lint 13 passed. The initial lint run detected a BOM in the new test file; it was removed and lint passed. Only one module per process was used.

S3.3 fixtures: stuck OFF hash c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5, no divergence, trajectory_defect null. Withdraw OFF hash a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9, first divergence remains designed index/sequence 20, shop:travel, trajectory_defect null. Both have zero declaration gap rows and mismatch counts. EXPECTED_FIRST unchanged.

Implementation commit: b8ee91ed. Pins and report are committed separately. Verification uses recorded production seams; no live game session was started.
