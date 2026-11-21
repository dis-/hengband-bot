"""Extract tests/fixtures/n1b-413-rearm-digger-loop-1121/boards.json.xz.

Source: n1-b life-413's stall of 2026-11-21 19:02:06 (stall:floor-dwell:melee:rearm-empty-hand,
Angband 12F, bot main db36f1744), the incident capture
n1b-413-20261121-190207-stall-floor-dwell-melee-rearm-empty-hand's state.jsonl.gz: the boards of
turn 674796 (the Long Sword back in the main hand, the next decision stuck:walled-off-wield-digger
'ta') and 674802 (the hand emptied by that 'ta', the next decision melee:rearm-empty-hand 'wq').

    python tests/extract_n1b_413_rearm_digger_loop_1121_fixture.py <state.jsonl.gz>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-rearm-digger-loop-1121"
TURNS = (674796, 674802)


if __name__ == "__main__":
    with gzip.open(sys.argv[1], "rt", encoding="utf-8") as stream:
        boards = {row["turn"]: row for row in map(json.loads, stream) if "grid_map" in row}
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        [boards[turn] for turn in TURNS], ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
