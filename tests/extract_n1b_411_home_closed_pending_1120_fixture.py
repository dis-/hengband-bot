"""Extract tests/fixtures/n1b-411-home-closed-pending-1120/.

Source: n1-b life-411's stop of 2026-11-20 03:33:27 (town:blocked:unmet:home_pending_item_clear,
bot main b77b2b7c68), its town-arrival directory 20261120-033234.618313668-turn9765891 (the live
capture's copy, read-only): the arrival checkpoint (policy.pkl, a Linux pickle), all 106
journal rows (row 105 the stop) and the sidecar files the restored policy reads,
xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_home_closed_pending_1120_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-home-closed-pending-1120"
ROWS = 106


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
