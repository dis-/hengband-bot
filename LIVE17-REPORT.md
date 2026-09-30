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
