"""Extract the quest-search sealed pocket fixture of n1-a life-496 (2026-11-08 01:36-03:35).

Input: the three capture directories of ``stall:floor-dwell:quest-search:loop`` (02:06:57,
02:38:00, 03:09:02), each with state.jsonl.gz and bot-decisions.jsonl.gz.  Output: the last
board of the first capture (the stop board) and every decision row of the three, reduced to
the replayed fields.
"""
import gzip
import json
import lzma
from pathlib import Path
import sys

OUTPUT = Path(__file__).with_name("fixtures") / "quest-sealed-pocket-1108.json.xz"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position")


def _rows(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream]


def extract(captures: list) -> dict:
    board = _rows(captures[0] / "state.jsonl.gz")[-1]
    sessions = []
    for capture in captures:
        rows = _rows(capture / "bot-decisions.jsonl.gz")
        sessions.append({
            "capture": capture.name,
            "map_memory": rows[-1]["map_memory"],
            "decisions": [{field: row[field] for field in DECISION_FIELDS} for row in rows],
        })
    return {"board": board, "sessions": sessions}


if __name__ == "__main__":
    pin = extract([Path(each) for each in sys.argv[1:]])
    payload = json.dumps(pin, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, sum(len(each["decisions"]) for each in pin["sessions"]))
