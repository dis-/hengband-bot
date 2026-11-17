"""Extract tests/fixtures/n1b-411-resume-poverty-1117/.

Source: n1-b life-411's town-arrival checkpoint of 2026-11-17 13:37:21 (turn 4829584), the
first town board after the resume of 13:37:19
(~/hengbot-soak/n1-b/life-411/jsonlog/town-arrival/20261117-133721.989989623-turn4829584, copied
read-only to C:/hengband-backups/pdca/captures/n1b-411-mining-1117/): the arrival policy, the
visit's first 11 journal rows (row 10 the first seek-downstairs toward the Yeek cave) and the
sidecar files the restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_resume_poverty_1117_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-resume-poverty-1117"
ROWS = 11


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
