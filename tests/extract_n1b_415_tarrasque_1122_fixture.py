"""Extract n1-b life-415's arrival on Angband 76F, RANDOM quest 42 (2026-11-22 17:08).

Source (the investigation copy, read-only): C:/hengband-backups/pdca/n1b-415-death/
state-tail.jsonl (the live state tail: player_turn rows) and bot-decisions-tail.jsonl (the
decision rows; its first line is cut by the tail and skipped).
Output: tests/fixtures/n1b-415-tarrasque-1122.json.xz -- the player_turn rows of turns 2124038
(decision 8017, the descent from 75F) through 2124107 (decision 8037, the death board), every row
of each turn (the arrival turn 2124039 has two), and the decisions' (sequence, turn, reason, key,
hp) of those turns.

    python tests/extract_n1b_415_tarrasque_1122_fixture.py
"""
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/n1b-415-death")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-415-tarrasque-1122.json.xz"
FIRST, LAST = 2124038, 2124107


def _rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # the tail's first line, cut
    return rows


def extract() -> dict:
    boards = [row for row in _rows(ROOT / "state-tail.jsonl")
              if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST]
    decisions = sorted(
        ({"sequence": row["decision_sequence"], "turn": row["turn"], "reason": row["reason"],
          "key": row["key"], "hp": row["player"]["hp"]}
         for row in _rows(ROOT / "bot-decisions-tail.jsonl")
         if "reason" in row and FIRST <= row["turn"] <= LAST),
        key=lambda row: row["sequence"])
    return {"rows": boards, "decisions": decisions}


if __name__ == "__main__":
    payload = extract()
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(text.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(payload["rows"]), len(payload["decisions"]))
