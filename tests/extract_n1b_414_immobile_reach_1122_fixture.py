"""Extract tests/fixtures/n1b-414-immobile-reach-1122/boards.json.xz.

Source: n1-b life-414 (Orc cave 22F), the stop of 2026-11-22 07:26:36
(20261122-072634-stall-floor-dwell-explore).  The bot process started at 06:51:33 (build
cc0ba74d6) on the game's reload of the floor; its boards are in the life's snapshot log
jsonlog/snapshots/snapshots-20261122-072923-e14f83.jsonl.gz.  Two of them are pinned: line 25
(turn 1104257, the absorbed Detect Evil's board, which showed the 21 死体の塊) and line 60
(turn 1104535, a later explore board, 2.0 s a decision on the recorded run).

    python tests/extract_n1b_414_immobile_reach_1122_fixture.py <snapshots.jsonl.gz>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]

from support.town_arrival_fixture import PRESET  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-414-immobile-reach-1122"
LINES = (25, 60)


if __name__ == "__main__":
    boards = []
    with gzip.open(sys.argv[1], "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if number in LINES:
                boards.append(json.loads(line))
    assert [board["turn"] for board in boards] == [1104257, 1104535], [b["turn"] for b in boards]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(
        json.dumps(boards, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
