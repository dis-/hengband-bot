"""Freeze the 2026-10-31 23:23 n1-b life-282 departure-unsatisfiable stop.

Source: the automatic capture incident-captures/20261031-232319-departure-
unsatisfiable of the viewing warrior n1-b life-282 (Lv17, 8,672 gold, build
bot-404e73286).  The pack held 19 items (4 free, MIN_TERMINAL_FREE_PACK_SLOTS)
with an 18-charge Identify staff; three carried equipment items (an unaware
ring, an {excellent} soft leather armour and a {special} sabre) and a wand
waited for Identify.  The observed Alchemist shelf sold Identify scrolls
within gold, so the Home deposit pass kept the equipment carried, while the
pack budget refused the scroll (and the Identify staff) for a fifth free
slot.  departure_block.failed was ["identify_staff_ready",
"home_candidate_resolved", "identification_need_clear",
"departure_identification_need_clear"].

The frozen shape is the one tests/extract_unid_deposit_fixture.py writes;
only this tool reads the capture.
"""

from __future__ import annotations

from pathlib import Path

from tests.extract_unid_deposit_fixture import freeze


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-1031-2323/life-282/"
               "incident-captures/20261031-232319-departure-unsatisfiable")
OUTPUT = Path(__file__).with_name("fixtures") / "unid-scroll-room-20261031.json.gz"
ARRIVAL_TURN, STOP_TURN = 343636, 345239


def main():
    freeze(CAPTURE, OUTPUT, ARRIVAL_TURN, STOP_TURN,
           "incident-20261031-232319-departure-unsatisfiable (n1-b life-282)")


if __name__ == "__main__":
    main()
