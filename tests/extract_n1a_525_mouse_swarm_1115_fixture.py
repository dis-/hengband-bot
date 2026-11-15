"""Extract tests/fixtures/n1a-525-mouse-swarm-1115/.

Source: n1-a life-525's stop of 2026-11-15 16:54:06 (loop-detected, Yeek cave 1F, Lv37
Warrior, build 25d9cc382), the incident capture 20261115-165404-loop-detected copied
read-only from the viewing server to C:/hengband-backups/pdca/n1a-525-loop2-1115/inc/, and
the stop capture 20261115-165406-loop-detected (its decision log).  The journal of the
16:52:21 town visit ends at its descent (68 rows), so the dungeon decisions were replayed
from the town-arrival checkpoint over the snapshot tail (each decision's board the record
matching the decision log's turn and position, its inputs the records since the previous
board) with .scratch/replay_dungeon.py; every one of the 741 decisions matched the record.
``policy.pkl.xz`` is that policy before decision 2508's inputs; ``boards.jsonl.xz`` holds
decisions 2508-2594 (the decision log's key, reason and equipment-mutation report) with
their inputs.

    PYTHONPATH="src;tests" python tests/extract_n1a_525_mouse_swarm_1115_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET

REPLAY = Path(__file__).resolve().parent.parent / ".scratch" / "dungeon-before-2508"
DECISION_LOG = Path("C:/hengband-backups/pdca/n1a-525-loop2-1115/20261115-165406-loop-detected"
                    "/bot-decisions.jsonl.gz")
TARGET = Path(__file__).with_name("fixtures") / "n1a-525-mouse-swarm-1115"


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
    with gzip.open(DECISION_LOG, "rt", encoding="utf-8") as stream:
        reports = {row["decision_sequence"]: row.get("equipment_mutation_report")
                   for row in map(json.loads, stream) if row.get("reason") != "loop-detected"}
    out, index = [], -1
    for number, row in enumerate(rows):
        board = index + 1
        while not board_of(ring[board], row):
            board += 1
        following = rows[number + 1] if number + 1 < len(rows) else None
        while (board + 1 < len(ring) and board_of(ring[board + 1], row)
               and not (following is not None and board_of(ring[board + 1], following))):
            board += 1
        out.append({"decision": dict(row, report=reports.get(row["decision_sequence"])),
                    "inputs": ring[index + 1:board + 1]})
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
