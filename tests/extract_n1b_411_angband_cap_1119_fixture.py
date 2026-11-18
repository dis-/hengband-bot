"""Extract tests/fixtures/n1b-411-angband-cap-1119/.

Source: n1-b life-411's town-arrival checkpoint of 2026-11-19 00:54:41 (turn 7813713,
~/hengbot-soak/n1-b/life-411/jsonlog/town-arrival/20261119-005441.269976523-turn7813713, copied
read-only): the arrival policy (Angband the guardian bounce valve's alternate, its recall depth 99),
the visit's 81 journal rows (row 29 the Word of Recall read to Angband, town:recall-to-angband; rows 30-80 its wait) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).  ``angband-99f-board.json.xz`` is the next dive's arrival
board (~/hengbot-soak/n1-b/life-411/state.jsonl line 5345, turn 7814111: Angband 99F).

    python tests/extract_n1b_411_angband_cap_1119_fixture.py <town-arrival directory> <99F board line>
"""
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-angband-cap-1119"
ROWS = 81


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    (FIXTURE / "angband-99f-board.json.xz").write_bytes(
        lzma.compress(Path(sys.argv[2]).read_bytes().strip(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
