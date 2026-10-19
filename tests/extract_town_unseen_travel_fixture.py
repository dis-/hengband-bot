"""Freeze the c4-a life-014 restart rows behind the unseen-grid travel stop.

Source: state-logs/c4a-loops-20261016/20261019-103907-no-key-exhausted
(state.jsonl.gz rows 93..101: the restarted process's first three decision
inputs, unchanged) plus the recorded decisions 0..2 of that process.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

FIRST_ROW, LAST_ROW = 93, 101


def extract(capture):
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as source:
        rows = source.read().splitlines(keepends=True)[FIRST_ROW:LAST_ROW + 1]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as source:
        decisions = [row for row in map(json.loads, source)
                     if row.get("decision_sequence") in (0, 1, 2)
                     and row.get("turn") == 1068208]
    body = "".join(rows).encode("utf-8")
    target = Path(__file__).parent / "fixtures" / "town-unseen-travel-20261019.jsonl.gz"
    target.write_bytes(gzip.compress(body, mtime=0))
    recorded = [{name: row[name] for name in ("decision_sequence", "turn", "key", "reason")}
                for row in decisions]
    target.with_suffix(".decisions.json").write_text(
        json.dumps(recorded, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    extract(Path(sys.argv[1]))
