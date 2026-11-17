"""Extract tests/fixtures/n1a-530-home-full-reject-1117/.

Source: n1-a life-530's incident capture of 2026-11-17 23:28:55
(town:blocked:survival:inventory_weight_ready, bot 47c9c23a5), copied read-only from
hengband.net ~/hengbot-soak/n1-a/life-530/incident-captures/
20261117-232855-town-blocked-survival-inventory_weight_ready/town-arrival/: the arrival
checkpoint (policy.pkl, turn 10926227), the first 68 journal rows (row 67 the board of
the second weight-overload deposit) and the sidecar files the restored policy reads
(the 49 MB loadout report was not copied by the capture), xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_home_full_reject_1117_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-home-full-reject-1117"
ROWS = 68


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
