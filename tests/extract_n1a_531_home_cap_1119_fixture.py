"""Extract tests/fixtures/n1a-531-home-cap-1119/.

Source: n1-a life-531's town arrival of 2026-11-19 02:21:47 (turn 3849028), copied read-only
to C:/hengband-backups/pdca/quest32-1119/n1-a-life-531/ (the Q32 strategy study's copy of
hengband.net ~/hengbot-soak/n1-a/life-531/jsonlog/town-arrival/): the arrival checkpoint
(policy.pkl), the first four journal rows and the sidecar files the restored policy reads,
xz-compressed (tests/support/town_arrival_fixture.py).  The Home holds 239 stacks.

    python tests/extract_n1a_531_home_cap_1119_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-home-cap-1119"
ROWS = 4


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
