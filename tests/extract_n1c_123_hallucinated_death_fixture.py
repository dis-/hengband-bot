"""Freeze the n1-c life-123 death boards of 2026-11-04 05:16 (城30階).

Source: the automatic player-death capture of the viewing Magic-Eater n1-c, copied
read-only to C:/hengband-backups/pdca/captures/stops-1104-morning/n1-c/life-123/
incident-captures/20261104-051655-player-death/: the player boards of turns
3934099-3934853.  The layout is extract_n1c_deaths_1101_fixtures.freeze's, whose
race lookup cannot read a hallucinated monster (the board names no race).  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_deaths_1101_fixtures import decision_rows
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


INCIDENT = Path("C:/hengband-backups/pdca/captures/stops-1104-morning/n1-c/life-123/"
                "incident-captures/20261104-051655-player-death")
SPAN = (3934099, 3934853)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1c-123-1104.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    rows = ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if (row["type"] == "player_turn" and row["turn"] not in turns
                and SPAN[0] <= row["turn"] <= SPAN[1]):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for monster in board.get(field, []) if "race_id" in monster}
    case = dict(
        source=INCIDENT.name, boards=boards, decisions=decision_rows(INCIDENT / "decision-tail.jsonl", turns),
        skill=knowledge(rows, start, "skill_exp"), home=knowledge(rows, start, "home"),
        sequence=state["state"].get("_me_staff_sequence"),
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
