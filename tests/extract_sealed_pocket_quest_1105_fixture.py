"""Extract the sealed-pocket quest floor fixture of n1-c life-140 (2026-11-05 05:41).

Input: a capture directory (state.jsonl.gz, bot-decisions.jsonl.gz) of the last
restart on the floor.  Output: the state rows from that session's first board to
the stop board and the session's decision rows, reduced to the replayed fields.
"""
import gzip
import lzma
import json
from pathlib import Path
import sys

OUTPUT = Path(__file__).with_name("fixtures") / "sealed-pocket-quest-1105.json.xz"
FIRST_TURN = 3970882
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position")


def extract(capture: Path) -> dict:
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8", errors="surrogateescape") as stream:
        lines = [line for line in stream if json.loads(line)["turn"] >= FIRST_TURN]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8", errors="surrogateescape") as stream:
        rows = [json.loads(line) for line in stream]
    session = max(index for index, row in enumerate(rows) if row.get("kind") == "session-start")
    decisions = [
        {field: row[field] for field in DECISION_FIELDS} for row in rows[session + 1:]
    ]
    return {"lines": lines, "decisions": decisions}


if __name__ == "__main__":
    pin = extract(Path(sys.argv[1]))
    payload = json.dumps(pin, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(pin["lines"]), len(pin["decisions"]))
