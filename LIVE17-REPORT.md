Live17 step 1: exact pin/live difference (base 997ffddc)
=======================================================

The live decision dictionaries at src/hengbot/cli.py:4142 and :4258 contain
sequence, turn, reason, key and prompt_owner_handoff, but no observation.
_ExecutorInputPort.submit_operation (:2143) therefore constructs an Operation
with observation=None. The live15 pin at tests/test_live15_identify_source.py:57
instead supplies observation=state explicitly; its macro pin does likewise.

The executor does match the real row against gate 1: input_executor.py:1128
compares match.feature.rstrip().endswith(feature.rstrip()) for both languages.
The selector prefix and trailing spaces are harmless. Classification uses the
TCP screen response, not JSONL messages. The earlier 00:47 screen is byte-for-
byte the JSON fixture used by live15 (after JSON decoding); the 02:21 stderr
records the same selector and prompt. No separate 02:21 screen response was
captured, so we do not claim an unseen full response.

After this textual match, input_executor.py:1146-1158 binds the source to the
pre-operation inventory. With observation=None, old_items=(), old=None and
sources=[]; len(sources)!=1 breaks the continuation and :1240 reports unowned
item-source. This is a source-identity comparison failure, not a prompt-text
failure. Request 13 was accepted for r; no f was posted. The two actual posts
in the final session are the periodic knowledge operation (sequence 0) and r
(sequence 1); nothing indicates a transport ordering failure. The executor-
barrier telemetry in cli.py:2591 reports this terminal result rather than an
independent resume gate.

The replacement pin must omit observation just like both live call sites,
observe a ready board through the real executor, and call the production CLI
sender. Use the recorded 02:21 state and existing recorded chooser screens;
stop at the first divergent answer without inventing a recorded result.

Step 1 commit: b45d6610.

Step 2 fix and verification
===========================

cli.py:2146 now defaults the operation observation to executor.ready_board
when the live metadata omits it. This is the actual command-boundary board
already obtained by the executor before admission clears ready_board. Explicit
observations remain supported. No new persistent attributes or thresholds.
The existing identity checks, current-board source-letter binding, inventory-
only '/' switch, equipment binding, and observed result-viewer continuations
remain in force.

tests/test_live17_identify_observation.py calls the same outer production
sender as the live loop and uses its five decision fields, without injecting
observation. The pin first fails against unchanged 997ffddc production code:
both language settings stop after ['r'] with the exact unowned item-source
diagnostic. The single revert check temporarily restores only cli.py from
997ffddc, runs the final new module, and restores the fixed bytes in finally:
2 tests / 4 subtest failures, exit 1, all at that same source gate. Fixed code:
2 tests pass. Recorded cases post ['r', 'f', 'a'] then stop at phase=screen
because there is no recorded post-divergence result. Separate, explicitly
source-derived variants post ['r', 'f', '/', 'a', ' ', ESC] when an inventory
chooser intervenes, and ['r', 'f', 'a', ' ', ESC] for a direct equipment chooser;
both complete only after observing the result pages and command boundary.

Fixture provenance: live17-before-identify-state.json is the last nonempty
JSONL snapshot in the frozen 20261001-022129-stuck-prompt capture (3492 rows,
turn 513481), serialized with sorted keys and otherwise unmodified.
SHA256 f87fe6dc501f731294ae255c0c624f8d30dc0b0f8ddddd4c2b79059a488b092a.
The existing live15 source and live13 target fixtures are reused unchanged.

Authorized verification, one module/fixture per process:
- tests.test_live17_identify_observation: 2 passed (4 subcases).
- tests.test_live13_full_equipped_identify: 1 passed.
- tests.test_live15_identify_source: 2 passed, including live16 macro binding.
- tests.test_test_fakery_lint: 13 passed.
- first_divergence_s3_3.py stuck s33: OFF SHA c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5;
  4 OFF rows, no first divergence, trajectory_defect=null.
- first_divergence_s3_3.py withdraw s33: OFF SHA a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9;
  34 OFF rows, designed first divergence at index/sequence 20 to shop:travel,
  trajectory_defect=null. EXPECTED_FIRST was not changed.
- git diff --check passed. input_executor.py was not touched.
