"""Extract tests/fixtures/n1b-411-castle-dive-1117/.

Source: n1-b life-411's town-arrival checkpoint of 2026-11-17 13:08:41 (turn 4828866), the
visit that ended with the loop-detected stop of 13:08:57
(~/hengbot-soak/n1-b/life-411/jsonlog/town-arrival/20261117-130841.283724632-turn4828866 and
captures/20261117-130857-loop-detected, copied read-only to
C:/hengband-backups/pdca/captures/n1b-411-mining-1117/): the arrival policy, the visit's first
26 journal rows (row 25 the first town:blocked:depth-gate:destination-51:missing-destruction)
and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_castle_dive_1117_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-castle-dive-1117"
ROWS = 26


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
