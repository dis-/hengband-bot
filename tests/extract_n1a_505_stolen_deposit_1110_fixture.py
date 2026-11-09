"""Extract tests/fixtures/stolen-deposit-1110/.

Source: n1-a life-505 2026-11-10 01:37 equipment-transaction:restore-blocked-terminal,
the town-arrival checkpoint of its incident capture on the viewing server
(~/hengbot-soak/n1-a/life-505/incident-captures/20261110-013747-equipment-transaction-
restore-blocked-terminal), copied read-only to
C:/hengband-backups/pdca/captures/n1a-505-stolen-deposit-1110/incident-20261110-013747/.

- ``t505``: the whole journal of the visit (32 rows, decisions 2349-2380).

Keeps the pickled arrival policy, the journal and the runtime sidecars with
their manifest (tests/extract_stops_1109_town_fixtures.py).

    python tests/extract_n1a_505_stolen_deposit_1110_fixture.py <capture>
"""
import sys
from pathlib import Path

import extract_stops_1109_town_fixtures as base

base.OUTPUT = Path(__file__).with_name("fixtures") / "stolen-deposit-1110"
base.ROWS = {"t505": 32}


def main() -> None:
    base.extract("t505", Path(sys.argv[1]))


if __name__ == "__main__":
    main()
