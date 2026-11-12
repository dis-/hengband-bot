"""Extract n1-c life-205's RANDOM quest 42 boards (Angband 76F, 2026-11-13 01:31).

Inputs: a slice of the life's jsonlog/snapshots (snapshots-20261113-012854-8d557b.jsonl.gz and
snapshots-current.jsonl.gz, gzip; the player_turn rows of turns 2321030-2321145 are enough) and
the life's bot-decisions.jsonl rows of the same turns.
Output: the player_turn rows of turns 2321066 (decision 2450, after the emergency teleport to
[14,132]) through 2321144 (decision 2470, return:wait-recall), the first row of each turn, and
the decisions' (sequence, turn, reason, key, hp) of those turns.
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-205-rq-t1-target-1113.json.xz"
FIRST, LAST = 2321066, 2321144


def extract(snapshots: Path, decisions: Path) -> dict:
    rows = {}
    with gzip.open(snapshots, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST:
                rows.setdefault(row["turn"], row)
    recorded = []
    for line in decisions.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if FIRST <= row["turn"] <= LAST:
            recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                             "reason": row["reason"], "key": row["key"],
                             "hp": row["player"]["hp"]})
    recorded.sort(key=lambda row: row["sequence"])
    return {"rows": [rows[turn] for turn in sorted(rows)], "decisions": recorded}


if __name__ == "__main__":
    payload = extract(Path(sys.argv[1]), Path(sys.argv[2]))
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(text.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(payload["rows"]), len(payload["decisions"]))
