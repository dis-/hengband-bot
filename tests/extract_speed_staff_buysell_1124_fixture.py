"""Extract tests/fixtures/n1b-416-speed-staff-buysell-1124/ (tests/test_speed_staff_buysell_1124_recorded.py).

Source: n1-b life-416 (Magic-Eater Lv50, Angband recall depth 99), 2026-11-23, a read-only copy in
C:/hengband-backups/pdca/captures/finale-bm-fix-1123/ of the incident capture
``incident-captures/20261123-234051-town-blocked-stage-deadline-buy``:

  town-arrival-4313051/   the town-arrival checkpoint ``20261123-233918.037385005-turn4313051``
                          (back from 64F at 23:39:18, decision 160): the Black Market sold it a
                          Staff of Speed (5 charges) for 21,292 at decision 197 (23:39:36) and the
                          Magic shop bought it back for 2,764 at decision 205 (23:39:38)

Kept: the checkpoint's journal rows up to the sale (the loadout report left out, as the other
town-arrival fixtures).

    python tests/extract_speed_staff_buysell_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-bm-fix-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-speed-staff-buysell-1124"
ROWS = 48


def main():
    extract(ROOT / "town-arrival-4313051", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
