"""Freeze the n1-b life-392 boards of 2026-11-13 (オークの洞窟19階) for the confused read.

Source: the viewing Magic-Eater n1-b life-392, died 19:52:34 JST to a
<スラーネッシュ>の女悪魔 (claws CONFUSE, speed +10).  Its loop-detected capture
(~/hengbot-soak/n1-b/life-392/captures/20261113-195226-loop-detected/, copied
read-only to C:/hengband-backups/pdca/captures/n1b-392-recall-confirm-1113/)
holds the player boards (``state.jsonl.gz``) and the live decision log was
copied beside it (``jsonlog/bot-decisions.jsonl``).  The span is the summoner
shot at turn 1124309 to the last board 1124513 before the loop stop.

The capture holds no skill-proficiency row: the skill row is n1-b life-325's (the
same Magic-Eater character build), from tests/fixtures/n1b-325-low-hp-escape-1106.json.gz.
Only this extraction tool reads the copies; the committed test reads the fixture alone.

    python tests/extract_n1b_392_confused_read_1113_fixture.py <capture root>
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_deaths_1101_fixtures import DECISION_FIELDS


SPAN = (1124309, 1124513)
FIXTURES = Path(__file__).with_name("fixtures")
OUTPUT = FIXTURES / "n1b-392-confused-read-1113.json.gz"
SKILL_SOURCE = FIXTURES / "n1b-325-low-hp-escape-1106.json.gz"


def main(source: str):
    root = Path(source)
    boards, turns = [], set()
    state = root / "captures" / "20261113-195226-loop-detected" / "state.jsonl.gz"
    with gzip.open(state, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (row["type"] == "player_turn" and SPAN[0] <= row["turn"] <= SPAN[1]
                    and row["turn"] not in turns):
                turns.add(row["turn"])
                boards.append(row)
    assert {SPAN[0], SPAN[1]} <= turns
    decisions = []
    for line in (root / "jsonlog" / "bot-decisions.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("turn") in turns and "reason" in row:
            decisions.append({field: row.get(field) for field in (*DECISION_FIELDS, "messages")})
    with gzip.open(SKILL_SOURCE, "rt", encoding="utf-8") as stream:
        skill = json.load(stream)["skill"]
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    case = dict(
        source="n1-b life-392 loop-detected capture and decision log (viewing server, 2026-11-13)",
        boards=boards, decisions=decisions, skill=skill, home=None, sequence=None,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main(sys.argv[1])
