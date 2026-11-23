"""Extract tests/fixtures/n1c-221-finale-gear-1123/ (tests/test_finale_gear_1123_recorded.py).

Source: n1-c life-221 (Magic-Eater Lv46, Angband recall depth 95), 2026-11-23, a read-only copy
in C:/hengband-backups/pdca/captures/finale-gear-1123/:

  town-arrival-5072942/   the town-arrival checkpoint ``jsonlog/town-arrival/
                          20261123-232731.414202503-turn5072942`` (23:27:31): the Home holds
                          ★賢者マーリンの魔法の鏡 (artifact 265: RES_CURSE, RES_BLIND), the decision
                          record's ``angband_finale`` reported resist curse and resist blindness
                          or light missing from the owned gear

Kept: the checkpoint's first 4 journal rows (the loadout report left out, as the other
town-arrival fixtures); row 2 is the visit's first fresh loadout search.

    python tests/extract_finale_gear_1123_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-gear-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-finale-gear-1123"
ROWS = 4


def main():
    extract(ROOT / "town-arrival-5072942", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
