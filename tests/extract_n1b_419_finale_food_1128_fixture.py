"""Extract tests/fixtures/n1b-419-finale-food-1128/ (tests/test_n1b_419_finale_food_1128_recorded.py).

Source: n1-b life-419 (Zombie Magic-Eater CL50, build bot-ad2db18c6), the incident capture
``incident-captures/20261128-072403-loop-detected`` copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-419-finale-food-1128/:

  town-arrival/           the town visit of 2026-11-28 07:23:06 (arrival turn 14707739, decision 711):
                          the equipment transactions at the Home (rows 6-71), the finale preparation's
                          Home read (row 73), deposit, the Magic shop sale and the Black Market's
                          *Healing* (rows 74-85), and from row 86 on the town stopped under
                          town:blocked:finale-prep-stopped:food:wonder-uncharged

Kept: the first ``ROWS`` journal rows (the loadout report left out, as the other town-arrival
fixtures).

    python tests/extract_n1b_419_finale_food_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-419-finale-food-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-finale-food-1128"
ROWS = 90


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
