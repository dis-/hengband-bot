"""Extract tests/fixtures/n1a-530-home-cash-sale-1118/.

Source: n1-a life-530's town-arrival checkpoint of 2026-11-18 06:38:41 (turn 11907268, the
Lv49 warrior back from the Yeek cave's first floor in the mining set the 06:36:52 *Identify*
purchase's 1,160 gold opened), copied read-only from hengband.net
~/hengbot-soak/n1-a/life-530/jsonlog/town-arrival/20261118-063841.592339344-turn11907268/:
the arrival checkpoint (policy.pkl, with the visit's current Home census of 237 rows), the
first journal row and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_home_cash_sale_1118_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-home-cash-sale-1118"
ROWS = 1


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
