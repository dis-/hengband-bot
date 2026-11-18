"""Extract tests/fixtures/n1a-531-overweight-1119/.

Source: n1-a life-531's stop of 2026-11-19 03:27:42
(town:blocked:overweight-home-full-no-legal-relief, bot 4f74fcc1d), copied read-only from
hengband.net ~/hengbot-soak/n1-a/life-531/jsonlog/town-arrival/
20261119-032720.269409722-turn4127811/: the arrival checkpoint (policy.pkl, turn 4127811),
all 28 journal rows (row 27 the stop) and the sidecar files the restored policy reads,
xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_531_overweight_1119_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-overweight-1119"
ROWS = 28


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
