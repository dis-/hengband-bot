"""Extract tests/fixtures/n1a-530-unseen-entrance-1117/.

Source: n1-a life-530's town-arrival checkpoint of 2026-11-17 17:37:47 (turn 8370825), the visit
that ended with the stop town:blocked:survival:depth_abilities of 17:38:01
(~/hengbot-soak/n1-a/life-530/incident-captures/20261117-173801-town-blocked-survival-depth_abilities,
copied read-only): the arrival policy, the visit's 34 journal rows (row 33 the stop) and the sidecar
files the restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_unseen_entrance_1117_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-unseen-entrance-1117"
ROWS = 34


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
