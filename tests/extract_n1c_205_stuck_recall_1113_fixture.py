"""Extract tests/fixtures/n1c-205-stuck-recall-1113.jsonl.gz.

Source: n1-c life-205 (Lv38 Magic-Eater), dungeon 12 49F, 2026-11-12 22:10:32-22:13:04,
copied read-only from the viewing server (jsonlog/snapshots and jsonlog/bot-decisions.jsonl.3)
to C:/hengband-backups/pdca/captures/n1c-205-stuck-recall-1113: the visit's boards and its
decision records.  Kept: the ~f skill list the process read, the boards of turns
2023470-2023535 (decisions 5066-5082; 5082 read Recall, stuck:recall-escape) and the recorded
(turn, decision, reason, key) of the same window.

    python tests/extract_n1c_205_stuck_recall_1113_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-205-stuck-recall-1113")
TARGET = Path(__file__).with_name("fixtures") / "n1c-205-stuck-recall-1113.jsonl.gz"
FIRST, LAST = 2023470, 2023535


def main() -> None:
    rows = []
    with gzip.open(CAPTURE / "221032_12-49-0.snapshots.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            board = json.loads(line)
            if (board.get("knowledge") or {}).get("category") == "skill_exp":
                if not any(row["role"] == "skill-knowledge" for row in rows):
                    rows.append({"role": "skill-knowledge", "board": board})
            elif board.get("type") == "player_turn" and FIRST <= board["turn"] <= LAST:
                rows.append({"role": "board", "board": board})
    with gzip.open(CAPTURE / "221032_12-49-0.decisions.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            if FIRST <= record["turn"] <= LAST:
                rows.append({"role": "decision", "decision": {
                    key: record[key] for key in ("turn", "decision_sequence", "reason", "key")}})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
