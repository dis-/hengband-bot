"""Extract tests/fixtures/n1c-222-finale-check-1126/ for test_finale_check_1126_recorded.

Source: n1-c life-222's incident capture
``incident-captures/20261126-074659-town-blocked-unmet-equipment_departure_ready/town-arrival/``
(Zombie Magic-Eater Lv50, 2026-11-26 07:46:26, turn 12306848: the town arrival of the process
restarted by the deploy, every journal row through the stop's own, 19 rows).

    python tests/extract_n1c_222_finale_check_1126_fixture.py <capture>/town-arrival
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-finale-check-1126"
ROWS = 19


def main() -> None:
    extract(Path(sys.argv[1]), FIXTURE, ROWS)


if __name__ == "__main__":
    main()
