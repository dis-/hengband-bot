"""Extract tests/fixtures/n1a-525-death-1115/.

Source: n1-a life-525's death of 2026-11-15 21:06:00 (ガラスの城 49F, Lv40 Warrior), the
incident capture 20261115-210559-player-death (its snapshot tail snapshots-current.jsonl.gz and
its decision log decision-tail.jsonl) copied to C:/hengband-backups/pdca/captures/n1a-525-death-1115/,
and the town-arrival checkpoint of the 21:05:39 visit (the departure of the fatal trip, turn
12038122), copied read-only from the viewing server's
jsonlog/town-arrival/20261115-210539.396042856-turn12038122/ to
C:/hengband-backups/pdca/n1a-525-rules-1115/cap/town-arrival/.  The journal of that visit ends at
its Recall (63 rows), so the dungeon decisions were replayed from the checkpoint over the snapshot
tail (each decision's board the record matching the decision log's turn and position, its inputs
the records since the previous board) with .scratch/replay_dungeon.py; every one of the 63 town
rows and the 135 dungeon decisions matched the record.  ``policy.pkl.xz`` is that policy before
decision 23980's inputs; ``boards.jsonl.xz`` holds decisions 23980-24023 (the decision log's key
and reason) with their inputs.

    PYTHONPATH="src;tests" python tests/extract_n1a_525_death_1115_fixture.py
"""
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET

REPLAY = Path(__file__).resolve().parent.parent / ".scratch" / "dungeon-before-23980"
TARGET = Path(__file__).with_name("fixtures") / "n1a-525-death-1115"


def board_of(record: dict, row: dict) -> bool:
    player = record.get("player") or {}
    return (record.get("type") == "player_turn" and record.get("turn") == row["turn"]
            and (player.get("y"), player.get("x"))
            == (row["position"]["y"], row["position"]["x"]))


def boards() -> list[dict]:
    ring = [json.loads(line) for line in
            (REPLAY / "ring.jsonl").read_text(encoding="utf-8").splitlines() if line]
    rows = [json.loads(line) for line in
            (REPLAY / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    out, index = [], -1
    for number, row in enumerate(rows):
        board = index + 1
        while not board_of(ring[board], row):
            board += 1
        following = rows[number + 1] if number + 1 < len(rows) else None
        while (board + 1 < len(ring) and board_of(ring[board + 1], row)
               and not (following is not None and board_of(ring[board + 1], following))):
            board += 1
        out.append({"decision": row, "inputs": ring[index + 1:board + 1]})
        index = board
    return out


if __name__ == "__main__":
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "policy.pkl.xz").write_bytes(
        lzma.compress((REPLAY / "policy.pkl").read_bytes(), preset=PRESET))
    (TARGET / "boards.jsonl.xz").write_bytes(lzma.compress("".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in boards()).encode("utf-8"),
        preset=PRESET))
    for path in sorted(TARGET.iterdir()):
        print(path.name, path.stat().st_size)
