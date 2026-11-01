"""Freeze the n1-c life-100 Yeek cave 5F loop boards of 2026-11-02 (n1c-5f-loop-1102).

Source: the viewing Magic-Eater n1-c life-100 (Lv8, 133 max HP, build
dc64cf14a), イークの洞窟5階, copied read-only to
C:/hengband-backups/pdca/captures/n1c-1102-0200/:

  incident-captures/20261102-015953-loop-detected  the snapshot ring and the
      policy state of the 01:59:56 loop-detected stop.
  20261102-015956-loop-detected/bot-decisions.jsonl.gz  the decision rows.

The fixture keeps the player boards (one per turn) from the 5F arrival (turn
550684) to the stop (551108), the last skill-proficiency and Home knowledge
rows before them, the policy-state ``_me_staff_sequence`` record, the monster
knowledge of their monsters, the DungeonDefinitions rows of the entered
dungeons and the recorded decision rows of the same turns.  Only this
extraction tool reads the captures; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-1102-0200")
INCIDENT = ROOT / "incident-captures/20261102-015953-loop-detected"
DECISIONS = ROOT / "20261102-015956-loop-detected/bot-decisions.jsonl.gz"
EDIT = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-5f-loop-20261102.json.gz"
FIRST, LAST = 550684, 551108
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    rows = ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if (row["type"] == "player_turn" and FIRST <= row["turn"] <= LAST
                and row["turn"] not in turns):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    assert {FIRST, LAST} <= turns
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        decisions = [{field: row.get(field) for field in DECISION_FIELDS}
                     for row in map(json.loads, stream)
                     if row.get("turn") in turns and row.get("reason") != "loop-detected"]
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))["state"]
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    fixture = dict(
        source=f"{INCIDENT.relative_to(ROOT.parent)} (copied from the viewing server)",
        boards=boards,
        decisions=decisions,
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state.get("_me_staff_sequence"),
        monraces={key: asdict(races[key]) for key in sorted(ids)},
        dungeons={key: asdict(dungeons[key])
                  for key in sorted(boards[0]["progress"]["entered_dungeon_ids"])},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
