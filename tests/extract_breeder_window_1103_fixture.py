"""Freeze the n1-c life-120 Q2 series of 2026-11-03 (breeder-window-1103).

Source: the state ring of the stall capture of 17:45:36, copied read-only to
C:/hengband-backups/pdca/captures/q2-pest-n1c-120-1103/captures/.  The fixture
keeps boards 56-97 of the ring: the worm count falls from 47 to 25 over the
first 20 actions and rises to 33 over the next 20.  Only this extraction tool
reads the capture; the committed tests read the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path("C:/hengband-backups/pdca/captures/q2-pest-n1c-120-1103/captures/"
               "20261103-174536-stall-floor-dwell-quest-strategy-q-final-patrol")
OUTPUT = Path(__file__).with_name("fixtures") / "breeder-window-20261103.json.gz"
FIRST_BOARD, LAST_BOARD = 56, 97


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        ring = [json.loads(line) for line in stream if line.strip()]
    boards = ring[FIRST_BOARD:LAST_BOARD + 1]
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for raw in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in raw.get(field, [])}
    fixture = {
        "source": str(CAPTURE),
        "boards": boards,
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n", errors="surrogateescape") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
