"""Extract tests/fixtures/hazard-search-1106.json.gz: n1-a life-492's walk onto the
HEAVY_ELECTRICAL_ZONE (terrain 229) out of the pocket at (15,84), Orc cave 23F.

Source: the player_turn boards of hengband.net
~/hengbot-soak/n1-a/life-492/incident-captures/20261106-235509-loop-detected, copied as
JSON lines to the path given on the command line.  Only this tool reads the copy; the
committed test reads the fixture: the boards from the walk out of the pocket at full HP
to the rest back in it, in order.
"""
import json
import sys
from pathlib import Path

from tests.extract_n1c_loops_0336_1102_fixtures import write


FIRST, LAST = 3729743, 3729824


def main(source: str) -> None:
    rows = [json.loads(line) for line in Path(source).open(encoding="utf-8")]
    write(Path(__file__).with_name("fixtures") / "hazard-search-1106.json.gz", [
        row for row in rows if row["type"] == "player_turn" and FIRST <= row["turn"] <= LAST])


if __name__ == "__main__":
    main(sys.argv[1])
