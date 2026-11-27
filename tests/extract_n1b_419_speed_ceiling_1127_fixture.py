"""Extract tests/fixtures/n1b-419-speed-ceiling-1127/ (tests/test_n1b_419_speed_ceiling_1127_recorded.py).

Source: n1-b life-419 (Zombie Magic-Eater CL50, HP 1128, permanent speed +17, gold 60,015 on
arrival; build bot-b5ea3de99) on hengband.net, the rolling town-arrival checkpoint
``jsonlog/town-arrival/20261127-122611.758669067-turn11367031`` copied read-only to
C:/hengband-backups/pdca/captures/n1b-419-shallow-dives-1127/town-arrival/.  Angband's saved
recall depth was 81 (Teleport Level from 80F onto 81F, playrecord-SOAK.txt), every other entered
dungeon's recall depth is in the board.  Row 10 posted the step-off of
town:unsafe-recall-fallback and row 40 read Word of Recall to the Castle (``rgf``,
town:recall-to-alt-dungeon; the held climb switch, the Castle band 45).

Kept: the first 41 journal rows (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1b_419_speed_ceiling_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-419-shallow-dives-1127/town-arrival/"
            "20261127-122611.758669067-turn11367031")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-speed-ceiling-1127"
ROWS = 41


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
