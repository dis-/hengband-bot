"""Extract tests/fixtures/n1b-411-robe-town-1121/ for test_n1b_411_robe_town_1121_recorded.

Source: n1-b life-411's town visit of 2026-11-21 12:41:04 (turn 11337431), wearing 宵闇のローブ,
copied to C:/hengband-backups/pdca/captures/n1b-411-20261121-1241-robe-town/town-arrival/: the
checkpoint after the arrival's first decision (45 journal rows; the C screen at row 11).

    python tests/extract_n1b_411_robe_town_1121_fixture.py <capture>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-robe-town-1121"
ARRIVAL = "town-arrival/20261121-124104.330655361-turn11337431"


def main() -> None:
    visit = Path(sys.argv[1]) / ARRIVAL
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows)


if __name__ == "__main__":
    main()
