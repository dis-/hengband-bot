"""Extract tests/fixtures/n1b-405-me-destruction-1115/.

Source: n1-b life-405 (Magic-Eater Lv42), copied read-only from the viewing server's
jsonlog/ to C:/hengband-backups/pdca/captures/n1b-405-me-destruction-1115/:

* ``town/``: the town-arrival checkpoint of 2026-11-15 23:18:10 (turn 2765944;
  town-arrival/20261115-231810.817550464-turn2765944), its first ``TOWN_ROWS`` journal rows
  (row 17 the recall read) and the sidecar files, xz-compressed
  (tests/support/town_arrival_fixture.py);
* ``castle/``: the town-arrival checkpoint of 23:21:22 (turn 2775795;
  town-arrival/20261115-232122.196279197-turn2775795), the policy the Castle dive went on with
  (the journal's first row only: the dive's boards are not in it);
* ``cycle-boards.jsonl.xz``: seven state lines of the 49F-50F-49F cycle from
  jsonlog/snapshots/snapshots-20261115-233110-41fb42.jsonl.gz (turns 2799879 49F at the down
  stair, 2799880 x2 the 50F arrival, 2799881 x3 the 49F arrival and its power list, 2801676
  49F at the same stair again; cycle-boards.jsonl in the capture directory).

    python tests/extract_n1b_405_me_destruction_1115_fixture.py <capture directory>
"""
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-405-me-destruction-1115"
TOWN_VISIT = "town-arrival/20261115-231810.817550464-turn2765944"
CASTLE_VISIT = "town-arrival/20261115-232122.196279197-turn2775795"
TOWN_ROWS = 21
LEFT_OUT = frozenset({"_loadout_report_path"})


if __name__ == "__main__":
    capture = Path(sys.argv[1])
    extract(capture / TOWN_VISIT, FIXTURE / "town", TOWN_ROWS, LEFT_OUT)
    extract(capture / CASTLE_VISIT, FIXTURE / "castle", 1, LEFT_OUT)
    (FIXTURE / "cycle-boards.jsonl.xz").write_bytes(
        lzma.compress((capture / "cycle-boards.jsonl").read_bytes(), preset=PRESET))
    print(sorted((str(path.relative_to(FIXTURE)), path.stat().st_size)
                 for path in FIXTURE.rglob("*") if path.is_file()))
