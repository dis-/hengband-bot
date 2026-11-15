"""Extract tests/fixtures/n1c-212-me-staff-fare-1115/.

Source: n1-c life-212's incident capture 20261115-141201-quest-blocked-me-staff (build
138f619e1), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1c-212-me-staff-1115/incident-captures/: the town-arrival checkpoint of
the Outpost visit (turn 344116) and its journal rows 0-9 (row 8 the first Morivant board after
the Magic shop's page), the loadout report left out.

    PYTHONPATH="src;tests" python tests/extract_n1c_212_me_staff_fare_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1c-212-me-staff-1115/incident-captures/"
             "20261115-141201-quest-blocked-me-staff/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-212-me-staff-fare-1115"
ROWS = 10


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
