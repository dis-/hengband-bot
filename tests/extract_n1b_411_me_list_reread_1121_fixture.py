"""Extract tests/fixtures/n1b-411-me-list-reread-1121/.

Source: n1-b life-411 (Magic-Eater Lv50, *Destruction* absorbed 99/99) on 2026-11-21: the
town-arrival directory 20261121-112608.607288878-turn11335544 of the process started at 11:26
(its first 8 journal rows: rows 4-6 browse the staff, wand and rod lists, rows 5-7 show them) and
three Angband 95F boards of the same life from the state log tail 12:02-12:03
(state-tail-1203.jsonl.gz), xz-compressed.

    python tests/extract_n1b_411_me_list_reread_1121_fixture.py <town-arrival directory> <state tail>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-me-list-reread-1121"
ROWS = 8
BOARDS = (0, 150, 299)


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    with gzip.open(sys.argv[2], "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    boards = [rows[index] for index in BOARDS]
    assert all(board["floor"]["level"] == 95 and board.get("type") != "power_list" for board in boards)
    (FIXTURE / "dungeon-boards.json.xz").write_bytes(
        lzma.compress(json.dumps(boards, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
