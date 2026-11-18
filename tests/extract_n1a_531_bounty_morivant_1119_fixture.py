"""Extract tests/fixtures/n1a-531-bounty-morivant-1119/.

Source: n1-a life-531's town-arrival checkpoint of 2026-11-19 04:47:45 (warrior Lv44, Morivant,
turn 4,226,851), copied read-only from the viewing server's
jsonlog/town-arrival/20261119-044745.707308051-turn4226851/ to
C:/hengband-backups/pdca/n1a-531-q32-stage-1119/; the visit stopped at 04:48:25 with
town:blocked:stage-deadline:quest (captures/20261119-044825-town-blocked-stage-deadline-quest).
The fixture keeps journal rows 0-5 with the checkpoint and the sidecar files; the large
loadout report is left out.

    python tests/extract_n1a_531_bounty_morivant_1119_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1a-531-q32-stage-1119/20261119-044745.707308051-turn4226851")
TARGET = Path(__file__).with_name("fixtures") / "n1a-531-bounty-morivant-1119"


def main() -> None:
    extract(VISIT, TARGET, 6, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
