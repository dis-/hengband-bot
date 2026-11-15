"""Extract tests/fixtures/n1b-397-deep-stuck-1115.jsonl.gz.

Source: n1-b life-397 (Lv50 Magic-Eater), Angband 79F, 2026-11-15 10:47:34-10:48:02, the
automatic incident capture of its death (20261115-104802-player-death), copied read-only from
the viewing server to C:/hengband-backups/pdca/n1b-397-death-1115.  Kept: the latest ~f skill
list the process read, the 79F boards from the arrival by the up stairs (turn 5734372) to the
last decision (turn 5735278, stuck:destroyed-circle-teleport 'rh'), and the recorded
(turn, decision, reason, key) of the same window.

    python tests/extract_n1b_397_deep_stuck_1115_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/n1b-397-death-1115/20261115-104802-player-death")
GENERATIONS = ("snapshots-20261115-104645-828586.jsonl.gz", "snapshots-current.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1b-397-deep-stuck-1115.jsonl.gz"
LAST = 5735278


def main() -> None:
    skill, boards = None, []
    for name in GENERATIONS:
        with gzip.open(CAPTURE / "snapshots" / name, "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                board = json.loads(line)
                if (board.get("knowledge") or {}).get("category") == "skill_exp":
                    skill = board
                elif board.get("type") == "player_turn" and board["turn"] <= LAST:
                    boards.append(board)
    # The 79F visit: the boards after the last one on another floor.
    first = max(index for index, board in enumerate(boards) if board["floor"]["level"] != 79) + 1
    boards = boards[first:]
    turns = {board["turn"] for board in boards}
    rows = [{"role": "skill-knowledge", "board": skill}]
    rows += [{"role": "board", "board": board} for board in boards]
    with open(CAPTURE / "decision-tail.jsonl", encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # the tail's first line is cut
            if record.get("turn") in turns or boards[0]["turn"] <= record.get("turn", 0) <= LAST:
                rows.append({"role": "decision", "decision": {
                    key: record[key] for key in ("turn", "decision_sequence", "reason", "key")}})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows), boards[0]["turn"], boards[-1]["turn"])


if __name__ == "__main__":
    main()
