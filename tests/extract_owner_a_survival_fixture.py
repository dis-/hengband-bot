"""Freeze the boards of the owner answers 1-3 of 2026-10-31 15h (#47, owner-a-survival).

Sources (read-only, C:/hengband-backups/pdca/captures/latest-12h-1031):

- adjacent-latch: n1-a life-446, incident capture 20261031-060729-player-death.
  The ring's player_turn boards 1712380..1712419 (the second emergency escape
  latches the town return at 1712410) and 1712924..1712931 (beside the
  immobile summoner's floor the avoidance meleed the adjacent hostile at
  1712931 although the return was latched).
- blind: the same capture, 1713388..1713414 (fighting the デス・ドレイク at
  [14,81], then blinded at 1713414 without seeing it any more).
- dark-stair: n1-c life-055 captures/20261031-081315-loop-detected state row
  114 (鉄獄1階, the burnt-out torch worn, the Brass Lantern {average} and a
  flask of oil carried; the return searched walls in the dark).
- dark-room: n1-c life-055 captures/20261031-081258-loop-detected state rows
  20 and 21 (the lit room [19,114] and, one step out of it, dark [20,113]).

Each case keeps the boards and the recorded decision rows of the same turns
(extract_dungeon_1031_fixture.ring_case / state_case).  Only this extraction
tool reads the captures; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import ROOT, ring_case, state_case


OUTPUT = Path(__file__).with_name("fixtures") / "owner-a-survival-1031.json.gz"


def main():
    death = ROOT / "n1-a/life-446/incident-captures/20261031-060729-player-death"
    life055 = ROOT / "n1-c/life-055/captures"
    cases = {
        "latch": ring_case(death, 1712380, 1712419),
        "adjacent": ring_case(death, 1712924, 1712931),
        "blind": ring_case(death, 1713388, 1713414),
        "dark-stair": state_case(life055 / "20261031-081315-loop-detected", [114]),
        "dark-room": state_case(life055 / "20261031-081258-loop-detected", [20, 21]),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
