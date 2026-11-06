"""Freeze the n1-b life-325 boards of 2026-11-06 (城33階) for the low-HP escape.

Source: the viewing Magic-Eater n1-b life-325 (build cbdf723f5), died 19:23 JST
to a 智天使's fire bolt.  Its state-log tail and decision tail were copied to
the session scratchpad (``SOURCE`` below): the player boards of turns
2100352-2100412 and the decision rows of the same turns.  At turn 2100389
(HP 153/386) the emergency ladder read Teleportation, the dive's second
emergency, without latching the town return; at 2100397 (HP 155, 13 hostiles
in view: the hasted 智天使 summoner, ten jackals, a キング・コブラ, the
TELE_TO セイレーン) the walk gate let one ``summoner:retreat`` step through.

The tail holds no skill-proficiency or Home knowledge row: the skill row is
n1-b life-292's (the same Magic-Eater character build), taken from
tests/fixtures/n1b-292-summoner-after-survival-1102.json.gz.  Only this
extraction tool reads the copies; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_deaths_1101_fixtures import DECISION_FIELDS


SPAN = (2100352, 2100412)
FIXTURES = Path(__file__).with_name("fixtures")
OUTPUT = FIXTURES / "n1b-325-low-hp-escape-1106.json.gz"
SKILL_SOURCE = FIXTURES / "n1b-292-summoner-after-survival-1102.json.gz"


def main(source: str):
    root = Path(source)
    boards, turns = [], set()
    for line in (root / "state-tail.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (row["type"] == "player_turn" and SPAN[0] <= row["turn"] <= SPAN[1]
                and row["turn"] not in turns):
            turns.add(row["turn"])
            boards.append(row)
    assert {SPAN[0], SPAN[1]} <= turns
    decisions = []
    for line in (root / "tail.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("turn") in turns and "reason" in row:
            decisions.append({field: row.get(field) for field in DECISION_FIELDS}
                             | {"over_extension": row.get("over_extension")})
    with gzip.open(SKILL_SOURCE, "rt", encoding="utf-8") as stream:
        skill = json.load(stream)["skill"]
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    case = dict(
        source="n1-b life-325 state-tail/decision tail (viewing server, 2026-11-06)",
        boards=boards, decisions=decisions, skill=skill, home=None, sequence=None,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main(sys.argv[1])
