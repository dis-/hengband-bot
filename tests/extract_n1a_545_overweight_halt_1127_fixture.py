"""Extract tests/fixtures/n1a-545-overweight-halt-1127/ (tests/test_n1a_545_overweight_halt_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL33, Sorcery, HP 700, gold 337 on arrival), the incident
capture ``incident-captures/20261127-102849-town-blocked-overweight-home-full-no-legal-relief``
copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1a-545-overweight-halt-1127/:

  town-arrival/           100 rows (arrival turn 4096373): the visit identified, deposited and
                          bought; row 97 bought ten Treasure Detection scrolls for the mining kit
                          (gold 337 -> 137) and row 99 stopped under
                          town:blocked:overweight-home-full-no-legal-relief (Home 146 items)

  live-files/bot_rogue2.txt
                          the character dump the game wrote for row 9's periodic C-screen dump
                          (10:28:15, copied read-only from life-545/user/ after the stop; it was
                          not rewritten after that row).  The journal holds no dump file, and the
                          arrival's sidecar copy is the older one, so without it row 10 on reads a
                          stale dump, the calibration is refused and the equipment transaction of
                          row 50 never opens (the replay diverged there).

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures) and the
row-9 dump as ``character-dump-row9.txt.xz``.

    python tests/extract_n1a_545_overweight_halt_1127_fixture.py
"""
from pathlib import Path

import lzma

from support.town_arrival_fixture import PRESET, extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-overweight-halt-1127/"
            "20261127-102849-town-blocked-overweight-home-full-no-legal-relief")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-overweight-halt-1127"
ROWS = 100
DUMP = Path("C:/hengband-backups/pdca/captures/n1a-545-overweight-halt-1127/live-files/bot_rogue2.txt")


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    (FIXTURE / "character-dump-row9.txt.xz").write_bytes(lzma.compress(DUMP.read_bytes(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
