"""Extract tests/fixtures/n1a-543-opening-release-1126-<n>/ (test_n1a_543_opening_release_1126_recorded).

Source: n1-a life-543 and life-544, Amberite Rogues (build bot-45814a87b) that completed Q34 and
then stopped in the Outpost as quest:blocked:opening-route on 2026-11-26 (Q1 readiness: DPS
12.705 and 13.167 against the Warrior row's 13.23).  Each fixture keeps one capture's
town-arrival checkpoint, its journal rows and sidecars (town_arrival_fixture.extract).

    PYTHONPATH="src;tests;." python tests/extract_n1a_543_opening_release_1126_fixtures.py <n1-a soak dir>

Only this tool reads the captures; the committed test reads the fixtures alone.
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURES = Path(__file__).with_name("fixtures")
# fixture suffix: (capture under the soak dir, journal rows kept)
CAPTURES = {
    # life-543's first stop: the arrival after the Q34 reward, 45 boards to the stop.
    "1": ("life-543/incident-captures/20261126-224614-quest-blocked-opening-route", 45),
    # life-543's restart: 8 boards to the stop.
    "2": ("life-543/incident-captures/20261126-224625-quest-blocked-opening-route", 8),
    # life-544's restart: 11 boards to the stop.
    "3": ("life-544/incident-captures/20261126-224718-quest-blocked-opening-route", 11),
}


def main() -> None:
    root = Path(sys.argv[1])
    for suffix, (capture, rows) in CAPTURES.items():
        extract(root / capture / "town-arrival",
                FIXTURES / f"n1a-543-opening-release-1126-{suffix}", rows)


if __name__ == "__main__":
    main()
