"""Freeze the n1-c life-107 Labyrinth 18F boards of 2026-11-02 (immobile-weak-kill-1102).

Source: the viewing Magic-Eater n1-c life-107 (Lv26, build bot-ddd9d4258),
迷宮18階 (dungeon 4, its bottom floor, where its guardian lives), copied
read-only to C:/hengband-backups/pdca/captures/immobile-weak-kill-1102/:
``live/eye-20261102-2002-rows.jsonl.gz`` (the boards of turns
1801340-1801897 from the live snapshot ring snapshots-20261102-201255-56f5cc,
with the last skill_exp and home knowledge rows before them),
``live/eye-20261102-2002-decisions.jsonl.gz`` (the decision rows of the same
turns) and the 19:55:03 loop-detected incident's policy-state.json of the same
floor visit.  A 発光アイ (race 80, NEVER_MOVE, GAZE:LOSE_STR, 18 HP) sits on
the corner (6,7) of the corridor the player walks up; its stat-drain ring
(immobile_threat_memory) takes the corridor out of every route, and the
recorded bot fired three blind ``*t`` shots from each cell of the corridor
(the eye was in view but never projectable) and turned back, round after round.

The fixture keeps the boards, the knowledge rows, the policy-state
``_me_staff_sequence`` and the floor's device-power uses before the boards
(``_me_power_floor``), the definitions of the entered dungeons, the monster
knowledge of the boards' monsters and the compact decision rows.  Only this
extraction tool reads the capture; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/immobile-weak-kill-1102")
ROWS = ROOT / "live/eye-20261102-2002-rows.jsonl.gz"
DECISIONS = ROOT / "live/eye-20261102-2002-decisions.jsonl.gz"
POLICY_STATE = ROOT / "20261102-195503-loop-detected/policy-state.json"
EDIT = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "immobile-weak-kill-20261102.json.gz"
FIRST, LAST = 1801340, 1801897


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    rows = _rows(ROWS)
    boards, turns = [], set()
    for row in rows:
        if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST \
                and row["turn"] not in turns:
            turns.add(row["turn"])
            boards.append(row)
    assert {FIRST, LAST} <= turns

    def knowledge(category):
        return next(row for row in rows if row.get("type") == "knowledge"
                    and row["knowledge"]["category"] == category)

    fixture = {"source": f"{ROOT} (copied from the viewing server)",
               "boards": boards, "skill": knowledge("skill_exp"),
               "home": knowledge("home")}
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
    # The guardians: the guardian-floor gate weighs the floor's own guardian.
    ids |= {row["guardian_id"] for row in fixture["dungeons"].values() if row["guardian_id"] > 0}
    fixture["monraces"] = {key: asdict(races[key]) for key in sorted(ids)}
    fixture["decisions"] = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
                            for row in _rows(DECISIONS) if row.get("turn") in turns]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
