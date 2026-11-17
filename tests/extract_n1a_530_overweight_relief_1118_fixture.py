"""Extract tests/fixtures/n1a-530-overweight-relief-1118/.

Source: n1-a life-530's incident capture of 2026-11-18 03:06:36
(town:blocked:overweight-home-full-no-legal-relief, bot 1df9764b9), copied read-only from
hengband.net ~/hengbot-soak/n1-a/life-530/incident-captures/
20261118-030636-town-blocked-overweight-home-full-no-legal-relief/town-arrival/: the arrival
checkpoint (policy.pkl, turn 11516396), all 31 journal rows (row 30 the stop) and the sidecar
files the restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_overweight_relief_1118_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-overweight-relief-1118"
ROWS = 31


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
