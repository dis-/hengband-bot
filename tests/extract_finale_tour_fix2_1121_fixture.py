"""Extract tests/fixtures/n1c-217-finale-tour-fix2-1121/ for test_finale_tour_fix2_1121_recorded.

Source: n1-c life-217, 2026-11-21 03:49:31-03:50:13 (bot-5de5adae3), copied to
C:/hengband-backups/pdca/captures/n1c-217-20261121-0349-finale-tour-missed2/: the town-arrival
checkpoint (turn 7117362) with the whole visit's journal (231 rows, through the recall read).

    python tests/extract_finale_tour_fix2_1121_fixture.py <capture>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-finale-tour-fix2-1121"
ARRIVAL = "jsonlog/town-arrival/20261121-034931.667590273-turn7117362"


def main() -> None:
    visit = Path(sys.argv[1]) / ARRIVAL
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows)


if __name__ == "__main__":
    main()
