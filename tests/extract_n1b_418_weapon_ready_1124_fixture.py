"""Freeze the town:blocked:survival:combat_weapon_ready visit of 2026-11-24.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-418-combat-weapon-ready-1124/:

- n1-b/life-418/incident-captures/20261124-220608-town-blocked-survival-combat_weapon_ready/
  town-arrival/ (22:05:30, turn 869302, Lv17 Zombie Magic-Eater) -- the town visit whose two
  Tower of Sorcery trips (me-staff) ended on the stop, its 149 journal rows (the stop is the
  last).

Only this extraction tool reads the capture; the committed test reads the fixture.
"""

from __future__ import annotations

from pathlib import Path

from support.town_arrival_fixture import extract

CAPTURES = Path("C:/hengband-backups/pdca/captures/n1b-418-combat-weapon-ready-1124")
FIXTURES = Path(__file__).with_name("fixtures")
VISIT = CAPTURES / "n1-b/life-418/town-arrival"


def main():
    extract(VISIT, FIXTURES / "n1b-418-weapon-ready-1124", 149)


if __name__ == "__main__":
    main()
