"""Freeze the n1-c life-102 Morivant return stop of 2026-11-02 05:10 (hourly-0600-1102).

Source: the viewing Magic-Eater n1-c (build bot-ff4196953), copied read-only to
C:/hengband-backups/pdca/captures/hourly-0600-1102/
n1-c-life-102-20261102-051020-quest-blocked-me-staff/:

  incident-captures/20261102-051004-quest-blocked-me-staff
      the snapshot ring and the policy-state ``_me_staff_sequence`` record
      (failure ``return-outpost-unavailable:me-staff:return-outpost``).
  bot-decisions.jsonl.gz
      the recorded decision rows.

Kept: the Morivant boards of turns 2457512 (after the absorb at the Tower,
the inn leg 'me-staff:return-outpost') and 2457605 (the travel
stopped at (28,63) by a puppy in view; the recorded stop), the knowledge
rows before them, the monster knowledge of their monsters, the entered
dungeons' definitions and the recorded decision rows of the same turns.

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import races_of, write


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0600-1102/"
            "n1-c-life-102-20261102-051020-quest-blocked-me-staff")
CAPTURE = ROOT / "incident-captures/20261102-051004-quest-blocked-me-staff"
EDIT = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "me-staff-grass-route-1102.json.gz"
TURNS = (2457512, 2457605)
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    boards, start = [], None
    for index, row in enumerate(rows):
        if row["type"] == "player_turn" and row["turn"] in TURNS and all(
                board["turn"] != row["turn"] for board in boards):
            start = index if start is None else start
            boards.append(row)
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decisions = [{field: row.get(field) for field in DECISION_FIELDS}
                     for row in map(json.loads, stream)
                     if row.get("turn") in TURNS and row.get("reason")]
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))["state"]
    write(OUTPUT, dict(
        source=f"{CAPTURE.relative_to(ROOT.parent)} (copied from the viewing server)",
        boards=boards,
        decisions=decisions,
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state["_me_staff_sequence"],
        monraces=races_of(races, boards),
        dungeons={key: asdict(dungeons[key])
                  for key in sorted(boards[0]["progress"]["entered_dungeon_ids"])},
    ))


if __name__ == "__main__":
    main()
