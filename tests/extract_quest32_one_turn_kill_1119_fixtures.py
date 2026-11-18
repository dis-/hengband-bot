"""Extract tests/fixtures/quest32-one-turn-kill-1119/{n1a-531,n1b-411,n1c-217}/.

Source: the newest town-arrival checkpoint of each viewing character on 2026-11-19, copied
read-only from the viewing server's ~/hengbot-soak/<bot>/life-<n>/jsonlog/town-arrival/ to
C:/hengband-backups/pdca/quest32-1119/:

* n1-a life-531, 20261119-022147.472786623-turn3849028 (warrior Lv42, the Outpost);
* n1-b life-411, 20261119-021905.798826121-turn7859191 (Magic-Eater Lv50, the Outpost);
* n1-c life-217, 20261119-022306.304457759-turn3213552 (Magic-Eater Lv36, the Outpost).

Each fixture keeps the arrival row (journal row 0) with the checkpoint and the sidecar
files (tests/support/town_arrival_fixture.extract); the large loadout report is left out.

    python tests/extract_quest32_one_turn_kill_1119_fixtures.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

SOURCE = Path("C:/hengband-backups/pdca/quest32-1119")
TARGET = Path(__file__).with_name("fixtures") / "quest32-one-turn-kill-1119"
VISITS = {"n1a-531": "n1-a-life-531", "n1b-411": "n1-b-life-411", "n1c-217": "n1-c-life-217"}


def main() -> None:
    for name, visit in VISITS.items():
        extract(SOURCE / visit, TARGET / name, 1, frozenset({"_loadout_report_path"}))
        print(name, sorted((path.name, path.stat().st_size) for path in (TARGET / name).iterdir()))


if __name__ == "__main__":
    main()
