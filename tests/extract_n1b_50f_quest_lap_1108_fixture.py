"""Extract the fixture of n1-b life-348's quest-search lap (Angband 50F, RANDOM quest 40, 2026-11-08).

Input: the capture directory C:\\hengband-backups\\pdca\\captures\\n1b-348-50f-loop-1108 with
state-tail.jsonl.gz (the last boards), decisions-tail.jsonl.gz (the decisions of 15:28:56-15:42),
frames-50f-arrival.jsonl.gz (the boards of the floor's first 2,400 game turns, from the
snapshot generation of 15:34:54) and exploration-ledger.json (the floor's ledger at 15:47).
Output: the last board, the ledger, every decision row reduced to the replayed fields, and the
arrival boards reduced to turn, position and messages.
"""
import gzip
import json
import lzma
from pathlib import Path
import sys

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-50f-quest-lap-1108.json.xz"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position")


def _rows(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def extract(capture: Path) -> dict:
    decisions = _rows(capture / "decisions-tail.jsonl.gz")
    return {
        "board": _rows(capture / "state-tail.jsonl.gz")[-1],
        "ledger": json.loads((capture / "exploration-ledger.json").read_text(encoding="utf-8")),
        "map_memory": decisions[-1]["map_memory"],
        "decisions": [{name: row[name] for name in DECISION_FIELDS} for row in decisions],
        "arrival": [
            {"turn": row["turn"], "y": row["player"]["y"], "x": row["player"]["x"],
             "messages": row.get("messages", [])}
            for row in _rows(capture / "frames-50f-arrival.jsonl.gz")
            if row.get("type") == "player_turn"
        ],
    }


if __name__ == "__main__":
    pin = extract(Path(sys.argv[1]))
    payload = json.dumps(pin, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(pin["decisions"]), len(pin["arrival"]))
