"""Extract tests/fixtures/n1c-223-haste-sustain-1127/ (tests/test_n1c_223_haste_sustain_1127_recorded.py).

Source: n1-c life-223 (Zombie Magic-Eater CL46, HP 1074, permanent speed +3, absorbed Speed 99
charges at a reliable rate; build bot-cd9f26f0f) on hengband.net, the rolling town-arrival
checkpoint ``jsonlog/town-arrival/20261127-134048.672221569-turn5722342`` copied read-only to
C:/hengband-backups/pdca/captures/speed-gate-70f-rework-1127/.  Angband's saved recall depth was 69:
the 2026-11-26 70-80F row (permanent +10) held the speed ceiling at 69F.  The visit (128 rows)
read Word of Recall to Angband.

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1c_223_haste_sustain_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/speed-gate-70f-rework-1127/"
            "20261127-134048.672221569-turn5722342")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-223-haste-sustain-1127"
ROWS = 128


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
