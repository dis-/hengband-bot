"""Extract tests/fixtures/n1a-525-device-skill-1115/.

Source: n1-a life-525's town-arrival checkpoint of 2026-11-15 17:36:10 (turn
10008229), copied read-only from the viewing server's
jsonlog/town-arrival/20261115-173610.999923530-turn10008229/ to
C:/hengband-backups/pdca/warrior-device-1115/: the arrival policy, the visit's 10
journal rows (row 9 the descent to the Yeek cave's 1F) and the sidecar files the
restored policy reads (the character dump among them; the 28 MB loadout report was
not copied by the capture), xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_525_device_skill_1115_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-device-skill-1115"
ROWS = 10


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
