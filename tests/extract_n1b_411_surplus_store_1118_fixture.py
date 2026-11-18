"""Extract tests/fixtures/n1b-411-surplus-store-1118/arrival/.

Source: n1-b life-411's town-arrival checkpoint of 2026-11-18 15:51:57 (Magic-Eater Lv50,
turn 7,309,154), the ``town-arrival/`` of incident capture
20261118-155222-loop-detected, copied read-only from the viewing server to
C:/hengband-backups/pdca/n1b-411-surplus-store-1118/town-arrival/.

* ``arrival``: that checkpoint with all 57 journal rows (decisions 1148-1204, the stop).

    python tests/extract_n1b_411_surplus_store_1118_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

SOURCE = Path("C:/hengband-backups/pdca/n1b-411-surplus-store-1118")
TARGET = Path(__file__).with_name("fixtures") / "n1b-411-surplus-store-1118"


def main() -> None:
    extract(SOURCE / "town-arrival", TARGET / "arrival", 57)
    for name in ("arrival",):
        print(name, sorted((path.name, path.stat().st_size) for path in (TARGET / name).iterdir()))


if __name__ == "__main__":
    main()
