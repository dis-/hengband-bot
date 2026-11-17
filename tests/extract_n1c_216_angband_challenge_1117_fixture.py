"""Extract tests/fixtures/n1c-216-angband-challenge-1117/.

Source: n1-c life-216's incident capture of 2026-11-17 17:28:01 (``loop-detected``, Magic-Eater
Lv50, the black-market tour loop), copied read-only from the viewing server to
C:/hengband-backups/pdca/bm-tour-loop-1117/incident-captures/20261117-172801-loop-detected/.
Only its town-arrival checkpoint (17:15:15, turn 5,750,562; the Glass castle conquest target,
2,609,342 gold, Angband's recall landing 80) and the first journal row (the arrival board) are
kept: the test reads the destination decided on that board, not the visit.

    PYTHONPATH="src;tests" python tests/extract_n1c_216_angband_challenge_1117_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/bm-tour-loop-1117/incident-captures/"
             "20261117-172801-loop-detected/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-216-angband-challenge-1117"


def main() -> None:
    extract(VISIT, TARGET, 1, frozenset({"_loadout_report_path"}))


if __name__ == "__main__":
    main()
