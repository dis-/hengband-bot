"""Extract tests/fixtures/n1a-530-sell-deadline-1118/.

Source: n1-a life-530's incident capture of 2026-11-18 01:28:03
(town:blocked:stage-deadline:sell, bot c2c293b34), copied read-only from hengband.net
~/hengbot-soak/n1-a/life-530/incident-captures/
20261118-012803-town-blocked-stage-deadline-sell/town-arrival/: the arrival checkpoint
(policy.pkl, turn 11245773), the first 11 journal rows (row 10 the Weaponsmith board after
the sale's ``@1`` tag) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_sell_deadline_1118_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-sell-deadline-1118"
ROWS = 11


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
