"""Freeze the n1-a life-469 loop boards of 2026-11-03 09:30 (鉄獄30階).

Source: the automatic loop-detected capture of the viewing warrior n1-a
(build 96a499308), copied read-only to
C:/hengband-backups/pdca/captures/hourly-0900-1103/n1-a/life-469/incident-captures/
20261103-093012-loop-detected/:

  snapshots/snapshots-current.jsonl.gz
      the player boards of turns 938634-939207: the unseen retreat
      (``unseen:reverse-choke``), the fight beside the ミミック(箱) (race
      NEVER_MOVE, summons and curses from out of sight), and the alternation
      of ``explore:avoid-immobile-summoner`` '6' and ``unseen:reverse-choke``
      '4' between (3, 80) and (3, 81) up to the loop detector;
  decision-tail.jsonl
      the recorded decision rows of the same turns.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0900-1103/n1-a/life-469/incident-captures")
CAPTURE = "20261103-093012-loop-detected"
SPAN = (938634, 939207)
OUTPUT = Path(__file__).with_name("fixtures") / "loop-n1a-469-1103.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1a-469", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]))


if __name__ == "__main__":
    main()
