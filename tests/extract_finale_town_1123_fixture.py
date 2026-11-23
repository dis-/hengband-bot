"""Extract tests/fixtures/n1b-416-finale-town-1123/ (tests/test_finale_town_1123_recorded.py).

Source: n1-b life-416 (Magic-Eater, Angband recall depth 99), 2026-11-23, a read-only copy in
C:/hengband-backups/pdca/captures/finale-town-1123/:

  town-arrival-4308361/   the town-arrival checkpoint ``jsonlog/town-arrival/
                          20261123-211345.470084024-turn4308361`` (back from the Castle 64F at
                          21:13:45): row 19 is ``town:unsafe-recall-fallback`` toward the Castle,
                          row 21 ``town:recall-to-alt-dungeon``

Kept: the checkpoint's first 22 journal rows (the loadout report left out, as the other
town-arrival fixtures).

    python tests/extract_finale_town_1123_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-town-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-town-1123"
ROWS = 22


def main():
    extract(ROOT / "town-arrival-4308361", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
