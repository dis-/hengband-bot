"""Freeze the n1-c life-080 Angband 5F descent board of 2026-11-01 (rq-after-q2-1102).

Source: the viewing Magic-Eater n1-c, incident capture copied read-only to
C:/hengband-backups/pdca/captures/viewing-incidents-20261101/n1-c/life-080/
incident-captures/20261101-050908-stuck-prompt/.  Its snapshot ring
snapshots-20261101-050824-a10a1a.jsonl.gz holds the 5F boards: recorded
decision 1872 at turn 577526 (鉄獄5階, (27,10) on the down staircase, Q2 not
taken) is ``descend`` '>', and turn 577527 is 鉄獄6階, random quest 49.

The fixture keeps the boards of SPAN (the walk onto the staircase and the
descent board), the last skill-proficiency and Home knowledge rows before
them, the policy-state ``_me_staff_sequence`` record, the monster knowledge
of their monsters, the recorded decision rows of the same turns and the
recorded absorbed-power decisions of this floor visit (``me-power:*`` rows
from ARRIVAL on; the capture's own ``_me_power_floor`` is the later town's)
and the RANDOM quest rows of lib/edit/quests (the production quest
knowledge).  Only this extraction tool reads the capture; the committed test
reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.quest_knowledge import (
    QUEST_TYPE_RANDOM, find_quest_definitions, load_quest_knowledge,
)
from tests.extract_d57_nav_depth_1101_fixtures import decision_rows
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


INCIDENT = Path("C:/hengband-backups/pdca/captures/viewing-incidents-20261101/n1-c/life-080/"
                "incident-captures/20261101-050908-stuck-prompt")
RING = INCIDENT / "snapshots" / "snapshots-20261101-050824-a10a1a.jsonl.gz"
SPAN = (577494, 577527)
ARRIVAL = 576284  # decision 1748, the first decision on 鉄獄5階
OUTPUT = Path(__file__).with_name("fixtures") / "rq-after-q2-n1c-080-1102.json.gz"


def main():
    rows = ring_rows(RING)
    first, last = SPAN
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if (row["type"] == "player_turn" and first <= row["turn"] <= last
                and row["turn"] not in turns):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    assert {first, last} <= turns, turns
    lines = (INCIDENT / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines()
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))["state"]
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    powers = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a bounded tail starts in the middle of a record
        if (ARRIVAL <= row.get("turn", 0) < last
                and str(row.get("reason", "")).startswith("me-power:")):
            powers.append({field: row.get(field)
                           for field in ("decision_sequence", "turn", "reason", "key", "position")})
    quests = load_quest_knowledge(find_quest_definitions(Path.cwd()))
    fixture = dict(
        source="viewing-incidents-20261101/n1-c/life-080 20261101-050908-stuck-prompt "
               "(copied from the viewing server)",
        boards=boards,
        decisions=decision_rows(lines, turns),
        power_uses=powers,
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state.get("_me_staff_sequence"),
        monraces={key: asdict(races[key]) for key in sorted(ids)},
        random_quests=[asdict(info) for info in quests.values() if info.type == QUEST_TYPE_RANDOM],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
