"""Extract tests/fixtures/n1c-221-restart-climb-1123/.

Source: n1-c life-221 (Magic-Eater Lv46, *Destruction* absorbed) on 2026-11-23: the town-arrival
directory 20261123-151513.015930284-turn4505636 (the visit the 15:16:04 departure to the
Mountain's 50F ended; its first 2 journal rows) and the first boards of the process restarted at
15:17:34 on the Mountain's 50F (turn 4507414-4507417, snapshots-current.jsonl.gz lines 1974-1982,
the power_list board left out), xz-compressed.

    python tests/extract_n1c_221_restart_climb_1123_fixture.py <town-arrival directory> <boards.jsonl.gz>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-restart-climb-1123"
ROWS = 2


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    with gzip.open(sys.argv[2], "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    boards = [row for row in rows if row.get("type") == "player_turn"]
    assert boards[0]["turn"] == 4507414 and all(
        (board["floor"]["dungeon_id"], board["floor"]["level"]) == (14, 50) for board in boards)
    boards = [boards[0], next(board for board in boards if board["turn"] == 4507417)]
    (FIXTURE / "dungeon-boards.json.xz").write_bytes(
        lzma.compress(json.dumps(boards, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
