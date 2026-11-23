"""Extract tests/fixtures/n1c-221-finale-gear-1124/ (tests/test_finale_gear_1124_recorded.py).

Source: n1-c life-221 (Zombie Magic-Eater Lv50), 2026-11-24, a read-only copy in
C:/hengband-backups/pdca/captures/finale-gear-1124/:

  20261124-071332.833855847-turn6256121/   the town-arrival checkpoint ``jsonlog/town-arrival/
                          20261124-071332.833855847-turn6256121`` (07:13:32), the visit that
                          switched to 99F/100F and wore the finale set (CON 18/140, HP 915)

Kept: the checkpoint's first 4 journal rows (the loadout report left out, as the other
town-arrival fixtures).

    python tests/extract_finale_gear_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-gear-1124")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-finale-gear-1124"
ROWS = 4


def main():
    extract(ROOT / "20261124-071332.833855847-turn6256121", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
