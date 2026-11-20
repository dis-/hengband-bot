"""Extract tests/fixtures/n1b-411-transfer-clear-1121/.

Source: n1-b life-411's stop of 2026-11-21 01:09:15 (town:blocked:survival:equipment_transfer_clear,
bot main 31f2fa528), its town-arrival directory 20261121-010834.192417917-turn11195981 (the local
copy of the capture n1b-411-20261121-010918-town-blocked-survival-equipment-transfer-clear): the
arrival checkpoint (policy.pkl), all 122 journal rows (row 121 the stop) and the sidecar files the
restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_transfer_clear_1121_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-transfer-clear-1121"
ROWS = 122


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
