"""Freeze the 2026-10-31 n1-b life-283 board just after Q34 was accepted.

Source: the automatic capture incident-captures/20261031-232924-loop-detected
of the viewing warrior n1-b life-283 (Lv1 zombie warrior, build
bot-404e73286).  The new character bought fifteen torches for Q34's twenty
(QUEST_34 throwing_items.lit_torch, owner 2026-10-30 「松明20本はキープして」)
and accepted the quest at turn 75210.  The next boards shelved the fifteen
at Home (turn 75416) and the town then waited for a general-store restock
it could not use, until loop-detected (23:29:27) and owner-retired-burst
(23:34:52); the same shape recurred on bot-13e2f14d0 (23:42:55).

Frozen in the shape tests/test_unid_deposit_recorded.py reads: the first
board (arrival), every store/knowledge/character observation before the
board, the opening ~9 Home answer, the acceptance board (twenty torches
carried), the board of turn 75692 (five carried, fifteen on the Home page,
just out of the General Store) and the store entrances.  Only this tool
reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-1031-2323/life-283/"
               "incident-captures/20261031-232924-loop-detected")
OUTPUT = Path(__file__).with_name("fixtures") / "q34-taken-torches-20261031.json.gz"
ACCEPTED_TURN, BOARD_TURN = 75210, 75692


def main():
    ring = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
    rows = ring_rows(ring.read_bytes())
    accepted = next(i for i, row in enumerate(rows)
                    if row["type"] == "player_turn" and row["turn"] == ACCEPTED_TURN)
    board = next(i for i, row in enumerate(rows)
                 if row["type"] == "player_turn" and row["turn"] == BOARD_TURN)
    assert [q["status"] for q in rows[accepted]["progress"]["quests"] if q["id"] == 34] == [1]
    case = dict(
        source="incident-20261031-232924-loop-detected (n1-b life-283)",
        sources={ring.name: hashlib.sha256(ring.read_bytes()).hexdigest()},
        arrival=rows[0],
        observations=[row for row in rows[1:board] if row["type"] in ("store", "knowledge", "character")],
        home_answer=next(row for row in rows[:board] if row["type"] == "knowledge"
                         and row["knowledge"]["category"] == "home"),
        accepted=rows[accepted],
        board=rows[board],
        store_cells=[[c["y"], c["x"], c["s"]] for c in rows[board]["grid_map"]["cells"] if "s" in c],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["observations"]), "observations")


if __name__ == "__main__":
    main()
