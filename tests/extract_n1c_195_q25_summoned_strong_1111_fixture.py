"""Freeze n1-c life-195's Quest 25 visit (2026-11-11, game 04:32-05:40) for the summoned-strong test.

Source: n1-c life-195 (build bot-69967a2e2) on hengband.net, the snapshot ring generation closed at
11:03:55 (~/hengbot-soak/n1-c/life-195/jsonlog/snapshots/snapshots-20261111-110355-85f258.jsonl.gz),
copied to C:/hengband-backups/pdca/captures/n1c-195-q25-summoned-strong-1111/.  The decision log of
that window had rotated away (bot-decisions.jsonl.7 begins at 19:34), so no key or reason was
recorded: the ring's rows are the boards the game showed the bot, one per decision, in order.

Kept: every board on the Q25 floor from the entry on the start stair [13,1] (turn 2593911) through
``LAST_TURN`` (05:40, after the fifth Teleportation and the walk back to [5,1]); the first skill
list the ring holds (turn 2594104, read during the visit).  The process's magic-eater lists and
absorption record are not in the ring (its town-arrival checkpoint was overwritten later).

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_174_q25_loops_1109_fixture import ring_rows

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-195-q25-summoned-strong-1111")
RING = ROOT / "snapshots-20261111-110355-85f258.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-195-q25-summoned-strong-1111.json.gz"
QUEST = 25
FIRST_TURN, LAST_TURN = 2593911, 2598640


def main():
    rows = ring_rows(RING)
    boards = [row for row in rows if row.get("type") == "player_turn"
              and FIRST_TURN <= row["turn"] <= LAST_TURN and row["floor"].get("quest_id") == QUEST]
    assert (boards[0]["player"]["y"], boards[0]["player"]["x"]) == (13, 1), boards[0]["player"]
    skill = next(row for row in rows if row.get("type") == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = {"source": "n1c-195-q25-summoned-strong-1111", "boards": boards, "skill": skill,
            "monraces": {key: asdict(races[key]) for key in sorted(ids) if key in races}}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} boards "
                     f"{boards[0]['turn']}-{boards[-1]['turn']}\n")


if __name__ == "__main__":
    main()
