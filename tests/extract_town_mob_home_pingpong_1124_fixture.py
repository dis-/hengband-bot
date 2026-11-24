"""Extract tests/fixtures/n1c-222-town-mob-home-1124/ (tests/test_town_mob_home_pingpong_1124_recorded.py).

Source: n1-c life-222 (Magic-Eater Lv23), the incident capture
``incident-captures/20261124-192436-town-blocked-stage-deadline-equipment/`` of the
town:blocked:stage-deadline:equipment auto-restart at 2026-11-24 19:24:44, a read-only copy in
C:/hengband-backups/pdca/captures/n1c-222-town-mob-home-1124/:

  town-arrival/           the town-arrival checkpoint of the return from the Orc cave 19F at
                          19:23:41 (turn 717107, decision 22804): the equipment transaction's
                          walk to Home and the town hunt's walk to a 戦傷兵士 alternated from
                          row 5 to the stage deadline (row 135)

Kept: every journal row of the checkpoint (136; the loadout report left out, as the other
town-arrival fixtures).

    python tests/extract_town_mob_home_pingpong_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-222-town-mob-home-1124/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-town-mob-home-1124"
ROWS = 136


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
