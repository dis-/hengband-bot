"""Extract tests/fixtures/n1c-221-light-flipflop-1124/ (tests/test_light_flipflop_1124_recorded.py).

Source: n1-c life-221 (Magic-Eater Lv46, Angband recall depth 95), 2026-11-24, a read-only copy
in C:/hengband-backups/pdca/captures/light-flipflop-1124/:

  town-arrival-5554134/   the town-arrival checkpoint ``jsonlog/town-arrival/
                          20261124-045453.474783631-turn5554134`` (04:54:53, a process started in
                          town with build 5a0bd46c0): the visit that stopped at 04:58:38 as
                          ``town:blocked:equipment-slot-flipflop:light``

Kept: the checkpoint's first 44 journal rows (the loadout report left out, as the other
town-arrival fixtures); rows 36, 39 and 42 are the periodic browses of the absorbed staff, wand
and rod lists, whose answers are the boards of rows 37, 40 and 43.

    python tests/extract_light_flipflop_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/light-flipflop-1124")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-light-flipflop-1124"
ROWS = 44


def main():
    extract(ROOT / "town-arrival-5554134", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
