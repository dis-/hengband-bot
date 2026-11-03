"""Freeze the n1-c life-120 Q2 boards of 2026-11-03 (q2-patrol-breeder-1103).

Source: the stall capture of 17:45:36 (stall:floor-dwell, reason
quest-strategy:q2-final-patrol), copied read-only to
C:/hengband-backups/pdca/captures/q2-pest-n1c-120-1103/captures/.  Every board
of its state ring is a walk (or a bump) of the final patrol on the floor the
breakthrough latch names (jsonlog/breeder-floor.json on the server).

The fixture keeps the capture's last boards, the compact decision rows of the
same turns and the monster knowledge of the boards' monsters.  Only this
extraction tool reads the capture; the committed tests read the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path("C:/hengband-backups/pdca/captures/q2-pest-n1c-120-1103/captures/"
               "20261103-174536-stall-floor-dwell-quest-strategy-q-final-patrol")
OUTPUT = Path(__file__).with_name("fixtures") / "q2-patrol-breeder-20261103.json.gz"
KEEP_BOARDS = 3


def rows(name):
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    boards = rows("state.jsonl.gz")[-KEEP_BOARDS:]
    turns = {raw["turn"] for raw in boards}
    ids = {row["race_id"] for raw in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in raw.get(field, [])}
    fixture = {
        "source": str(CAPTURE),
        "boards": boards,
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
        "decisions": [{"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
                      for row in rows("bot-decisions.jsonl.gz") if row["turn"] in turns],
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n", errors="surrogateescape") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
