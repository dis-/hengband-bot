"""Extract tests/fixtures/town-stops-1109b/.

Source: the town-arrival checkpoints of the viewing bots' town stops of
2026-11-09 after 08:00 (the incident captures of the viewing server):

- ``i497``: n1-a life-497 2026-11-09 08:46 town:blocked:owner-retired-burst.
- ``j497``: n1-a life-497 2026-11-09 11:31 town:blocked:survival:identify_staff_ready.
- ``d179``: n1-c life-179 2026-11-09 08:16 town:blocked:owner-retired-burst.

Each keeps its pickled arrival policy, its journal cut to the rows the tests
replay, and its runtime sidecars with their manifest.

    python tests/extract_town_stops_1109b_fixtures.py <i497> <j497> <d179>
"""
import sys
from pathlib import Path

import extract_stops_1109_town_fixtures as base

base.OUTPUT = Path(__file__).with_name("fixtures") / "town-stops-1109b"
base.ROWS = {"i497": 18, "j497": 15, "d179": 2}


def main() -> None:
    for name, capture in zip(base.ROWS, sys.argv[1:4]):
        base.extract(name, Path(capture))


if __name__ == "__main__":
    main()
