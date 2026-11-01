"""Freeze the n1-a life-451 random-quest teleport boards (#47, rq-teleport-reserve-1101).

Source (read-only, copied from the viewing server by the D55 diagnosis):
C:/hengband-backups/pdca/captures/fix-deaths-1101/n1-a/life-451/
incident-captures/20261031-182443-player-death (Lv32 warrior, 鉄獄38階,
random quest 45 『カルバノグの殺人兎』, never seen).

- reserve-reached: the ring's 38F player_turn boards of turns
  1663508..1663533.  Decision 594 (1663519) read the sixth-from-last teleport
  ('rc', emergency:teleport, 5 -> 4 scrolls); decision 595 (1663533) went on
  looting (seek-loot) under the quest exit lock.
- reserve-held: turns 1662207..1662227.  Decision at 1662215 read a teleport
  (6 -> 5 scrolls); 1662227 is the board with exactly the reserve left.

Each case keeps the boards and the recorded decision rows of the same turns.
The snapshot ring copy is the tail of a multi-member gzip: decoding starts at
the first member header and keeps whole members only.  Only this extraction
tool reads the capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import decisions_by_turn, sha, tail_rows
from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/fix-deaths-1101")
CAPTURE = ROOT / "n1-a/life-451/incident-captures/20261031-182443-player-death"
OUTPUT = Path(__file__).with_name("fixtures") / "rq-teleport-reserve-1101.json.gz"
QUEST_FLOOR = (1, 38, 45)


def quest_floor_boards(rows: list[dict], first: int, last: int) -> list[dict]:
    by_turn = {
        row["turn"]: row
        for row in rows
        if row.get("type") == "player_turn"
        and first <= row["turn"] <= last
        and (row["floor"]["dungeon_id"], row["floor"]["level"],
             row["floor"]["quest_id"]) == QUEST_FLOOR
    }
    return [by_turn[turn] for turn in sorted(by_turn)]


def main():
    ring = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
    tail = CAPTURE / "decision-tail.jsonl"
    rows = ring_rows(ring.read_bytes())
    decisions = decisions_by_turn(tail_rows(tail))
    cases = {}
    for name, first, last in (
        ("reserve-reached", 1663508, 1663533),
        ("reserve-held", 1662207, 1662227),
    ):
        boards = quest_floor_boards(rows, first, last)
        cases[name] = dict(
            source=str(CAPTURE.relative_to(ROOT)).replace("\\", "/"),
            sources={ring.name: sha(ring), tail.name: sha(tail)},
            boards=boards,
            decisions=[decisions.get(board["turn"]) for board in boards],
        )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
