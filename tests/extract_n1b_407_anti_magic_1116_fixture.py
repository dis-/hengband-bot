"""Extract tests/fixtures/n1b-407-anti-magic-1116.jsonl.gz.

Source: n1-b life-407 (Lv50 Magic-Eater), Castle 64F, 2026-11-16, the automatic
loop-detected captures 20261116-164955 and 20261116-165012, copied read-only from the
viewing server to C:/hengband-backups/pdca/n1b-407-loop-1116.  Kept: the ~f skill list,
the boards of the loot alternation around the Broad Axe at (15,23) (turns 5747574-5747594)
and of the fight at (15,23) (turns 5747721-5747742), the first board of each turn (the
second one of a turn is the board the refused ``m`` left), and the recorded
(turn, decision, reason, key) of the same windows from either capture's decision tail.

    python tests/extract_n1b_407_anti_magic_1116_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURES = Path("C:/hengband-backups/pdca/n1b-407-loop-1116")
TARGET = Path(__file__).with_name("fixtures") / "n1b-407-anti-magic-1116.jsonl.gz"
WINDOWS = (
    ("loot", "20261116-164955-loop-detected", 5747574, 5747594),
    ("fight", "20261116-165012-loop-detected", 5747721, 5747742),
)


def _lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    rows, skill = [], None
    for window, capture, first, last in WINDOWS:
        seen = set()
        for board in _lines(CAPTURES / capture / "state.jsonl.gz"):
            if (board.get("knowledge") or {}).get("category") == "skill_exp":
                skill = board
            elif (board.get("type") == "player_turn" and first <= board["turn"] <= last
                  and board["turn"] not in seen):
                seen.add(board["turn"])
                rows.append({"role": "board", "window": window, "board": board})
        # The fight's decisions are in the earlier capture's tail (the later one starts at
        # its restart): every capture is read, each record once.
        records = {}
        for _window, other, _first, _last in WINDOWS:
            for record in _lines(CAPTURES / other / "bot-decisions.jsonl.gz"):
                if first <= (record.get("turn") or 0) <= last:
                    kept = {key: record[key] for key in ("turn", "decision_sequence", "reason", "key")}
                    records[(record["time"], kept["decision_sequence"])] = kept
        rows += [{"role": "decision", "window": window, "decision": records[key]}
                 for key in sorted(records)]
    rows.insert(0, {"role": "skill-knowledge", "board": skill})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
