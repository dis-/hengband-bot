"""Freeze the Q2 boards of n1-a life-482 and one of life-480 (q2-early-1105).

Source: the Q2 boards of the rotated snapshot logs, filtered to floor.quest_id == 2
and copied read-only to C:/hengband-backups/pdca/captures/q2-n1a-1105/q2-boards/.
The fixture keeps life-482 from the entrance to [2,20] (the board where the recorded
build left the north route) and the life-480 board at [12,46] just after the blue
icky things.  Only this extraction tool reads the capture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path("C:/hengband-backups/pdca/captures/q2-n1a-1105/q2-boards")
OUTPUT = Path(__file__).with_name("fixtures") / "q2-early-20261105.json.gz"
LAST_OPENING_TURN = 522987
AFTER_BLUE_TURN = 426031


def rows(name):
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    opening = [raw for raw in rows("life-482.jsonl.gz") if raw["turn"] <= LAST_OPENING_TURN]
    after_blue = next(raw for raw in rows("life-480.jsonl.gz") if raw["turn"] == AFTER_BLUE_TURN)
    ids = {row["race_id"] for raw in (*opening, after_blue)
           for field in ("visible_monsters", "detected_monsters")
           for row in raw.get(field, [])}
    fixture = {
        "source": str(CAPTURE),
        "boards": opening,
        "after_blue": after_blue,
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n", errors="surrogateescape") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
