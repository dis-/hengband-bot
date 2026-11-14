"""Extract tests/fixtures/n1a-522-overweight-1114/.

Source: n1-a life-522's incident capture of 2026-11-14 16:34:50
(town:blocked:overweight-retained-only, bot cdf059701), copied read-only to
C:/hengband-backups/pdca/captures/overweight-1114/n1-a/life-522/incident-captures/
20261114-163450-town-blocked-overweight-retained-only/town-arrival/: the arrival
checkpoint (policy.pkl, turn 2781151), the whole visit journal (157 rows, row 156 the
board of the stop) and the sidecar files the restored policy reads (the arrival
calibration among them; the 8 MB loadout report is left out), xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_522_overweight_1114_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-522-overweight-1114"
ROWS = 157


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
