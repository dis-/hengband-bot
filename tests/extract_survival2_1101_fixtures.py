"""Freeze the survival2-1101 boards (#47, owner answers of 2026-11-01 21h).

Sources: turn windows of the viewing bots, copied read-only to
C:/hengband-backups/pdca/captures/survival2-1101/ (README.txt there names the
server file of each window; one row of ``CASES`` per frozen case):

  n1c-092  n1-c life-092 (Lv12 zombie Magic-Eater, Angband 14F, build
           38cc744aa, 2026-11-01 12:0x): hunted a レッド・ゼリー (race 131,
           NEVER_MOVE, TOUCH:LOSE_STR) at (16,86) to the cell beside it
           (turn 1065156 '1' hunt) and fired beside it, drained eight times
           until it died at turn 1065268.  Boards 1065063-1065240.
  n1b-287  n1-b life-287 (Lv23 warrior, Labyrinth 15F, build 04ad2c6d2,
           2026-11-01 03:5x): hunted the sleeping レッド・ゼリー at (6,43)
           (turn 929114 '4' to (6,44)) and meleed it, drained twice.  Boards
           929001-929197 (no decision log: the life's jsonlog was pruned).
  n1a-459  n1-a life-459 (Lv15 warrior, random quest 49 on Angband 6F):
           meleed beside a 自縛霊 (race 1012, NEVER_MOVE, TOUCH:LOSE_WIS) on a
           quest floor.  Boards 374062-374159 (no decision log in the copy).

Each case keeps its player boards (one per turn), the last skill-proficiency
and Home knowledge rows before them, the monster knowledge of their monsters,
the recorded decision rows of the same turns where the copy has them, and for
the Magic-Eater the policy-state ``_me_staff_sequence`` record and the floor's
recorded new-floor power casts (decision rows 4545-4549 of
jsonlog/bot-decisions.jsonl.5, turns 1063321-1063367).  Only this extraction
tool reads the captures; the committed tests read the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_deaths_1101_fixtures import DECISION_FIELDS


ROOT = Path("C:/hengband-backups/pdca/captures/survival2-1101")
FIXTURE = Path(__file__).with_name("fixtures") / "survival2-1101.json.gz"
# name: (window, decision rows or None, policy state or None, first, last)
CASES = {
    "n1c-092": ("n1-c/life-092/ring-1064800-1065500.jsonl.gz",
                "n1-c/life-092/decisions-1064800-1065500.jsonl.gz",
                "n1-c/life-092/policy-state-121826.json", 1065063, 1065240),
    "n1b-287": ("n1-b/life-287/ring-929000-929200.jsonl.gz", None, None, 929001, 929197),
    "n1a-459": ("n1-a/life-459/ring-374000-374200.jsonl.gz", None, None, 374062, 374159),
}
# The recorded new-floor casts of the life-092 floor (turn, power effect).
NEW_FLOOR_CASTS = ((1063321, "map-area"), (1063358, "detect-evil"), (1063367, "detect-traps"))


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _knowledge(rows, category):
    return next((row for row in rows if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == category), None)


def freeze_case(window, decisions, state, first, last, races) -> dict:
    rows = _rows(ROOT / window)
    boards, turns = [], set()
    for row in rows:
        if row["type"] == "player_turn" and first <= row["turn"] <= last and row["turn"] not in turns:
            turns.add(row["turn"])
            boards.append(row)
    assert {first, last} <= turns, (window, first, last)
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    case = dict(
        source=f"{window} (copied from the viewing server)",
        boards=boards,
        skill=_knowledge(rows, "skill_exp"),
        home=_knowledge(rows, "home"),
        monraces={key: asdict(races[key]) for key in sorted(ids)},
        decisions=[],
    )
    if decisions is not None:
        case["decisions"] = [{field: row.get(field) for field in DECISION_FIELDS}
                             for row in _rows(ROOT / decisions)
                             if row.get("turn") in turns and "reason" in row]
    if state is not None:
        record = json.loads((ROOT / state).read_text(encoding="utf-8"))
        case["sequence"] = record["state"].get("_me_staff_sequence")
        case["new_floor_casts"] = [list(cast) for cast in NEW_FLOOR_CASTS]
    return case


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    fixture = {name: freeze_case(*spec, races) for name, spec in CASES.items()}
    with gzip.open(FIXTURE, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(FIXTURE, FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
