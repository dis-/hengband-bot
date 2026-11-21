"""Extract tests/fixtures/n1b-411-twilight-robe-1121/ for test_n1b_411_twilight_robe_1121_recorded.

Source: n1-b life-411's town arrival of 2026-11-21 11:26:08 (turn 11335544), wearing 宵闇のローブ,
copied to C:/hengband-backups/pdca/captures/n1b-411-20261121-twilight-robe/town-arrival/.

    python tests/extract_n1b_411_twilight_robe_1121_fixture.py <capture>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-twilight-robe-1121"
ARRIVAL = "town-arrival/20261121-112608.607288878-turn11335544"


def main() -> None:
    visit = Path(sys.argv[1]) / ARRIVAL
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows)


if __name__ == "__main__":
    main()
