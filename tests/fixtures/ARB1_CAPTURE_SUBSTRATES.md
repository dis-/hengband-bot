# ARB-1 capture substrates

The five uncompressed incident files in this directory are byte-for-byte copies
of decision-log rows. They preserve reason attribution and decision telemetry,
but they do not contain emitter snapshots and therefore cannot be replayed
through `HengbotPolicy.choose_key`.

- `incident-equipment-abandon-loop-20260822.jsonl`: decision-log rows only.
- `incident-alchemist-repetition-20260823.jsonl`: decision-log rows only.
- `incident-launcher-repetition-20260823.jsonl`: decision-log rows only.
- `incident-calibration-entry-await-20260823.jsonl`: decision-log rows only.
- `incident-magic-abandon-cycle-20260823.jsonl`: decision-log rows only.

`incident-postlevel-repetition-turn-1006064.jsonl.gz` contains the one emitter
snapshot at turn 1006064 from the retained incident snapshot ring. It is a real
public-policy replay substrate. The gzip stream is canonicalized with an empty
stored filename and modification time zero.
