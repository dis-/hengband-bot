"""Extract tests/fixtures/n1b-411-finale-initiative-1121/boards.json.xz.

Source: n1-b life-411's 99F battle of 2026-11-21 13:58 (bot main b9efeeca0), the incident capture
n1b-411-20261121-135909-loop-detected's state.jsonl.gz: three boards of the stand at (8,76) on
Oberon's row, Oberon at (8,60) -- turn 11355723 (the stand's first melt), 11355745 (the first
hold: one wall left, at (8,61)) and 11355767 (the melt of that last wall after ten holds; the next
board shows the player touched and leaving by Teleportation).

    python tests/extract_n1b_411_finale_initiative_1121_fixture.py <state.jsonl.gz>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-finale-initiative-1121"
TURNS = (11355723, 11355745, 11355767)


if __name__ == "__main__":
    with gzip.open(sys.argv[1], "rt", encoding="utf-8") as stream:
        boards = {row["turn"]: row for row in map(json.loads, stream) if "grid_map" in row}
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        [boards[turn] for turn in TURNS], ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
