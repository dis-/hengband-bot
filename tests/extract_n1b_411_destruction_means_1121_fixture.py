"""Extract tests/fixtures/n1b-411-destruction-means-1121/ for
test_n1b_411_destruction_means_1121_recorded.

Source: n1-b life-411, 2026-11-21 04:55:38 (bot-96a461c09), copied to
C:/hengband-backups/pdca/captures/n1b-411-20261121-045656-loop-detected/: the town-arrival
checkpoint of turn 11261617 (the mining set's return), its one journal row.

    python tests/extract_n1b_411_destruction_means_1121_fixture.py <capture>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-destruction-means-1121"
ARRIVAL = "jsonlog/town-arrival/20261121-045538.528782484-turn11261617"


def main() -> None:
    visit = Path(sys.argv[1]) / ARRIVAL
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows)


if __name__ == "__main__":
    main()
