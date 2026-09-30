Live15 cause (step 1)

policy_equipment.py:2513-2525 composes rfa as a plan with source and target
gates, rather than posting all three keys. cli.py:2537 selects only one
localized prompt using prompt_japanese; cli.py:2562 passes that single string
to the executor. With English selected and the recorded Japanese read-scroll
screen, input_executor.py:1119-1131 rejects the source continuation. Only r
has been accepted; cli.py:2579 reports executor-barrier and the remaining fa
is dropped. Live13 starts at rf with a manually constructed target continuation,
so it bypasses the failing production source gate.

The fix will retain both authoritative localized prompt alternatives at the
executor boundary and pin the production CLI adapter with both recorded screens.

Step 2 completed

- cli.py:2557-2561 retains both localized gate features for full-equipped
  identify. The existing producer plan remains rfa; the executor posts only r,
  observes the source, binds the scroll identity to current state, posts f,
  observes the target, binds the equipped identity, then posts a.
- input_executor.py:1161-1169 requires the bound source letter to be visible
  and requires an advertised '/' before switching an inventory target chooser
  to equipment. No new persistent attributes or thresholds were introduced.
- tests/test_live15_identify_source.py:29 drives both recorded screens through
  _send_prompt_gated_decision_key and _ExecutorInputPort, with both language
  settings. It deliberately stops after a: no post-divergence result was captured.
  Existing result-viewer ownership remains in input_executor.py:1104-1109.
- New recorded fixture: tests/fixtures/live-screens/live15-read-scroll-prompt.json,
  copied byte-for-byte from live-screen-20261001-0047-read-scroll-prompt.json.
- Verification: live15 1 test (two language cases) passed; live13 1 passed;
  test_test_fakery_lint 13 passed. test_input_executor: 72 passed, 1 error due to
  missing pre-existing jsonlog/incident-20260919-2230-recall-depth-prompt.jsonl.
  No forbidden modules, suites, or gate scripts were run.
- Single revert check: restoring only cli.py to step-1 HEAD makes the English
  setting fail with accepted=['r'] and the recorded unowned item-source stop;
  the Japanese case passes. Fixed bytes were restored and live15 passed again.
- The incident logs do not record prompt_japanese. The language mismatch is
  inferred from the rejecting continuation and reproduced with False; startup
  cli.py:3153 takes that setting from the info response. The fix removes this
  dependency for this operation.
- Step 1 commit: f290e941. Step 2 commit: the commit containing this section.
