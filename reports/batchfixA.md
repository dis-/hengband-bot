# batchfixA reproduction (base a4e51bf9)

Each invocation runs one authorized test module or named test, never a suite runner. No live bot/game/worktree was changed.

| Test | First divergence | Cause |
| --- | --- | --- |
| control_client four routing/shadow pins | CLI exits 75 before mocked transport, versus 0/3 | cli.py:3130 process-global Windows port-1 mutex collides with another test process. `_acquire_control_owner` dates to 6f842037; no change in d7429e7b..HEAD. Re-run DisabledCliPinTest alone: 9/9 pass. |
| posted_effect P1b | ESC/home:queue-withdraw-identify-staff-reserve versus historical Eh/survival substitution | c989ea1a, policy_town.py store-context preservation; already fails with d7429e7b production. Restore the historical substitution only at the test input seam; keep production store protection. |
| policy_structure foreign cases | ProductionHarness is bound as a foreign TestCase in three modules | 28ee9a9a (Class A), 073fa4ba (storewhich), 3b0d6c02 (storewhich2). Import the harness module instead of its TestCase. |
| pickup historical atomic macro | SENT versus historical TERMINAL; compiler stages g/a | 28ee9a9a cli.py:2155 compile_observed_input. Already fails on d7429e7b. Supply the explicitly historical atomic operation through the executor seam, preserving all outcome assertions and production compilation. |
| live32 two shadow/pickle pins | pickle.dumps raises local-lambda AttributeError | policy_town.py:2973 registry caches local closures (introduced by 65977ec0, later split by afc0a29a). d7429e7b passes; identify which new supplier evaluation reaches this cache. Replace closures with serializable callable code. |
| ownership_s2a1 posted closure | three barrier-provenance-missing rows versus two | already fails on d7429e7b. Recorded attachment: sequence=5429, posted=5428; choose_key increments then test increments: 5430/5432/5434 wait, 5436 releases at existing STORE_STUCK_LIMIT=8. ef93a790 added the two-row assertion; 6601d170 changed store bound to 8. Do not change the assertion or tune the production bound without an applicable ruling. |

Historical baseline commands/results are in validation/batchfixA/d7429e7b-*.log. The common brief's claim that all these pins passed on d7429e7b does not hold for P1b, historical atomic pickup, or the closure wait count in this checkout.
