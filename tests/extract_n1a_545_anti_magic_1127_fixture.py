"""Extract tests/fixtures/n1a-545-anti-magic-1127/ (tests/test_caster_equipment_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL23, Sorcery), the live run's last town-arrival checkpoint
copied read-only from the viewing server (``~/hengbot-soak/n1-a/life-545/jsonlog/town-arrival``)
to C:/hengband-backups/pdca/captures/n1a-545-anti-magic-1127/:

  town-arrival/20261127-031152.649582844-turn1622167/
                          the town-arrival checkpoint of 2026-11-27 03:11:52: 39 rows; row 7
                          (town:restore-combat-weapon ``wob``) wears ☆死天使アズリエルの革製ラージ・
                          シールド {+探赤r毒暗獄沌;麻[魔, .} again (its NO_MAGIC known), with the
                          Sorcery books 1 and 2 carried, and the visit recalls to the dungeon in it

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_anti_magic_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-anti-magic-1127/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-anti-magic-1127"
ROWS = 39


def main():
    extract(ROOT / "20261127-031152.649582844-turn1622167", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
