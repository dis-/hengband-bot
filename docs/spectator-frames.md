# Spectator frames (bot side)

With `--spectate-file PATH`, posted policy decisions are also appended to
`spectate-frames.jsonl` in PATH's parent directory. Each UTF-8 JSONL row has the
same screen, colours, panels, key (macro notation), reason, decision_sequence
and Unix time as the snapshot projection, plus `frame` (integer, starting at 1).
The pre-action screen is acquired before the action's response deadline; the
row is committed only when the policy action is actually posted. Refused
posts, executor continuations, prompt answers and recovery keys add no frames.
No-key decisions still refresh the compatibility snapshot when due.

`spectate.json` retains atomic replacement and its 0.25-second throttle. The
frames are unthrottled. Frame numbering resumes from the newest complete row
on restart. When adding a row would exceed 16 MiB, the writer atomically
replaces the file with the newest complete rows fitting approximately 8 MiB,
including that row. A single row larger than 16 MiB is rejected. On rotation
failure it drops that frame rather than growing the file. The consumer must
reopen after replacement, identify rows by frame number, and skip frames it
already played. A torn final row from a failed append is repaired on the next
write. Storage and colour-request errors are caught and rate limited on stderr;
colour failure falls back to the executor's existing screen.

`--spectate-max-backlog N` defaults to 0 (disabled, no acknowledgement reads).
For N > 0 the bot reads sibling `spectate-played.json` before each policy action:

```json
{"frame": 123, "time": 1792930000.0}
```

If `last_written_frame - frame >= N`, it polls every 0.05 seconds until the
backlog falls below N. The current action has not added its frame yet. The
consumer must keep `time` fresh even while stalled. A missing, unreadable,
invalid or more than 10-second-old acknowledgement releases the bot; invalid
negative/future frame numbers or non-finite/future timestamps also fail open.
N=20 represents five seconds at the consumer's planned 0.25 seconds per frame.
The bot does not impose playback cadence. Existing `--min-action-seconds`
remains independent; viewers can omit it to wait only on backlog.

Intentional waits cancel and re-arm the decision watchdog, are excluded from
decision timing, extend the activity timestamp, and precede response deadlines.
The test suite uses injected clocks and temporary files. Offline cost probe:
`PYTHONPATH=src python scripts/perf_spectator_frames.py --iterations 300`.
Per-pin behavioural revert proofs: `python scripts/check_spectator_frames_pins.py`.
The probe only contacts its own fixture TCP server, never a running game.
