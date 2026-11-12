"""Freeze the n1-c life-205 loop boards of 2026-11-13 04:49 (ガラスの城60階).

Source: the automatic loop-detected capture of the viewing Magic-Eater n1-c
(Lv42), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-205-summoner-explore-osc-1113/incident/
(life-205/incident-captures/20261113-044903-loop-detected/):

  snapshots/snapshots-current.jsonl.gz
      the snapshot ring.  It holds two timelines (the save was reloaded once:
      turn 2928567 on 1F back to 2916602 on 50F); only the last one is kept,
      from the last arrival on 60F (turn 2921091) to the stop (2922761): the
      alternation of ``explore:avoid-immobile-summoner`` '9' at (29, 38) and
      ``explore`` '1' at (28, 39) beside the ノーム・メイジ group (race 281, a
      summoner), and the repeated Teleport Away up to the loop detector;
  decision-tail.jsonl
      the recorded decision rows of the same timeline;
  policy-state.json
      the stop's Magic-Eater staff record (``_me_staff_sequence``) and the absorbed
      powers' uses on this floor visit (``_me_power_floor``);
  20261113-044904-loop-detected/control-at-stop.json.gz (the stop's capture directory)
      the game's input context at the stop.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.

    python tests/extract_n1c_205_summoner_explore_1113_fixture.py
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_deaths_1101_fixtures import DECISION_FIELDS
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-205-summoner-explore-osc-1113")
INCIDENT = ROOT / "incident"
STOP = ROOT / "20261113-044904-loop-detected" / "control-at-stop.json.gz"
FLOOR = (20, 60)
FIRST, LAST = 2921091, 2922761
OUTPUT = Path(__file__).with_name("fixtures") / "loop-n1c-205-1113.json.gz"


def last_timeline(rows: list[dict]) -> int:
    """The index where the last timeline's player turns begin (after a reload)."""
    start, previous = 0, None
    for index, row in enumerate(rows):
        if row.get("type") != "player_turn":
            continue
        if previous is not None and row["turn"] < previous:
            start = index
        previous = row["turn"]
    return start


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    rows = ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns, start = [], set(), None
    for index in range(last_timeline(rows), len(rows)):
        row = rows[index]
        if (row["type"] == "player_turn" and FIRST <= row["turn"] <= LAST
                and (row["floor"]["dungeon_id"], row["floor"]["level"]) == FLOOR
                and row["turn"] not in turns):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    assert (boards[0]["turn"], boards[-1]["turn"]) == (FIRST, LAST)
    tail = []
    for line in (INCIDENT / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            tail.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
    decisions, previous = [], None
    for row in tail:
        if "reason" not in row or not isinstance(row.get("turn"), int):
            continue
        if previous is not None and row["turn"] < previous:
            decisions = []  # an earlier timeline (the reload)
        previous = row["turn"]
        if row["turn"] in turns:
            decisions.append({field: row.get(field) for field in DECISION_FIELDS})
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    with gzip.open(STOP, "rt", encoding="utf-8") as stream:
        stop = json.load(stream)
    case = dict(
        source="life-205/incident-captures/20261113-044903-loop-detected (copied from the viewing server)",
        boards=boards,
        decisions=decisions,
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state["state"].get("_me_staff_sequence"),
        me_power_floor=state["state"].get("_me_power_floor"),
        stop={"input_kind": stop["input_kind"], "input_prompt": stop["input_prompt"],
              "turn": stop["state"].get("turn")},
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]), len(decisions))


if __name__ == "__main__":
    main()
