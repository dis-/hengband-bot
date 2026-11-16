"""Extract tests/fixtures/n1a-528-depth-gate-1116/.

Source: n1-a life-528's town-arrival checkpoint of 2026-11-16 07:47:12 (turn 3439910),
captured with the loop-detected stop of 07:47:57
(~/hengbot-soak/n1-a/life-528/incident-captures/20261116-074757-loop-detected/town-arrival,
copied read-only to C:/hengband-backups/pdca/captures/n1a-528-depth-gate-1116/): the arrival
policy, the visit's first 49 journal rows (row 48 the first
town:blocked:depth-gate:destination-51) and the sidecar files the restored policy reads,
xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_528_depth_gate_1116_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-528-depth-gate-1116"
ROWS = 49


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
