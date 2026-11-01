"""Freeze the 2026-11-01 01:01 n1-a life-454 departure-unsatisfiable stop (D54).

Source: the automatic capture incident-captures/20261101-010142-departure-
unsatisfiable of the viewing warrior n1-a life-454 (Lv8, 189 gold, build
bot-f9c921d32), copied read-only to C:/hengband-backups/pdca/captures/
fix-depart-1101.  Right after Q1 the character held one Word of Recall of
the nine it needed, eight Treasure Detection scrolls and no digger; the
General store sold no digger it could pay for (one 1,436-gold shovel at
80151, none later), so fundraising stayed in ``prepare`` waiting for the
mining kit.  The town owners retired (stuck:wander, boxed breakouts) and the
visit stopped with departure_block.failed ["recall_departure_ready",
"food_ready", "teleport_ready", "cure_critical_ready", "identify_staff_ready",
"home_candidate_resolved", "identification_need_clear",
"departure_identification_need_clear"], then town:blocked:owner-retired-burst
three times.

Frozen in the shape tests/extract_unid_deposit_fixture.py writes (the arrival
board after Q1, the visit's store pages and knowledge, the stop board and
decision).  Only this tool reads the capture.
"""

from __future__ import annotations

from pathlib import Path

from tests.extract_unid_deposit_fixture import freeze


CAPTURE = Path("C:/hengband-backups/pdca/captures/fix-depart-1101/n1-a/life-454/"
               "incident-captures/20261101-010142-departure-unsatisfiable")
OUTPUT = Path(__file__).with_name("fixtures") / "diggerless-scavenge-20261101.json.gz"
ARRIVAL_TURN, STOP_TURN = 82392, 86884


def main():
    freeze(CAPTURE, OUTPUT, ARRIVAL_TURN, STOP_TURN,
           "incident-20261101-010142-departure-unsatisfiable (n1-a life-454)")


if __name__ == "__main__":
    main()
