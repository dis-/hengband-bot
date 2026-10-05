"""Extract only the supplied retired log copies; never access live jsonlog."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path(r"C:\hengband-backups\state-logs\equip-alternation-20261005-1933")
TARGET = Path(__file__).parent / "fixtures/equipment-alternation-20261005.json.gz"


def main():
    rows = {}
    with gzip.open(SOURCE / "decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            sequence = row.get("decision_sequence", 0)
            if 4655 <= sequence <= 4660 and row.get("reason", "").startswith("equipment-transaction:"):
                rows[str(sequence)] = row
    turns = {row["turn"] for row in rows.values()}
    boards = {}
    with gzip.open(SOURCE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            board = json.loads(line)
            if board.get("turn") in turns and board.get("type") == "player_turn":
                boards[str(board["turn"])] = board
    data = {
        "provenance": {
            "source": str(SOURCE),
            "source_sha256": {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                              for name in ("decisions.jsonl.gz", "state.jsonl.gz")},
            "scope": "Exact decision rows and player_turn boards; no policy checkpoint was captured.",
        },
        "rows": rows, "boards": boards,
    }
    TARGET.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=True, sort_keys=True).encode(), mtime=0))
    print(f"Extracted {len(rows)} decisions, {len(boards)} boards; sha256={hashlib.sha256(TARGET.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
