"""Freeze the two n1-c loop stops of 2026-11-02 03:36 / 03:38 (n1c-loops-0336-1102).

Sources: the viewing Magic-Eater n1-c (build bot-df4001950), copied read-only
to C:/hengband-backups/pdca/captures/n1c-loops-0336-1102/:

  life-100-033602/incident-captures/20261102-033533-loop-detected
      life-100 (Lv27, オークの洞窟16階): the snapshot ring, the policy-state
      ``_me_staff_sequence`` record; life-100-033602/bot-decisions.jsonl.gz
      the decision rows.  Kept: the player boards of turns 1469200-1469360
      (the corridor loop between (42,92) and (41,93)), the monster
      knowledge of their monsters, the DungeonDefinitions rows of the entered
      dungeons and the recorded decision rows of the same turns.
  life-101-033837/incident-captures/20261102-033821-livelock-exhausted
      life-101 (a new Lv1 character, the Outpost): the snapshot ring from the
      birth on.  Kept: the first board after the opening absorption (turn
      75015), the knowledge rows before it, the General store page the game
      showed on the first entry (turn 75127), the store entrances and the
      recorded decision rows of the first visit and wait (decisions 8-30 of
      the first session, life-101 jsonlog/bot-decisions.jsonl).

Only this extraction tool reads the captures; the committed test reads the
fixtures.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-loops-0336-1102")
EDIT = Path("C:/hengband/lib/edit")
FIXTURES = Path(__file__).with_name("fixtures")
LOOT = dict(
    capture=ROOT / "life-100-033602/incident-captures/20261102-033533-loop-detected",
    decisions=ROOT / "life-100-033602/bot-decisions.jsonl.gz",
    turns=(1469200, 1469360),
    output=FIXTURES / "n1c-loot-corridor-20261102.json.gz",
)
RESTOCK = dict(
    capture=ROOT / "life-101-033837/incident-captures/20261102-033821-livelock-exhausted",
    # The first session's decision rows (life-101 jsonlog/bot-decisions.jsonl,
    # copied read-only beside the captures).
    decisions=ROOT / "life-101-033837/bot-decisions-session1-8-30.jsonl",
    start_turn=75015, store_turn=75127,
    output=FIXTURES / "n1c-opening-restock-wait-20261102.json.gz",
)
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def races_of(races, boards):
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    return {key: asdict(races[key]) for key in sorted(ids) if key in races}


def write(path, fixture):
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(path, path.stat().st_size)


def loot_corridor(races, dungeons):
    capture = LOOT["capture"]
    first, last = LOOT["turns"]
    rows = ring_rows(capture / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if row["type"] == "player_turn" and first <= row["turn"] <= last and row["turn"] not in turns:
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    with gzip.open(LOOT["decisions"], "rt", encoding="utf-8") as stream:
        decisions = [{field: row.get(field) for field in DECISION_FIELDS}
                     for row in map(json.loads, stream)
                     if row.get("turn") in turns and row.get("reason") not in {None, "loop-detected"}]
    state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))["state"]
    write(LOOT["output"], dict(
        source=f"{capture.relative_to(ROOT)} (copied from the viewing server)",
        boards=boards,
        decisions=decisions,
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state.get("_me_staff_sequence"),
        monraces=races_of(races, boards),
        dungeons={key: asdict(dungeons[key])
                  for key in sorted(boards[0]["progress"]["entered_dungeon_ids"])},
    ))


def opening_restock(races):
    capture = RESTOCK["capture"]
    rows = ring_rows(capture / "snapshots" / "snapshots-current.jsonl.gz")
    start = next(index for index, row in enumerate(rows)
                 if row["type"] == "player_turn" and row["turn"] == RESTOCK["start_turn"])
    page = next(row for row in rows
                if row["type"] == "store" and row["turn"] == RESTOCK["store_turn"])
    board = rows[start]
    cells = [[c["y"], c["x"], c["s"]] for c in board["grid_map"]["cells"] if "s" in c]
    decisions = [json.loads(line) for line in
                 RESTOCK["decisions"].read_text(encoding="utf-8").splitlines() if line.strip()]
    write(RESTOCK["output"], dict(
        id="life-101/20261102-033821-livelock-exhausted",
        source=f"{capture.relative_to(ROOT)} (copied from the viewing server)",
        board=board,
        pages={str(page["store"]["store_type"]): page["store"]},
        store_cells=cells,
        knowledge=[row for row in rows[:start] if row["type"] == "knowledge"],
        monraces=races_of(races, [board]),
        decisions=[dict({field: row.get(field) for field in DECISION_FIELDS},
                        procurement_requirements=row.get("procurement_requirements"),
                        in_store=row.get("in_store"))
                   for row in decisions],
    ))


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    loot_corridor(races, dungeons)
    opening_restock(races)


if __name__ == "__main__":
    main()
