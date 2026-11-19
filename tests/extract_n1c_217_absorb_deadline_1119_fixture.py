"""Extract tests/fixtures/n1c-217-absorb-deadline-1119/.

Source: n1-c life-217's stop of 2026-11-19 17:53:43 (town:blocked:stage-deadline:quest, bot main
00a79d9dc0), its town-arrival directory 20261119-175320.890814885-turn4858301 (the live capture's
copy C:/hengband-backups/pdca/captures/n1c-217-absorb-deadline-1119, read-only): the arrival
checkpoint (policy.pkl, a Linux pickle), all 65 journal rows (row 64 the stop) and the sidecar
files the restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1c_217_absorb_deadline_1119_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-absorb-deadline-1119"
ROWS = 65


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
