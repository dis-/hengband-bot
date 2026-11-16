"""Extract tests/fixtures/n1c-216-guardian-alt-1117/.

Source: n1-c life-216's incident capture of 2026-11-17 01:50:46
(``town:blocked:guardian-bounce-no-alternate``, Magic-Eater Lv46, build bot-f2ce3ebf6),
copied read-only from the viewing server's
incident-captures/20261117-015046-town-blocked-guardian-bounce-no-alternate/ to
C:/hengband-backups/pdca/captures/n1c-216-guardian-alt-1117/.  Its town-arrival checkpoint
(01:50:34, turn 3,847,823) and all 42 journal rows replay as recorded on main f2ce3ebf6
(tests/replay_town_arrival.py); row 41 is the stop.

    PYTHONPATH="src;tests" python tests/extract_n1c_216_guardian_alt_1117_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1c-216-guardian-alt-1117/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-216-guardian-alt-1117"


def main() -> None:
    extract(VISIT, TARGET, 42, frozenset({"_loadout_report_path"}))


if __name__ == "__main__":
    main()
