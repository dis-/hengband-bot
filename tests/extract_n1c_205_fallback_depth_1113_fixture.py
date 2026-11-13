"""Extract tests/fixtures/n1c-205-fallback-depth-1113/.

Source: n1-c life-205 (Lv46 Magic-Eater) 2026-11-13 18:54:18, the town arrival
after an Orc cave 23F dive of the over-extension alternate (pack-full return).
The town-arrival checkpoint 20261113-185418.072937541-turn4570597 on the
viewing server (~/hengbot-soak/n1-c/life-205/jsonlog/town-arrival/), copied
read-only to
C:/hengband-backups/pdca/captures/n1c-205-fallback-depth-1113/visit/town-arrival/
(with the live alternate-dungeon.json beside it).

- ``visit``: the arrival policy and the journal rows 0-50 (row 50 is the
  recall read, ``rgc`` town:recall-to-alt-dungeon: the Orc cave 23F).

    python tests/extract_n1c_205_fallback_depth_1113_fixture.py <capture>/visit
"""
import sys
from pathlib import Path

import extract_stops_1109_town_fixtures as base

base.OUTPUT = Path(__file__).with_name("fixtures") / "n1c-205-fallback-depth-1113"
base.ROWS = {"visit": 51}


def main() -> None:
    base.extract("visit", Path(sys.argv[1]))


if __name__ == "__main__":
    main()
