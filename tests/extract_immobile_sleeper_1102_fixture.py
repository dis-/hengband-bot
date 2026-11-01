"""Freeze the n1-c life-103 Silver jelly boards of 2026-11-02 (shoot-immobile-sleeper-1102).

Source: the viewing Magic-Eater n1-c life-103 (Lv9), 鉄獄5階, copied read-only
to C:/hengband-backups/pdca/captures/hourly-0600-1102/
n1-c-life-103-20261102-053149-loop-detected/: the live snapshot ring of the
05:31:45 loop-detected capture, boards of turns 412529-412823 (decision
sequences 4278-4306).  A sleeping シルバー・ゼリー (race 73, NEVER_MOVE) lies
seven cells east of the player on a clear row; the recorded bot retreated
(``threat:avoid-engagement``), explored back towards it and boxed itself in.

The fixture keeps the boards, the last skill-proficiency and Home knowledge
rows of the ring before the boards, the policy-state ``_me_staff_sequence``
and the floor's device-power uses before the boards (``_me_power_floor``),
the definitions of the entered dungeons, the monster knowledge of the boards'
monsters and the compact decision rows of the same turns.  Only this
extraction tool reads the capture; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0600-1102/"
            "n1-c-life-103-20261102-053149-loop-detected")
RING = ROOT / "incident-captures/20261102-053145-loop-detected/snapshots/snapshots-current.jsonl.gz"
DECISIONS = ROOT / "bot-decisions.jsonl.gz"
POLICY_STATE = ROOT / "incident-captures/20261102-053145-loop-detected/policy-state.json"
EDIT = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "immobile-sleeper-20261102.json.gz"
FIRST, LAST = 412529, 412823


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    rows = ring_rows(RING)
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST \
                and row["turn"] not in turns:
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    assert {FIRST, LAST} <= turns

    def last_knowledge(category):
        return next(row for row in reversed(rows[:start]) if row.get("type") == "knowledge"
                    and row["knowledge"]["category"] == category)

    fixture = {"source": f"{RING.parent.parent} (copied from the viewing server)",
               "boards": boards, "skill": last_knowledge("skill_exp"),
               "home": last_knowledge("home")}
    ids = {row["race_id"] for raw in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in raw.get(field, [])}
    state = json.loads(POLICY_STATE.read_text(encoding="utf-8"))["state"]
    fixture["sequence"] = state["_me_staff_sequence"]
    floor = state["_me_power_floor"]
    fixture["power_floor"] = dict(floor, turn=FIRST, uses=[use for use in floor["uses"]
                                               if use["turn"] < FIRST])
    dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    fixture["dungeons"] = {key: asdict(dungeons[key])
                           for key in sorted(boards[0]["progress"]["entered_dungeon_ids"])}
    fixture["monraces"] = {key: asdict(races[key]) for key in sorted(ids)}
    decisions = []
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") in turns:
                decisions.append({"turn": row["turn"], "reason": row["reason"],
                                  "key": row["key"]})
    fixture["decisions"] = decisions
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
