# batchfixA reproduction (base a4e51bf9)

Each invocation runs one authorized test module or named test, never a suite runner. No live bot/game/worktree was changed.

| Test | First divergence | Cause |
| --- | --- | --- |
| control_client four routing/shadow pins | CLI exits 75 before mocked transport, versus 0/3 | cli.py:3130 process-global Windows port-1 mutex collides with another test process. `_acquire_control_owner` dates to 6f842037; no change in d7429e7b..HEAD. Re-run DisabledCliPinTest alone: 9/9 pass. |
| posted_effect P1b | ESC/home:queue-withdraw-identify-staff-reserve versus historical Eh/survival substitution | c989ea1a, policy_town.py store-context preservation; already fails with d7429e7b production. Restore the historical substitution only at the test input seam; keep production store protection. |
| policy_structure foreign cases | ProductionHarness is bound as a foreign TestCase in three modules | 28ee9a9a (Class A), 073fa4ba (storewhich), 3b0d6c02 (storewhich2). Import the harness module instead of its TestCase. |
| pickup historical atomic macro | SENT versus historical TERMINAL; compiler stages g/a | 28ee9a9a cli.py:2155 compile_observed_input. Already fails on d7429e7b. Supply the explicitly historical atomic operation through the executor seam, preserving all outcome assertions and production compilation. |
| live32 two shadow/pickle pins | pickle.dumps raises local-lambda AttributeError | policy_town.py:2973 registry caches local closures (introduced by 65977ec0, later split by afc0a29a). d7429e7b and 19a6fd1f^ pass both pins; 19a6fd1f fails both. Its policy_home.py:816 ammo retention invokes _ammo_procurement_target, then :1145 weight candidates, then :1188 the registry (stack in registry-first-call.log). Replace closures with serializable callable code. |
| ownership_s2a1 posted closure | three barrier-provenance-missing rows versus two | already fails on d7429e7b. Recorded attachment: sequence=5429, posted=5428; choose_key increments then test increments: 5430/5432/5434 wait, 5436 releases at existing STORE_STUCK_LIMIT=8. ef93a790 added the incorrect two-row assertion while STORE_STUCK_LIMIT was already 8 (printed git blob); 6601d170 had changed it months earlier. This is a pre-existing assertion arithmetic error, not a regression from today's merges. Do not change the assertion or tune the production bound without an applicable ruling. |

Historical baseline commands/results are in validation/batchfixA/d7429e7b-*.log. The common brief's claim that all these pins passed on d7429e7b does not hold for P1b, historical atomic pickup, or the closure wait count in this checkout.

## Step 2 fixes

- Production registry callbacks are bound methods of a serializable `_TownNeedLookup`, replacing local lambdas. Existing cached data stays bound to the restored policy. The new recorded-board pin checks category/store resolution and mutable candidate changes before and after restoration. Original ON/OFF shadow byte identity pins pass.
- Mocked endpoint tests now mock only the endpoint lease too. The production process guard remains checked by test_cli, including a second real process. No transport fallback/duplication/shadow assertions changed.
- Class A/storewhich/storewhich2 import the harness module; they no longer export a foreign TestCase binding. Their own inherited tests still run.
- Historical P1b feeds its recorded downstream rewrite at the procurement seam and checks the real production posting release. Disabling that release makes the pin fail. It still starts from the recorded board and recorded visit.
- Historical atomic pickup feeds the explicitly pre-fix atomic macro by bypassing only the new compiler in that one historical test. It still traverses the real executor/transport/classifier and reproduces the recorded stop. Current compiled pickup remains checked separately through the production sender.
- No EXPECTED_FIRST, fixture, existing assertion, depth gate, weight rule, speed rule, or production threshold was changed.

Adjacent-commit checks: the ORIGINAL P1b pin passes at c989ea1a^ and fails at c989ea1a; the ORIGINAL pickup macro pin is checked on both sides of 28ee9a9a. Both are earlier than d7429e7b. Live32 passes both pins at 19a6fd1f^ and fails both at 19a6fd1f, confirming the ammo-fit merge exposed the serializability defect rather than changing its shadow verdict.

R1 printed identifier evidence (`assertion_change_audit.py --travel-symbols`): `7 '(' -> STORE_HOME`. No item-slot/message/source mappings were inferred. R2: no new UI classification, continuation, or screen fake. R4: historical P1b uses the recorded replacement key; pickup historical simulation reproduces the original macro; live32 stops at its first changed route key as before. R9: all existing LF-normalized checksum assertions remain unchanged.

Single revert checks: reverting the registry callbacks produces the local-lambda pickle error in the new restored pin; disabling `_release_rewritten_store_posting` leaves the visit alive and fails P1b. Logs: validation/batchfixA/revert-registry.log and revert-posting.log.

Assertion audit before the step 2 commit (verbatim):

```
No changed pre-existing assertions or forbidden test edits.
```

No ruling-based expectation change has been made. The only remaining requested decision is whether to correct the pre-existing closure assertion from two waits to three; changing the production bound to manufacture two waits would violate the no-new-threshold rule and would alter correct current behavior.

## Final verification

| Module | Run | Result |
| --- | ---: | --- |
| tests.test_control_client | 33 | 33 passed |
| tests.test_posted_effect_unobserved | 7 | 7 passed |
| tests.test_policy_structure | 7 | 7 passed |
| tests.test_pickup_pile_prompt_recorded | 12 | 12 passed |
| tests.test_live32_shop_leave | 5 | 5 passed |
| tests.test_ownership_s2a1_closure | 80 | 79 passed; 1 failed (pre-existing wait count) |
| tests.test_cli | 234 | 234 passed |
| tests.test_input_executor | 73 | 73 passed |
| tests.test_classA_observed_input | 30 | 30 passed |
| tests.test_shop_one_shot | 53 | 52 passed; 1 skipped |
| tests.test_storewhich_recorded | 2 | 2 passed |
| tests.test_storewhich2_recorded | 1 | 1 passed |
| tests.test_test_fakery_lint | 13 | 13 passed (captured tool output) |

Total: 550 run, 548 passed, 1 skipped, 1 unresolved pre-existing assertion. git diff --check passed. All tests ran one module per process, with the explicit module list in verify_modules.py.

Step 1 commit: c3046e04. Step 2 is the commit containing this final report and event.
