"""Extract tests/fixtures/n1b-416-light-flipflop-1122/.

n1-b life-416 (Lv7 Magic-Eater, new character, build bot-437d85905) stopped in town on
2026-11-22 17:12:12 with ``town:blocked:equipment-slot-flipflop:light`` (the server restarted the
bot).  Every wear was the light ranker's ``wield-light`` (ladder_objectives, equipment-visit
journal ``writer`` ladder_objectives:key:498): the identified 光明の真鍮のランタン on (decision
1375), a torch on (1380), the lantern back (1381).

Source, copied read-only from the viewing server to C:/hengband-backups/pdca/n1b-416-light/:

* the town-arrival checkpoint the restart wrote on the stop's board
  (jsonlog/town-arrival/20261122-171216.637455517-turn132740; the stopped visit's own arrival
  checkpoint was not kept): the policy, the sidecars and the journal's rows 0-5;
* ``boards.json``: three boards of the stopped visit from the capture's state.jsonl.gz
  (captures/20261122-171212-town-blocked-equipment-slot-flipflop-light): turn 132166 (the
  visit's first town board: a torch worn, the lantern {高級品} unidentified), 132684 (the
  lantern identified and worn: the torch went on next) and 132728 (the torch worn: the lantern
  went back on next).

    python tests/extract_n1b_416_light_flipflop_1122_fixture.py
    (PYTHONPATH: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1b-416-light")
VISIT = SOURCE / "jsonlog/town-arrival/20261122-171216.637455517-turn132740"
STATE = SOURCE / "captures/20261122-171212-town-blocked-equipment-slot-flipflop-light/state.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1b-416-light-flipflop-1122"
ROWS = 6
TURNS = (132166, 132684, 132728)


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    boards = {}
    with gzip.open(STATE, "rt", encoding="utf-8") as stream:
        for line in stream:
            turn = json.loads(line).get("turn")
            if turn in TURNS:
                boards[str(turn)] = line.rstrip("\n")
    assert sorted(boards) == sorted(map(str, TURNS)), sorted(boards)
    (TARGET / "boards.json.xz").write_bytes(lzma.compress(
        json.dumps(boards, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(TARGET, sum(path.stat().st_size for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
