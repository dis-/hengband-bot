"""Extract tests/fixtures/home-scan-take-1112/.

Source: n1-c life-196 2026-11-12 00:44 town:blocked:owner-retired-burst after
town:blocked:equipment-home-unavailable, the town-arrival checkpoint of its
incident capture on the viewing server
(~/hengbot-soak/n1-c/life-196/incident-captures/20261112-004419-town-blocked-
owner-retired-burst-after-town-blocked-equipment-home-unavailable), copied
read-only to C:/hengband-backups/pdca/captures/n1c-196-home-unavail-1112/.

- ``h196``: the journal of the visit through the first blocked decision
  (49 rows, decisions 32310-32358).

Keeps the pickled arrival policy, the journal and the runtime sidecars with
their manifest (tests/extract_stops_1109_town_fixtures.py).

    python tests/extract_n1c_196_home_scan_take_1112_fixture.py <capture>
"""
import sys
from pathlib import Path

import extract_stops_1109_town_fixtures as base

base.OUTPUT = Path(__file__).with_name("fixtures") / "home-scan-take-1112"
base.ROWS = {"h196": 49}


def main() -> None:
    base.extract("h196", Path(sys.argv[1]))


if __name__ == "__main__":
    main()
