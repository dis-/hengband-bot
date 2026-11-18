"""Extract tests/fixtures/n1b-411-entrance-wait-1118/.

Source: n1-b life-411's town-arrival checkpoint of 2026-11-18 14:26:45 (turn 7149646, bot
8c523e614), copied read-only from hengband.net
~/hengbot-soak/n1-b/life-411/jsonlog/town-arrival/20261118-142645.007639632-turn7149646/: the
arrival checkpoint (policy.pkl), all 51 journal rows (row 50 the empty decision that stopped
the bot with no-key-exhausted at 14:27:03) and the sidecar files the restored policy reads,
xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_entrance_wait_1118_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-entrance-wait-1118"
ROWS = 51


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
