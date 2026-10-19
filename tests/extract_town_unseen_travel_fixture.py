"""Freeze the c4-a life-014 rows behind the unseen-grid travel stops (#79).

usage: extract_town_unseen_travel_fixture.py <capture-directory> [20261019|111025]

20261019: state-logs/c4a-loops-20261016/20261019-103907-no-key-exhausted,
  state.jsonl.gz rows 93..101 (the restarted process's first three decision
  inputs, unchanged) plus its recorded decisions 0..2.
111025: state-logs/c4a-loops-20261016/20261019-111025-no-key-exhausted,
  state.jsonl.gz rows 0..11 (the whole restarted process: decisions 0..7,
  unchanged) plus its recorded decisions 0..7.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

SOURCES = {
    "20261019": (93, 101, range(0, 3), 1068208),
    "111025": (0, 11, range(0, 8), None),
}


def extract(capture, name="20261019"):
    first_row, last_row, sequences, turn = SOURCES[name]
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as source:
        rows = source.read().splitlines(keepends=True)[first_row:last_row + 1]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as source:
        decisions = [row for row in map(json.loads, source)
                     if row.get("decision_sequence") in sequences
                     and (turn is None or row.get("turn") == turn)]
    # The log holds earlier processes too; keep the restarted process's rows.
    decisions = decisions[-len(sequences):]
    body = "".join(rows).encode("utf-8")
    target = Path(__file__).parent / "fixtures" / f"town-unseen-travel-{name}.jsonl.gz"
    target.write_bytes(gzip.compress(body, mtime=0))
    recorded = [{name: row[name] for name in ("decision_sequence", "turn", "key", "reason")}
                for row in decisions]
    target.with_suffix(".decisions.json").write_text(
        json.dumps(recorded, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    extract(Path(sys.argv[1]), *sys.argv[2:3])
