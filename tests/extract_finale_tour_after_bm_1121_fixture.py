"""Extract tests/fixtures/n1c-217-finale-tour-after-bm-1121/ for
test_finale_tour_after_bm_1121_recorded.

Source: n1-c life-217, 2026-11-21 02:57-03:01 (main 31f2fa528), copied to
C:/hengband-backups/pdca/captures/n1c-217-20261121-0257-finale-tour-missed/.
The town-arrival checkpoint (Zul, turn 7002152: 26 of the 40 Teleportation carried,
none at Home) and two recorded town boards of n1c-state.gz:

* ``last-bm-town``: town 3 at turn 7019700, the last town of the Black Market tour
  (town:cross-town-bm-tour:travel-3), where the Word of Recall was read at 02:59:41;
* ``alchemist-seen``: town 1 at turn 6996376 (the previous loop of the circuit), its
  Alchemist shelf seen without the scrolls at turn 6995315.

    python tests/extract_finale_tour_after_bm_1121_fixture.py <capture>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import PRESET, extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-finale-tour-after-bm-1121"
ARRIVAL = "jsonlog/town-arrival/20261121-025709.566203430-turn7002152"
STATES = "n1c-state.gz"
BOARDS = {"last-bm-town": (7019700, 4), "alchemist-seen": (6996376, 2)}  # (turn, town_index)


def boards(path: Path) -> dict:
    found: dict = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            board = json.loads(line)
            floor = board.get("floor", {})
            for name, (turn, town_index) in BOARDS.items():
                if (name not in found and board.get("turn") == turn and floor.get("in_town")
                        and floor.get("town_index") == town_index and not board.get("store")):
                    found[name] = board
    return found


def main() -> None:
    root = Path(sys.argv[1])
    visit = root / ARRIVAL
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows)
    found = boards(root / STATES)
    assert set(found) == set(BOARDS), sorted(found)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(
        json.dumps(found, ensure_ascii=False).encode("utf-8"), preset=PRESET))


if __name__ == "__main__":
    main()
