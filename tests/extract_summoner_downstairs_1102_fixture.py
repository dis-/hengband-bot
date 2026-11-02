"""Freeze the n1-c life-103 23F boards of an avoided クイルスルグ (2026-11-02).

Sources (copied read-only from the viewing server):
- boards: C:/hengband-backups/pdca/captures/viewing-incidents-20261102/n1-c/
  life-103/incident-captures/20261102-134240-town-blocked-survival-
  inventory_weight_ready, snapshot ring generation
  snapshots-20261102-131600-b3bb3c (Angband 23F, floor (3, 23, 0)).
- decisions: the decision rows of the same turns as the read-only
  investigation exported them from the full life-103 decision log,
  C:/hengband-backups/pdca/captures/summoner-avoid-1102/n1c-life103-timeline.tsv
  (time, turn, floor, position, HP, visible hostiles, reason, key); the
  incident's own decision tail starts at 13:37 and does not reach 13:09.
  ``decision_sequence`` is the timeline line number.  ``floor_powers`` are
  the same timeline's Magic-Eater power rows of this floor visit (from the
  12:59:14 arrival), which the ring does not reach.

At 13:09:33 (turn 3693780) the bot saw a クイルスルグ (race 342, NEVER_MOVE,
S_MONSTER) at (36,192); from then on the immobile-summoner owner explored
the whole floor (209 ``explore:avoid-immobile-summoner`` decisions, to
13:10:48), read Recall at (29,3) and waited.  Frozen: the first 31 player
boards of the avoidance, turns 3693780-3694083, in the layout of
extract_n1c_deaths_1101_fixtures.freeze.
Only this extraction tool reads the captures; the committed test reads the
fixture alone.
"""

from __future__ import annotations

import ast
import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/viewing-incidents-20261102/n1-c/life-103/incident-captures")
CAPTURE = "20261102-134240-town-blocked-survival-inventory_weight_ready"
RING = "snapshots-20261102-131600-b3bb3c.jsonl.gz"
TIMELINE = Path("C:/hengband-backups/pdca/captures/summoner-avoid-1102/n1c-life103-timeline.tsv")
SPAN = (3693780, 3694083)  # the first 31 boards of the avoidance
FLOOR = (3, 23)


def _on_floor(row) -> bool:
    return (row["floor"]["dungeon_id"], row["floor"]["level"]) == FLOOR


def timeline_rows(turns: set[int]) -> list[dict]:
    rows = []
    for number, line in enumerate(TIMELINE.read_text(encoding="utf-8").splitlines(), 1):
        cells = line.split("\t")
        if not cells[1].isdigit():
            continue  # rows without a game turn (stops, session lines)
        turn = int(cells[1])
        if turn in turns and (cells[2], cells[3]) == tuple(map(str, FLOOR)):
            y, x = (int(value) for value in cells[5].split(","))
            rows.append({"decision_sequence": number, "turn": turn, "reason": cells[9],
                         "key": ast.literal_eval(cells[10]), "position": {"y": y, "x": x}})
    return rows


def floor_power_rows(first_turn: int) -> list[dict]:
    """The Magic-Eater power rows of this floor visit before ``first_turn``
    (the visit began at 12:59:14; the ring starts later)."""
    rows = []
    for line in TIMELINE.read_text(encoding="utf-8").splitlines():
        cells = line.split("	")
        if not cells[1].isdigit() or int(cells[1]) >= first_turn:
            continue
        if (cells[2], cells[3]) != tuple(map(str, FLOOR)):
            rows = []  # another floor: the visit starts after it
            continue
        if cells[9].startswith("me-power:"):
            y, x = (int(value) for value in cells[5].split(","))
            rows.append({"turn": int(cells[1]), "reason": cells[9],
                         "key": ast.literal_eval(cells[10]), "position": {"y": y, "x": x}})
    return rows


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    frozen = freeze("n1c-103-quylthulg", CAPTURE, (SPAN,), races, root=ROOT, ring=RING,
                    keep=_on_floor)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    case["decisions"] = timeline_rows({board["turn"] for board in case["boards"]})
    case["source"] += "; decisions: n1c-life103-timeline.tsv"
    case["floor_powers"] = floor_power_rows(SPAN[0])
    if case["skill"] is None:
        # The generation holds no skill list before the span: its first one
        # (read-only proficiency, the same character and level).
        rows = ring_rows(ROOT / CAPTURE / "snapshots" / RING)
        case["skill"] = next(row for row in rows if row["type"] == "knowledge"
                             and row["knowledge"]["category"] == "skill_exp")
    output = frozen.with_name("summoner-downstairs-1102.json.gz")
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    frozen.unlink()
    print(output, output.stat().st_size, len(case["boards"]), len(case["decisions"]))


if __name__ == "__main__":
    main()
