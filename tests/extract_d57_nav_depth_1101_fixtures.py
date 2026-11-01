"""Freeze the D57 navigation and depth boards of 2026-11-01 (#47, d57-nav-depth-1101).

Sources: the automatic player-death captures of the viewing Magic-Eater n1-c,
copied read-only to C:/hengband-backups/pdca/captures/fix-n1c-deaths-1101/,
and the life-083 decision log copied read-only to
C:/hengband-backups/pdca/captures/d57-nav-depth-1101/life-083/ (one row of
``CASES`` per frozen case):

  n1c-079  life-079 (Lv12, 鉄獄12階, build 04ad2c6d2, 04:28): an absorbed
           Detect Evil showed a デスソード (race 107, NEVER_MOVE, speed +20)
           at (14,63); the next board no longer listed it, the descent route
           stepped beside it and the character went 151 -> -2 in one step.
           Ring boards of turns 600461-600610 (arrival to the last board).
  n1c-083  life-083 (Lv14, 迷宮12階, build c326f0fd6, 06:2x): a Labyrinth
           dive of the over-extension alternate with seven emergency escapes
           and no pickup, ended by Word of Recall.  Ring boards of turns
           1186699-1187204 (the first escape to the town arrival).

Each case keeps its player boards (one per turn), the last skill-proficiency
and Home knowledge rows before them, the policy-state ``_me_staff_sequence``
record, the monster knowledge of their monsters, the DungeonDefinitions rows
of the entered dungeons and the recorded decision rows of the same turns
(with ``over_extension``).  Only this extraction tool reads the captures; the
committed tests read the frozen fixtures alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/fix-n1c-deaths-1101")
LOGS = Path("C:/hengband-backups/pdca/captures/d57-nav-depth-1101")
FIXTURES = Path(__file__).with_name("fixtures")
EDIT = Path("C:/hengband/lib/edit")
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "player",
                   "position", "over_extension")
# name: (incident capture, decision log or None, (first turn, last turn))
CASES = {
    "n1c-079": ("life-079/incident-captures/20261101-042804-player-death", None,
                (600461, 600610)),
    "n1c-083": ("life-083/incident-captures/20261101-064758-player-death",
                LOGS / "life-083" / "bot-decisions.jsonl.gz", (1186699, 1187204)),
}


def decision_rows(lines, turns):
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a bounded tail starts in the middle of a record
        if row.get("turn") in turns and "reason" in row:
            rows.append({field: row.get(field) for field in DECISION_FIELDS})
    return rows


def freeze(name, capture, log, span, races, dungeons):
    incident = ROOT / capture
    rows = ring_rows(incident / "snapshots" / "snapshots-current.jsonl.gz")
    first, last = span
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if (row["type"] == "player_turn" and first <= row["turn"] <= last
                and row["turn"] not in turns):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    assert {first, last} <= turns, (name, first, last)
    if log is None:
        lines = (incident / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines()
    else:
        with gzip.open(log, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines()
    state = json.loads((incident / "policy-state.json").read_text(encoding="utf-8"))["state"]
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    fixture = dict(
        source=f"{capture} (copied from the viewing server)",
        boards=boards,
        decisions=decision_rows(lines, turns),
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state.get("_me_staff_sequence"),
        monraces={key: asdict(races[key]) for key in sorted(ids)},
        dungeons={key: asdict(dungeons[key])
                  for key in sorted(boards[0]["progress"]["entered_dungeon_ids"])},
    )
    output = FIXTURES / f"d57-{name}-1101.json.gz"
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    return output


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    for name, (capture, log, span) in CASES.items():
        output = freeze(name, capture, log, span, races, dungeons)
        print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
