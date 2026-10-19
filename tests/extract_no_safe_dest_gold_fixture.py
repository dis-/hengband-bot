"""Extract the no-safe-destination-above-the-gold-target pin (c4-a life-014).

Capture 2026-10-19 23:16:44 (bot dcf664fa, restarted process): the town
board with gold 20,238 refused every recall landing and stopped with
``town:blocked:depth-gate:destination-26:missing-resist_acid,resist_elec``.
Keeps the raw state.jsonl lines FIRST_LINE..LAST_LINE (the restarted
process's boards for decision rows 0..6; the lines before FIRST_LINE are the
previous process's tail at the same turn) and the recorded decision metadata
(sequence, turn, key, reason, drained record count) of rows 0..6.  Raw lines
are stored unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\hengband-backups\state-logs\c4a-loops-20261016")
CAPTURE = "20261019-231644-town-blocked-owner-retired-burst"
FIRST_LINE = 72
LAST_LINE = 83
LAST_DECISION = 6


def main(target: Path) -> None:
    with gzip.open(ROOT / CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        lines = list(stream)
    with gzip.open(ROOT / CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    rows = [row for row in rows if "decision_sequence" in row]
    start = max(index for index, row in enumerate(rows) if row["decision_sequence"] == 0)
    decisions = [
        {
            "decision_sequence": row["decision_sequence"], "turn": row["turn"],
            "key": row["key"], "reason": row["reason"],
            "drained": int((row.get("timing") or {}).get("jsonl_drain_records") or 0),
        }
        for row in rows[start:start + LAST_DECISION + 1]
    ]
    out = {"source": CAPTURE, "first_line": FIRST_LINE,
           "lines": lines[FIRST_LINE:LAST_LINE + 1], "decisions": decisions}
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
