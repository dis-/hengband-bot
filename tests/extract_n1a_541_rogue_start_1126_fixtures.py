"""Extract tests/fixtures/n1a-541-rogue-start-1126-<n>/ (test_n1a_541_rogue_start_1126_recorded).

Source: n1-a life-541, the first Amberite Rogue (build bot-e5ddb9743), whose Q34-first opening
stopped in town as livelock:exhausted three times on 2026-11-26 (incident captures
20261126-215216 / -215227 / -215234-livelock-exhausted).  Each fixture keeps one capture's
town-arrival checkpoint, its journal rows and sidecars (town_arrival_fixture.extract).

    PYTHONPATH="src;tests;." python tests/extract_n1a_541_rogue_start_1126_fixtures.py <incident-captures-dir>

Only this tool reads the captures; the committed test reads the fixtures alone.
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURES = Path(__file__).with_name("fixtures")
# fixture suffix: (capture, journal rows kept)
CAPTURES = {
    "1": ("20261126-215216-livelock-exhausted", 11),
    "2": ("20261126-215227-livelock-exhausted", 15),
    "3": ("20261126-215234-livelock-exhausted", 5),
}


def main() -> None:
    root = Path(sys.argv[1])
    for suffix, (capture, rows) in CAPTURES.items():
        extract(root / capture / "town-arrival",
                FIXTURES / f"n1a-541-rogue-start-1126-{suffix}", rows)


if __name__ == "__main__":
    main()
