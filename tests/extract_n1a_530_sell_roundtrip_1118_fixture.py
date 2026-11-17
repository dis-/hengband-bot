"""Extract tests/fixtures/n1a-530-sell-roundtrip-1118/.

Source: n1-a life-530's incident capture of 2026-11-18 03:53:26
(town:blocked:stage-deadline:sell, bot fa6471d0f), copied read-only from hengband.net
~/hengbot-soak/n1-a/life-530/incident-captures/
20261118-035326-town-blocked-stage-deadline-sell/town-arrival/: the arrival checkpoint
(policy.pkl, turn 11516973), the first 85 journal rows (row 84 the Weaponsmith board of the
refused third round trip) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_sell_roundtrip_1118_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-sell-roundtrip-1118"
ROWS = 85


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
