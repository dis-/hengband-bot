"""Extract tests/fixtures/n1b-407-retired-home-exit-1116/n1b-407-1330/.

Source: n1-b life-407's town-arrival checkpoint of 2026-11-16 13:30:13 (Magic-Eater
Lv50, turn 5,378,821), from the viewing server's loop-detected incident capture
life-407/incident-captures/20261116-133135-loop-detected/town-arrival/, copied
read-only to C:/hengband-backups/pdca/captures/n1b-407-restock-1116/.

Journal row 43 is the Home page on which the forgiven owner retirement replaced
``home:full-skip:sale-item-held``'s Enter with the exit (``--owner-retired-log-only``);
row 44 is the first outside board, live ``town:blocked:restock-store-unreachable``.
The fixture keeps journal rows 0-44 with the checkpoint (``policy.pkl``) and the
sidecar files, all xz-compressed (tests/support/town_arrival_fixture.extract).

    PYTHONPATH="src;tests;." python tests/extract_n1b_407_retired_home_exit_1116_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1b-407-restock-1116/"
             "20261116-133135-loop-detected/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1b-407-retired-home-exit-1116" / "n1b-407-1330"
ROWS = 45


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
